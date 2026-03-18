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
    CarClass.STOCK:        _STOCK,
    CarClass.ROAD_ROOKIE:  _ROAD_ROOKIE,
    CarClass.SPORTS_CAR:   _GT4,
    CarClass.RALLY_CROSS:  _ROAD_ROOKIE,
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
