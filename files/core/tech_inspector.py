"""
Tech Inspection Validator
Defines per-car-class legal parameter ranges and validates/clamps setups
so they will pass iRacing's tech inspection at session start.

Why setups fail tech inspection:
  - iRacing enforces hard limits on every adjustable parameter per car.
  - Values outside these limits cause an immediate "FAILED TECH" at the grid.
  - The optimizer previously worked only in delta-space (±clicks) without
    checking whether the resulting absolute value stayed inside the legal range.

Usage:
    from core.tech_inspector import validate_setup, clamp_to_legal, BOUNDS

    issues = validate_setup(my_setup_dict, CarClass.GT3)
    legal  = clamp_to_legal(my_setup_dict, CarClass.GT3)
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Any

from core.car_classifier import CarClass


# ── Dataclasses ────────────────────────────────────────────────────────────────

@dataclass
class ParamBounds:
    min_val: float
    max_val: float
    step: float = 0.1           # smallest legal increment
    unit: str = ""              # display unit (psi, deg, mm, N/mm, %, …)
    display_name: str = ""      # human-readable label

    def clamp(self, value: float) -> float:
        """Round to nearest legal step then clamp to [min, max]."""
        snapped = round(round(value / self.step) * self.step, 6)
        return float(max(self.min_val, min(self.max_val, snapped)))

    def is_legal(self, value: float) -> bool:
        return self.min_val - 1e-6 <= value <= self.max_val + 1e-6


@dataclass
class TechIssue:
    param: str
    display_name: str
    value: float
    min_val: float
    max_val: float
    unit: str
    clamped_value: float

    @property
    def description(self) -> str:
        return (
            f"{self.display_name} = {self.value:.3g} {self.unit} "
            f"(legal range: {self.min_val:.3g}–{self.max_val:.3g} {self.unit}). "
            f"Auto-corrected to {self.clamped_value:.3g} {self.unit}."
        )


# ── Parameter bounds per car class ────────────────────────────────────────────
#
# Format:  param_key → ParamBounds(min, max, step, unit, display_name)
#
# Keys are the internal parameter names used throughout the app.
# These ranges are based on iRacing garage screens for each class.
# Where a class shares limits with another the _GT3 entry is referenced.
# ─────────────────────────────────────────────────────────────────────────────

_GT3: Dict[str, ParamBounds] = {
    # ── Alignment ─────────────────────────────────────────────────────────
    "camber_lf":        ParamBounds(-5.0, -1.5, 0.1,  "deg",   "LF Camber"),
    "camber_rf":        ParamBounds(-5.0, -1.5, 0.1,  "deg",   "RF Camber"),
    "camber_lr":        ParamBounds(-3.5, -0.5, 0.1,  "deg",   "LR Camber"),
    "camber_rr":        ParamBounds(-3.5, -0.5, 0.1,  "deg",   "RR Camber"),
    "toe_front":        ParamBounds(-3.0,  3.0, 0.1,  "mm",    "Front Toe (−=out, +=in)"),
    "toe_rear":         ParamBounds( 0.0,  5.0, 0.1,  "mm",    "Rear Toe (toe-in)"),
    # ── Tire pressures ────────────────────────────────────────────────────
    "pressure_lf":      ParamBounds(26.0, 38.0, 0.1,  "psi",   "LF Cold Pressure"),
    "pressure_rf":      ParamBounds(26.0, 38.0, 0.1,  "psi",   "RF Cold Pressure"),
    "pressure_lr":      ParamBounds(26.0, 38.0, 0.1,  "psi",   "LR Cold Pressure"),
    "pressure_rr":      ParamBounds(26.0, 38.0, 0.1,  "psi",   "RR Cold Pressure"),
    # ── Springs ───────────────────────────────────────────────────────────
    "spring_lf":        ParamBounds( 40.0, 200.0, 5.0, "N/mm", "LF Spring Rate"),
    "spring_rf":        ParamBounds( 40.0, 200.0, 5.0, "N/mm", "RF Spring Rate"),
    "spring_lr":        ParamBounds( 40.0, 200.0, 5.0, "N/mm", "LR Spring Rate"),
    "spring_rr":        ParamBounds( 40.0, 200.0, 5.0, "N/mm", "RR Spring Rate"),
    # ── ARB ───────────────────────────────────────────────────────────────
    "arb_front":        ParamBounds(1, 7, 1, "step", "Front ARB"),
    "arb_rear":         ParamBounds(1, 7, 1, "step", "Rear ARB"),
    # ── Ride height ───────────────────────────────────────────────────────
    "rh_lf":            ParamBounds(48.0,  95.0, 1.0, "mm",   "LF Ride Height"),
    "rh_rf":            ParamBounds(48.0,  95.0, 1.0, "mm",   "RF Ride Height"),
    "rh_lr":            ParamBounds(58.0, 110.0, 1.0, "mm",   "LR Ride Height"),
    "rh_rr":            ParamBounds(58.0, 110.0, 1.0, "mm",   "RR Ride Height"),
    # ── Dampers ───────────────────────────────────────────────────────────
    "bump_slow_lf":     ParamBounds(1, 18, 1, "clicks", "LF Slow Bump"),
    "bump_slow_rf":     ParamBounds(1, 18, 1, "clicks", "RF Slow Bump"),
    "bump_slow_lr":     ParamBounds(1, 18, 1, "clicks", "LR Slow Bump"),
    "bump_slow_rr":     ParamBounds(1, 18, 1, "clicks", "RR Slow Bump"),
    "bump_fast_lf":     ParamBounds(1, 12, 1, "clicks", "LF Fast Bump"),
    "bump_fast_rf":     ParamBounds(1, 12, 1, "clicks", "RF Fast Bump"),
    "bump_fast_lr":     ParamBounds(1, 12, 1, "clicks", "LR Fast Bump"),
    "bump_fast_rr":     ParamBounds(1, 12, 1, "clicks", "RR Fast Bump"),
    "rebound_slow_lf":  ParamBounds(1, 18, 1, "clicks", "LF Slow Rebound"),
    "rebound_slow_rf":  ParamBounds(1, 18, 1, "clicks", "RF Slow Rebound"),
    "rebound_slow_lr":  ParamBounds(1, 18, 1, "clicks", "LR Slow Rebound"),
    "rebound_slow_rr":  ParamBounds(1, 18, 1, "clicks", "RR Slow Rebound"),
    "rebound_fast_lf":  ParamBounds(1, 12, 1, "clicks", "LF Fast Rebound"),
    "rebound_fast_rf":  ParamBounds(1, 12, 1, "clicks", "RF Fast Rebound"),
    "rebound_fast_lr":  ParamBounds(1, 12, 1, "clicks", "LR Fast Rebound"),
    "rebound_fast_rr":  ParamBounds(1, 12, 1, "clicks", "RR Fast Rebound"),
    # ── Aerodynamics ──────────────────────────────────────────────────────
    "wing_front":       ParamBounds(0, 10, 1, "step", "Front Wing"),
    "wing_rear":        ParamBounds(0, 10, 1, "step", "Rear Wing"),
    "brake_duct_front": ParamBounds(0, 100, 10, "%",  "Front Brake Duct"),
    "brake_duct_rear":  ParamBounds(0, 100, 10, "%",  "Rear Brake Duct"),
    # ── Brakes ────────────────────────────────────────────────────────────
    "brake_bias":       ParamBounds(49.0, 63.0, 0.5, "%",  "Brake Bias (front)"),
    "brake_pressure":   ParamBounds(80.0, 100.0, 1.0, "%", "Max Brake Pressure"),
    # ── Electronics ───────────────────────────────────────────────────────
    "tc_1":             ParamBounds(0, 9, 1, "level", "Traction Control (TC1)"),
    "tc_2":             ParamBounds(0, 9, 1, "level", "Traction Control (TC2)"),
    "abs":              ParamBounds(0, 9, 1, "level", "ABS"),
    # ── Differential ──────────────────────────────────────────────────────
    "diff_preload":     ParamBounds(0, 200, 5, "Nm",  "Diff Preload"),
    "diff_power":       ParamBounds(0, 90,  5, "deg", "Diff Power Ramp"),
    "diff_coast":       ParamBounds(0, 90,  5, "deg", "Diff Coast Ramp"),
}

_GT4: Dict[str, ParamBounds] = {
    **_GT3,  # GT4 shares most limits; override specifics below
    "camber_lf":    ParamBounds(-4.5, -1.0, 0.1, "deg", "LF Camber"),
    "camber_rf":    ParamBounds(-4.5, -1.0, 0.1, "deg", "RF Camber"),
    "camber_lr":    ParamBounds(-3.0, -0.5, 0.1, "deg", "LR Camber"),
    "camber_rr":    ParamBounds(-3.0, -0.5, 0.1, "deg", "RR Camber"),
    "brake_bias":   ParamBounds(50.0, 62.0, 0.5, "%", "Brake Bias (front)"),
    "spring_lf":    ParamBounds(30.0, 150.0, 5.0, "N/mm", "LF Spring Rate"),
    "spring_rf":    ParamBounds(30.0, 150.0, 5.0, "N/mm", "RF Spring Rate"),
    "spring_lr":    ParamBounds(30.0, 150.0, 5.0, "N/mm", "LR Spring Rate"),
    "spring_rr":    ParamBounds(30.0, 150.0, 5.0, "N/mm", "RR Spring Rate"),
    "wing_front":   ParamBounds(0, 5, 1, "step", "Front Wing"),
    "wing_rear":    ParamBounds(0, 5, 1, "step", "Rear Wing"),
}

_GTP: Dict[str, ParamBounds] = {
    **_GT3,
    "camber_lf":    ParamBounds(-5.5, -2.0, 0.1, "deg", "LF Camber"),
    "camber_rf":    ParamBounds(-5.5, -2.0, 0.1, "deg", "RF Camber"),
    "camber_lr":    ParamBounds(-4.0, -1.0, 0.1, "deg", "LR Camber"),
    "camber_rr":    ParamBounds(-4.0, -1.0, 0.1, "deg", "RR Camber"),
    "pressure_lf":  ParamBounds(22.0, 34.0, 0.1, "psi", "LF Cold Pressure"),
    "pressure_rf":  ParamBounds(22.0, 34.0, 0.1, "psi", "RF Cold Pressure"),
    "pressure_lr":  ParamBounds(20.0, 32.0, 0.1, "psi", "LR Cold Pressure"),
    "pressure_rr":  ParamBounds(20.0, 32.0, 0.1, "psi", "RR Cold Pressure"),
    "brake_bias":   ParamBounds(47.0, 60.0, 0.5, "%", "Brake Bias (front)"),
    "spring_lf":    ParamBounds(60.0, 300.0, 5.0, "N/mm", "LF Spring Rate"),
    "spring_rf":    ParamBounds(60.0, 300.0, 5.0, "N/mm", "RF Spring Rate"),
    "spring_lr":    ParamBounds(60.0, 300.0, 5.0, "N/mm", "LR Spring Rate"),
    "spring_rr":    ParamBounds(60.0, 300.0, 5.0, "N/mm", "RR Spring Rate"),
    "rh_lf":        ParamBounds(30.0, 80.0, 1.0, "mm", "LF Ride Height"),
    "rh_rf":        ParamBounds(30.0, 80.0, 1.0, "mm", "RF Ride Height"),
    "rh_lr":        ParamBounds(40.0, 100.0, 1.0, "mm", "LR Ride Height"),
    "rh_rr":        ParamBounds(40.0, 100.0, 1.0, "mm", "RR Ride Height"),
    "wing_front":   ParamBounds(0, 12, 1, "step", "Front Wing"),
    "wing_rear":    ParamBounds(0, 12, 1, "step", "Rear Wing"),
}

_LMP2: Dict[str, ParamBounds] = {
    **_GTP,
    "wing_front": ParamBounds(0, 10, 1, "step", "Front Wing"),
    "wing_rear":  ParamBounds(0, 10, 1, "step", "Rear Wing"),
}

_FORMULA: Dict[str, ParamBounds] = {
    **_GT3,
    "camber_lf":    ParamBounds(-5.0, -1.0, 0.1, "deg", "LF Camber"),
    "camber_rf":    ParamBounds(-5.0, -1.0, 0.1, "deg", "RF Camber"),
    "camber_lr":    ParamBounds(-3.5, -0.5, 0.1, "deg", "LR Camber"),
    "camber_rr":    ParamBounds(-3.5, -0.5, 0.1, "deg", "RR Camber"),
    "pressure_lf":  ParamBounds(20.0, 32.0, 0.1, "psi", "LF Cold Pressure"),
    "pressure_rf":  ParamBounds(20.0, 32.0, 0.1, "psi", "RF Cold Pressure"),
    "pressure_lr":  ParamBounds(18.0, 30.0, 0.1, "psi", "LR Cold Pressure"),
    "pressure_rr":  ParamBounds(18.0, 30.0, 0.1, "psi", "RR Cold Pressure"),
    "brake_bias":   ParamBounds(50.0, 65.0, 0.5, "%", "Brake Bias (front)"),
    "spring_lf":    ParamBounds(50.0, 400.0, 10.0, "N/mm", "LF Spring Rate"),
    "spring_rf":    ParamBounds(50.0, 400.0, 10.0, "N/mm", "RF Spring Rate"),
    "spring_lr":    ParamBounds(50.0, 400.0, 10.0, "N/mm", "LR Spring Rate"),
    "spring_rr":    ParamBounds(50.0, 400.0, 10.0, "N/mm", "RR Spring Rate"),
    "rh_lf":        ParamBounds(20.0, 70.0, 1.0, "mm", "LF Ride Height"),
    "rh_rf":        ParamBounds(20.0, 70.0, 1.0, "mm", "RF Ride Height"),
    "rh_lr":        ParamBounds(30.0, 90.0, 1.0, "mm", "LR Ride Height"),
    "rh_rr":        ParamBounds(30.0, 90.0, 1.0, "mm", "RR Ride Height"),
    "wing_front":   ParamBounds(0, 20, 1, "step", "Front Wing"),
    "wing_rear":    ParamBounds(0, 20, 1, "step", "Rear Wing"),
    "diff_power":   ParamBounds(0, 60, 5, "deg", "Diff Power Ramp"),
    "diff_coast":   ParamBounds(0, 60, 5, "deg", "Diff Coast Ramp"),
}

_TCR: Dict[str, ParamBounds] = {
    **_GT3,
    "camber_lf":    ParamBounds(-4.0, -1.0, 0.1, "deg", "LF Camber"),
    "camber_rf":    ParamBounds(-4.0, -1.0, 0.1, "deg", "RF Camber"),
    "camber_lr":    ParamBounds(-2.5, -0.5, 0.1, "deg", "LR Camber"),
    "camber_rr":    ParamBounds(-2.5, -0.5, 0.1, "deg", "RR Camber"),
    "pressure_lf":  ParamBounds(28.0, 40.0, 0.1, "psi", "LF Cold Pressure"),
    "pressure_rf":  ParamBounds(28.0, 40.0, 0.1, "psi", "RF Cold Pressure"),
    "pressure_lr":  ParamBounds(26.0, 38.0, 0.1, "psi", "LR Cold Pressure"),
    "pressure_rr":  ParamBounds(26.0, 38.0, 0.1, "psi", "RR Cold Pressure"),
    "brake_bias":   ParamBounds(52.0, 68.0, 0.5, "%", "Brake Bias (front)"),
    "wing_front":   ParamBounds(0, 5, 1, "step", "Front Wing"),
    "wing_rear":    ParamBounds(0, 5, 1, "step", "Rear Wing"),
}

_PORSCHE_CUP: Dict[str, ParamBounds] = {
    **_GT3,
    "camber_lf":    ParamBounds(-4.5, -1.5, 0.1, "deg", "LF Camber"),
    "camber_rf":    ParamBounds(-4.5, -1.5, 0.1, "deg", "RF Camber"),
    "camber_lr":    ParamBounds(-3.0, -0.5, 0.1, "deg", "LR Camber"),
    "camber_rr":    ParamBounds(-3.0, -0.5, 0.1, "deg", "RR Camber"),
    # Cup cars typically have no adjustable aero wings
    "wing_front":   ParamBounds(0, 3, 1, "step", "Front Wing"),
    "wing_rear":    ParamBounds(0, 3, 1, "step", "Rear Wing"),
}

_STOCK: Dict[str, ParamBounds] = {
    "camber_lf":    ParamBounds(-5.0,  0.0, 0.1,  "deg",   "LF Camber"),
    "camber_rf":    ParamBounds(-5.0,  0.0, 0.1,  "deg",   "RF Camber"),
    "camber_lr":    ParamBounds(-3.0,  1.0, 0.1,  "deg",   "LR Camber"),
    "camber_rr":    ParamBounds(-3.0,  1.0, 0.1,  "deg",   "RR Camber"),
    "toe_front":    ParamBounds(-5.0,  5.0, 0.1,  "mm",    "Front Toe"),
    "toe_rear":     ParamBounds(-5.0,  5.0, 0.1,  "mm",    "Rear Toe"),
    "pressure_lf":  ParamBounds(28.0, 45.0, 0.5,  "psi",   "LF Cold Pressure"),
    "pressure_rf":  ParamBounds(28.0, 45.0, 0.5,  "psi",   "RF Cold Pressure"),
    "pressure_lr":  ParamBounds(28.0, 45.0, 0.5,  "psi",   "LR Cold Pressure"),
    "pressure_rr":  ParamBounds(28.0, 45.0, 0.5,  "psi",   "RR Cold Pressure"),
    "spring_lf":    ParamBounds(500.0, 2500.0, 50.0, "lb/in", "LF Spring Rate"),
    "spring_rf":    ParamBounds(500.0, 2500.0, 50.0, "lb/in", "RF Spring Rate"),
    "spring_lr":    ParamBounds(500.0, 2500.0, 50.0, "lb/in", "LR Spring Rate"),
    "spring_rr":    ParamBounds(500.0, 2500.0, 50.0, "lb/in", "RR Spring Rate"),
    "brake_bias":   ParamBounds(48.0, 62.0, 0.5,  "%",     "Brake Bias (front)"),
    "brake_pressure": ParamBounds(80.0, 110.0, 1.0, "%",   "Max Brake Pressure"),
    "rh_lf":        ParamBounds(100.0, 180.0, 1.0, "mm",   "LF Ride Height"),
    "rh_rf":        ParamBounds(100.0, 180.0, 1.0, "mm",   "RF Ride Height"),
    "rh_lr":        ParamBounds(110.0, 190.0, 1.0, "mm",   "LR Ride Height"),
    "rh_rr":        ParamBounds(110.0, 190.0, 1.0, "mm",   "RR Ride Height"),
    "tc_1":         ParamBounds(0, 9, 1, "level", "Traction Control"),
    "abs":          ParamBounds(0, 9, 1, "level", "ABS"),
}

_ROAD_ROOKIE: Dict[str, ParamBounds] = {
    **_GT3,
    "camber_lf":    ParamBounds(-3.5, -0.5, 0.1, "deg", "LF Camber"),
    "camber_rf":    ParamBounds(-3.5, -0.5, 0.1, "deg", "RF Camber"),
    "camber_lr":    ParamBounds(-2.5, -0.0, 0.1, "deg", "LR Camber"),
    "camber_rr":    ParamBounds(-2.5, -0.0, 0.1, "deg", "RR Camber"),
    "pressure_lf":  ParamBounds(26.0, 36.0, 0.5, "psi", "LF Cold Pressure"),
    "pressure_rf":  ParamBounds(26.0, 36.0, 0.5, "psi", "RF Cold Pressure"),
    "pressure_lr":  ParamBounds(25.0, 35.0, 0.5, "psi", "LR Cold Pressure"),
    "pressure_rr":  ParamBounds(25.0, 35.0, 0.5, "psi", "RR Cold Pressure"),
    "spring_lf":    ParamBounds(20.0, 120.0, 5.0, "N/mm", "LF Spring Rate"),
    "spring_rf":    ParamBounds(20.0, 120.0, 5.0, "N/mm", "RF Spring Rate"),
    "spring_lr":    ParamBounds(20.0, 120.0, 5.0, "N/mm", "LR Spring Rate"),
    "spring_rr":    ParamBounds(20.0, 120.0, 5.0, "N/mm", "RR Spring Rate"),
    "wing_front":   ParamBounds(0, 5, 1, "step", "Front Wing"),
    "wing_rear":    ParamBounds(0, 5, 1, "step", "Rear Wing"),
    "brake_bias":   ParamBounds(50.0, 62.0, 0.5, "%", "Brake Bias (front)"),
    "arb_front":    ParamBounds(1, 5, 1, "step", "Front ARB"),
    "arb_rear":     ParamBounds(1, 5, 1, "step", "Rear ARB"),
}

# ── Oval (NASCAR short track / intermediate / superspeedway) ──────────────────
_OVAL: Dict[str, ParamBounds] = {
    **_STOCK,
    # Oval-specific parameters
    "stagger":       ParamBounds(0.0,  4.0,  0.25,  "in",      "Stagger (R−L circumference)"),
    "wedge":         ParamBounds(48.0, 54.0, 0.5,   "%",       "Cross Weight (Wedge)"),
    "track_bar":     ParamBounds(1,    10,   1,      "clicks",  "Track Bar Height"),
    "shock_rf_bump": ParamBounds(1,    14,   1,      "clicks",  "RF Shock Bump"),
    "shock_lf_bump": ParamBounds(1,    14,   1,      "clicks",  "LF Shock Bump"),
    "shock_rr_bump": ParamBounds(1,    14,   1,      "clicks",  "RR Shock Bump"),
    "shock_lr_bump": ParamBounds(1,    14,   1,      "clicks",  "LR Shock Bump"),
    "front_tape":    ParamBounds(0,    10,   1,      "strips",  "Front Grill Tape"),
}

# ── Dirt Oval (late models, sprint cars, modifieds) ───────────────────────────
_DIRT_OVAL: Dict[str, ParamBounds] = {
    # Alignment
    "camber_lf":         ParamBounds(-5.0,  2.0,  0.1,  "deg",    "LF Camber"),
    "camber_rf":         ParamBounds(-5.0,  2.0,  0.1,  "deg",    "RF Camber"),
    "camber_lr":         ParamBounds(-4.0,  2.0,  0.1,  "deg",    "LR Camber"),
    "camber_rr":         ParamBounds(-4.0,  2.0,  0.1,  "deg",    "RR Camber"),
    "toe_front":         ParamBounds(-6.0,  6.0,  0.1,  "mm",     "Front Toe"),
    "toe_rear":          ParamBounds(-6.0,  6.0,  0.1,  "mm",     "Rear Toe"),
    # Tire pressures — dirt runs much lower pressures
    "pressure_lf":       ParamBounds(8.0,  22.0,  0.5,  "psi",    "LF Cold Pressure"),
    "pressure_rf":       ParamBounds(8.0,  22.0,  0.5,  "psi",    "RF Cold Pressure"),
    "pressure_lr":       ParamBounds(8.0,  22.0,  0.5,  "psi",    "LR Cold Pressure"),
    "pressure_rr":       ParamBounds(8.0,  22.0,  0.5,  "psi",    "RR Cold Pressure"),
    # Springs
    "spring_lf":         ParamBounds(100.0, 1200.0, 50.0, "lb/in", "LF Spring Rate"),
    "spring_rf":         ParamBounds(100.0, 1200.0, 50.0, "lb/in", "RF Spring Rate"),
    "spring_lr":         ParamBounds(100.0, 1200.0, 50.0, "lb/in", "LR Spring Rate"),
    "spring_rr":         ParamBounds(100.0, 1200.0, 50.0, "lb/in", "RR Spring Rate"),
    # Dirt-specific
    "bite_bar":          ParamBounds(0,    10,    1,     "notches", "Bite Bar"),
    "wedge":             ParamBounds(48.0, 56.0,  0.5,   "%",       "Cross Weight (Wedge)"),
    "nose_weight":       ParamBounds(0.0,  50.0,  1.0,   "lb",      "Nose Weight"),
    "wing_angle":        ParamBounds(0.0,  30.0,  1.0,   "deg",     "Rear Wing Angle"),
    "shock_compression": ParamBounds(1,    14,    1,     "clicks",  "Shock Compression"),
    # Brakes
    "brake_bias":        ParamBounds(50.0, 70.0,  0.5,   "%",       "Brake Bias (front)"),
    "brake_pressure":    ParamBounds(80.0, 110.0, 1.0,   "%",       "Max Brake Pressure"),
}

# Map CarClass → bounds dict
BOUNDS: Dict[CarClass, Dict[str, ParamBounds]] = {
    CarClass.GT3:          _GT3,
    CarClass.GT4:          _GT4,
    CarClass.GTP:          _GTP,
    CarClass.GTE:          _GTP,       # GTE shares GTP bounds closely
    CarClass.LMP2:         _LMP2,
    CarClass.PROTOTYPE:    _LMP2,
    CarClass.FORMULA:      _FORMULA,
    CarClass.SUPER_FORMULA: _FORMULA,
    CarClass.PORSCHE_CUP:  _PORSCHE_CUP,
    CarClass.TCR:          _TCR,
    CarClass.V8_SUPERCAR:  _STOCK,
    CarClass.STOCK:        _OVAL,
    CarClass.ROAD_ROOKIE:  _ROAD_ROOKIE,
    CarClass.SPORTS_CAR:   _GT4,
    CarClass.RALLY_CROSS:  _ROAD_ROOKIE,
    CarClass.DIRT_OVAL:    _DIRT_OVAL,
    CarClass.DEFAULT:      _GT3,
}


# ── Public API ─────────────────────────────────────────────────────────────────

def _resolve_car_class(car_class) -> CarClass:
    """Normalize a string or CarClass enum to a CarClass enum."""
    if isinstance(car_class, CarClass):
        return car_class
    s = str(car_class).lower().replace(" ", "_")
    for member in CarClass:
        if member.value.lower() == s or member.name.lower() == s:
            return member
    return CarClass.DEFAULT


def get_bounds(car_class) -> Dict[str, ParamBounds]:
    """Return the parameter bounds dict for a car class."""
    return BOUNDS.get(_resolve_car_class(car_class), _GT3)


def validate_setup(
    setup_values: Dict[str, float],
    car_class,
) -> List[TechIssue]:
    """
    Check every key in *setup_values* against the legal range for *car_class*.

    Returns a list of TechIssue objects — one per out-of-range parameter.
    An empty list means the setup passes tech inspection for these parameters.

    Parameters
    ----------
    setup_values : dict
        Keys are internal param names (e.g. 'camber_lf', 'brake_bias').
        Values are floats in the parameter's natural unit.
    car_class : CarClass or str
        Used to look up legal ranges.
    """
    bounds = get_bounds(_resolve_car_class(car_class))
    issues: List[TechIssue] = []

    for key, value in setup_values.items():
        if key not in bounds:
            continue
        b = bounds[key]
        if not b.is_legal(value):
            issues.append(TechIssue(
                param=key,
                display_name=b.display_name or key,
                value=value,
                min_val=b.min_val,
                max_val=b.max_val,
                unit=b.unit,
                clamped_value=b.clamp(value),
            ))

    return issues


def clamp_to_legal(
    setup_values: Dict[str, float],
    car_class,
) -> Dict[str, float]:
    """
    Return a new dict with every parameter clamped to its legal range.
    Parameters not in the bounds table are passed through unchanged.
    """
    bounds = get_bounds(_resolve_car_class(car_class))
    result: Dict[str, float] = {}
    for key, value in setup_values.items():
        if key in bounds:
            result[key] = bounds[key].clamp(value)
        else:
            result[key] = value
    return result


def bounds_summary_for_prompt(car_class) -> str:
    """
    Return a compact plain-text summary of all legal ranges for a car class.
    Intended to be included in an AI prompt so Claude knows what values are legal.
    """
    resolved = _resolve_car_class(car_class)
    bounds = get_bounds(resolved)
    lines = [f"Legal parameter ranges for {resolved.value.upper()}:"]
    for key, b in bounds.items():
        name = b.display_name or key
        lines.append(
            f"  {name}: {b.min_val:.3g}–{b.max_val:.3g} {b.unit} "
            f"(step {b.step:.3g})"
        )
    return "\n".join(lines)


# ── Parameter name normalisation ───────────────────────────────────────────────
#
# Claude outputs human-readable names like "LF Camber", "Front ARB", "Brake Bias".
# Our bounds dict uses snake_case internal keys like "camber_lf", "arb_front".
# This table maps every reasonable Claude output variant → internal key.
#
# Keys are lowercased + whitespace-collapsed before lookup.
_CLAUDE_NAME_MAP: Dict[str, str] = {
    # ── Camber ────────────────────────────────────────────────────────────────
    "lf camber":                "camber_lf",
    "rf camber":                "camber_rf",
    "lr camber":                "camber_lr",
    "rr camber":                "camber_rr",
    "left front camber":        "camber_lf",
    "right front camber":       "camber_rf",
    "left rear camber":         "camber_lr",
    "right rear camber":        "camber_rr",
    "camber lf":                "camber_lf",
    "camber rf":                "camber_rf",
    "camber lr":                "camber_lr",
    "camber rr":                "camber_rr",
    # ── Toe ───────────────────────────────────────────────────────────────────
    "front toe":                "toe_front",
    "rear toe":                 "toe_rear",
    "toe front":                "toe_front",
    "toe rear":                 "toe_rear",
    "front toe in":             "toe_front",
    "rear toe in":              "toe_rear",
    # ── Tire pressures ────────────────────────────────────────────────────────
    "lf cold pressure":         "pressure_lf",
    "rf cold pressure":         "pressure_rf",
    "lr cold pressure":         "pressure_lr",
    "rr cold pressure":         "pressure_rr",
    "lf pressure":              "pressure_lf",
    "rf pressure":              "pressure_rf",
    "lr pressure":              "pressure_lr",
    "rr pressure":              "pressure_rr",
    "left front cold pressure": "pressure_lf",
    "right front cold pressure":"pressure_rf",
    "left rear cold pressure":  "pressure_lr",
    "right rear cold pressure": "pressure_rr",
    "left front pressure":      "pressure_lf",
    "right front pressure":     "pressure_rf",
    "left rear pressure":       "pressure_lr",
    "right rear pressure":      "pressure_rr",
    "lf starting pressure":     "pressure_lf",
    "rf starting pressure":     "pressure_rf",
    "lr starting pressure":     "pressure_lr",
    "rr starting pressure":     "pressure_rr",
    # ── Springs ───────────────────────────────────────────────────────────────
    "lf spring":                "spring_lf",
    "rf spring":                "spring_rf",
    "lr spring":                "spring_lr",
    "rr spring":                "spring_rr",
    "lf spring rate":           "spring_lf",
    "rf spring rate":           "spring_rf",
    "lr spring rate":           "spring_lr",
    "rr spring rate":           "spring_rr",
    "left front spring":        "spring_lf",
    "right front spring":       "spring_rf",
    "left rear spring":         "spring_lr",
    "right rear spring":        "spring_rr",
    "spring lf":                "spring_lf",
    "spring rf":                "spring_rf",
    "spring lr":                "spring_lr",
    "spring rr":                "spring_rr",
    # ── ARBs ──────────────────────────────────────────────────────────────────
    "front arb":                "arb_front",
    "rear arb":                 "arb_rear",
    "arb front":                "arb_front",
    "arb rear":                 "arb_rear",
    "front anti-roll bar":      "arb_front",
    "rear anti-roll bar":       "arb_rear",
    "front sway bar":           "arb_front",
    "rear sway bar":            "arb_rear",
    "front stabilizer bar":     "arb_front",
    "rear stabilizer bar":      "arb_rear",
    # ── Ride heights ──────────────────────────────────────────────────────────
    "lf ride height":           "rh_lf",
    "rf ride height":           "rh_rf",
    "lr ride height":           "rh_lr",
    "rr ride height":           "rh_rr",
    "ride height lf":           "rh_lf",
    "ride height rf":           "rh_rf",
    "ride height lr":           "rh_lr",
    "ride height rr":           "rh_rr",
    "left front ride height":   "rh_lf",
    "right front ride height":  "rh_rf",
    "left rear ride height":    "rh_lr",
    "right rear ride height":   "rh_rr",
    # ── Slow bump dampers ─────────────────────────────────────────────────────
    "lf slow bump":             "bump_slow_lf",
    "rf slow bump":             "bump_slow_rf",
    "lr slow bump":             "bump_slow_lr",
    "rr slow bump":             "bump_slow_rr",
    "lf bump slow":             "bump_slow_lf",
    "rf bump slow":             "bump_slow_rf",
    "lr bump slow":             "bump_slow_lr",
    "rr bump slow":             "bump_slow_rr",
    "left front slow bump":     "bump_slow_lf",
    "right front slow bump":    "bump_slow_rf",
    "left rear slow bump":      "bump_slow_lr",
    "right rear slow bump":     "bump_slow_rr",
    # ── Fast bump dampers ─────────────────────────────────────────────────────
    "lf fast bump":             "bump_fast_lf",
    "rf fast bump":             "bump_fast_rf",
    "lr fast bump":             "bump_fast_lr",
    "rr fast bump":             "bump_fast_rr",
    "lf bump fast":             "bump_fast_lf",
    "rf bump fast":             "bump_fast_rf",
    "lr bump fast":             "bump_fast_lr",
    "rr bump fast":             "bump_fast_rr",
    # ── Slow rebound dampers ──────────────────────────────────────────────────
    "lf slow rebound":          "rebound_slow_lf",
    "rf slow rebound":          "rebound_slow_rf",
    "lr slow rebound":          "rebound_slow_lr",
    "rr slow rebound":          "rebound_slow_rr",
    "lf rebound slow":          "rebound_slow_lf",
    "rf rebound slow":          "rebound_slow_rf",
    "lr rebound slow":          "rebound_slow_lr",
    "rr rebound slow":          "rebound_slow_rr",
    "left front slow rebound":  "rebound_slow_lf",
    "right front slow rebound": "rebound_slow_rf",
    "left rear slow rebound":   "rebound_slow_lr",
    "right rear slow rebound":  "rebound_slow_rr",
    # ── Fast rebound dampers ──────────────────────────────────────────────────
    "lf fast rebound":          "rebound_fast_lf",
    "rf fast rebound":          "rebound_fast_rf",
    "lr fast rebound":          "rebound_fast_lr",
    "rr fast rebound":          "rebound_fast_rr",
    "lf rebound fast":          "rebound_fast_lf",
    "rf rebound fast":          "rebound_fast_rf",
    "lr rebound fast":          "rebound_fast_lr",
    "rr rebound fast":          "rebound_fast_rr",
    # ── Wings / Aero ──────────────────────────────────────────────────────────
    "front wing":               "wing_front",
    "rear wing":                "wing_rear",
    "wing front":               "wing_front",
    "wing rear":                "wing_rear",
    "front wing angle":         "wing_front",
    "rear wing angle":          "wing_rear",
    "front downforce":          "wing_front",
    "rear downforce":           "wing_rear",
    "front brake duct":         "brake_duct_front",
    "rear brake duct":          "brake_duct_rear",
    "brake duct front":         "brake_duct_front",
    "brake duct rear":          "brake_duct_rear",
    # ── Brakes ────────────────────────────────────────────────────────────────
    "brake bias":               "brake_bias",
    "brake balance":            "brake_bias",
    "front brake bias":         "brake_bias",
    "brake pressure bias":      "brake_bias",
    "brake pressure":           "brake_pressure",
    "max brake pressure":       "brake_pressure",
    "brake force":              "brake_pressure",
    # ── Electronics ───────────────────────────────────────────────────────────
    "tc":                       "tc_1",
    "tc1":                      "tc_1",
    "tc 1":                     "tc_1",
    "traction control":         "tc_1",
    "traction control 1":       "tc_1",
    "tc2":                      "tc_2",
    "tc 2":                     "tc_2",
    "traction control 2":       "tc_2",
    "abs":                      "abs",
    "abs setting":              "abs",
    # ── Differential ──────────────────────────────────────────────────────────
    "diff preload":             "diff_preload",
    "differential preload":     "diff_preload",
    "preload":                  "diff_preload",
    "diff power ramp":          "diff_power",
    "power ramp":               "diff_power",
    "diff coast ramp":          "diff_coast",
    "coast ramp":               "diff_coast",
    "diff power":               "diff_power",
    "diff coast":               "diff_coast",

    # ── Oval parameters ───────────────────────────────────────────────────
    "stagger":                  "stagger",
    "tire stagger":             "stagger",
    "wedge":                    "wedge",
    "cross weight":             "wedge",
    "cross weight %":           "wedge",
    "track bar":                "track_bar",
    "track bar height":         "track_bar",
    "panhard bar":              "track_bar",
    "panhard bar height":       "track_bar",
    "watts link":               "track_bar",
    "rf shock bump":            "shock_rf_bump",
    "rf bump":                  "shock_rf_bump",
    "right front bump":         "shock_rf_bump",
    "lf shock bump":            "shock_lf_bump",
    "lf bump":                  "shock_lf_bump",
    "left front bump":          "shock_lf_bump",
    "rr shock bump":            "shock_rr_bump",
    "lr shock bump":            "shock_lr_bump",
    "front tape":               "front_tape",
    "grill tape":               "front_tape",
    "tape":                     "front_tape",

    # ── Dirt parameters ───────────────────────────────────────────────────
    "bite bar":                 "bite_bar",
    "bite":                     "bite_bar",
    "wing angle":               "wing_angle",
    "rear wing angle":          "wing_angle",
    "dirt wing":                "wing_angle",
    "shock compression":        "shock_compression",
    "compression":              "shock_compression",
    "nose weight":              "nose_weight",
    "front nose weight":        "nose_weight",
}


def normalize_param_key(raw_name: str) -> Optional[str]:
    """
    Map a human-readable parameter name (as output by Claude) to the internal
    bounds key used in tech_inspector.  Returns None if no mapping found.

    Matching is case-insensitive and whitespace-collapsed.
    """
    key = " ".join(raw_name.lower().strip().split())
    # Direct lookup first
    if key in _CLAUDE_NAME_MAP:
        return _CLAUDE_NAME_MAP[key]
    # Try stripping common trailing words that Claude sometimes appends
    for suffix in (" setting", " rate", " angle", " level", " (front)", " (rear)"):
        if key.endswith(suffix):
            trimmed = key[: -len(suffix)].strip()
            if trimmed in _CLAUDE_NAME_MAP:
                return _CLAUDE_NAME_MAP[trimmed]
    return None


def tech_fail_reasons() -> List[str]:
    """
    Return a human-readable list of common reasons setups fail tech inspection,
    for display in the UI tooltip or info panel.
    """
    return [
        "Value outside legal range — iRacing enforces hard min/max limits per car. "
        "Any parameter beyond the garage slider's endpoint triggers an immediate fail.",

        "Wrong step increment — some parameters must be set in specific increments "
        "(e.g. 0.5 psi, 1 click). A value that falls between steps is rejected.",

        "Series-mandated fixed values — some parameters (e.g. wing angle in BoP "
        "series like IMSA GTP) may be locked by the series rules and cannot be "
        "changed at all; any non-default value fails tech.",

        "Restricted parameters — multi-class races or fixed-setup events may lock "
        "certain sections (diff, TC, ABS) regardless of the car's normal range.",

        "Mismatched car/track config — loading a setup saved for a different track "
        "layout or car skin can carry over values that are out-of-range on the "
        "current variant.",
    ]
