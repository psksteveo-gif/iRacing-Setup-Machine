"""
Setup Change Impact Predictor — Physics-based prediction of setup change effects.
Estimates sector time, balance, tire wear impact from adjustments.
"""

import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


@dataclass
class ImpactPrediction:
    """Predicted effect of a single setup change."""
    change_description: str          # e.g. "+1 click rear wing"
    parameter: str                   # internal key
    direction: str                   # "increase" or "decrease"
    magnitude: float                 # how many clicks/turns/psi
    # Predicted effects
    lap_time_delta_s: float          # + = slower, - = faster
    straight_speed_delta_kmh: float
    corner_speed_delta_kmh: float
    balance_shift: str               # "more oversteer" / "more understeer" / "neutral"
    tire_wear_impact: str            # "increased" / "decreased" / "minimal"
    confidence: float                # 0–1 confidence in prediction
    explanation: str                 # human-readable reasoning


@dataclass
class ImpactReport:
    """Full impact analysis for one or more setup changes."""
    predictions: List[ImpactPrediction]
    net_lap_time_delta_s: float
    net_balance_shift: str
    summary: str


# Physics models: parameter → effect coefficients
# Each entry: (lap_time_per_unit, straight_speed_per_unit, corner_speed_per_unit,
#              balance_direction, tire_wear_direction)
# Units: seconds, km/h, km/h per 1 unit of change
_EFFECT_MODELS: Dict[str, Dict] = {
    "rear_wing": {
        "lap_time_per_click": 0.05,    # higher wing = slower straights but faster corners
        "straight_speed": -1.5,         # km/h lost per click
        "corner_speed": 0.8,            # km/h gained per click
        "balance": "understeer",        # more rear wing → more rear grip → understeer
        "tire_wear": "decreased",       # more aero load → more even wear
        "confidence": 0.7,
    },
    "front_wing": {
        "lap_time_per_click": 0.03,
        "straight_speed": -0.8,
        "corner_speed": 0.5,
        "balance": "oversteer",         # more front wing → more front grip → oversteer
        "tire_wear": "minimal",
        "confidence": 0.7,
    },
    "rear_spring": {
        "lap_time_per_click": 0.02,
        "straight_speed": 0.0,
        "corner_speed": -0.3,
        "balance": "oversteer",         # stiffer rear → less rear grip → oversteer
        "tire_wear": "increased",
        "confidence": 0.5,
    },
    "front_spring": {
        "lap_time_per_click": 0.02,
        "straight_speed": 0.0,
        "corner_speed": -0.3,
        "balance": "understeer",        # stiffer front → less front grip → understeer
        "tire_wear": "increased",
        "confidence": 0.5,
    },
    "rear_arb": {
        "lap_time_per_click": 0.015,
        "straight_speed": 0.0,
        "corner_speed": 0.2,
        "balance": "oversteer",         # stiffer rear ARB → oversteer
        "tire_wear": "minimal",
        "confidence": 0.6,
    },
    "front_arb": {
        "lap_time_per_click": 0.015,
        "straight_speed": 0.0,
        "corner_speed": 0.2,
        "balance": "understeer",
        "tire_wear": "minimal",
        "confidence": 0.6,
    },
    "tire_pressure": {
        "lap_time_per_click": 0.04,     # per 0.5 PSI
        "straight_speed": 0.1,
        "corner_speed": -0.5,
        "balance": "neutral",
        "tire_wear": "increased",       # over-inflated wears center more
        "confidence": 0.65,
    },
    "ride_height_rear": {
        "lap_time_per_click": 0.03,
        "straight_speed": -0.5,         # higher → more drag
        "corner_speed": 0.3,
        "balance": "understeer",
        "tire_wear": "minimal",
        "confidence": 0.5,
    },
    "ride_height_front": {
        "lap_time_per_click": 0.03,
        "straight_speed": -0.3,
        "corner_speed": 0.2,
        "balance": "oversteer",
        "tire_wear": "minimal",
        "confidence": 0.5,
    },
    "brake_bias": {
        "lap_time_per_click": 0.01,     # per 0.5% shift
        "straight_speed": 0.0,
        "corner_speed": 0.0,
        "balance": "understeer",        # more front bias → understeer on entry
        "tire_wear": "minimal",
        "confidence": 0.75,
    },
    "tc_level": {
        "lap_time_per_click": 0.08,     # per TC level
        "straight_speed": -0.5,
        "corner_speed": 0.0,
        "balance": "neutral",
        "tire_wear": "decreased",
        "confidence": 0.8,
    },
    "abs_level": {
        "lap_time_per_click": 0.05,
        "straight_speed": 0.0,
        "corner_speed": 0.0,
        "balance": "neutral",
        "tire_wear": "decreased",
        "confidence": 0.8,
    },

    # ── Oval-specific parameters ───────────────────────────────────────────
    "stagger": {
        "lap_time_per_click": 0.05,    # per 0.25" of stagger
        "straight_speed": 0.0,
        "corner_speed": 0.6,           # more stagger = faster through left turns
        "balance": "oversteer",        # more stagger = more rotation in left turns
        "tire_wear": "increased",      # asymmetric circumference = uneven wear
        "confidence": 0.75,
    },
    "wedge": {
        "lap_time_per_click": 0.03,    # per 0.5% cross weight
        "straight_speed": 0.0,
        "corner_speed": -0.3,
        "balance": "understeer",       # more wedge (cross weight) = tight = understeer
        "tire_wear": "minimal",
        "confidence": 0.70,
    },
    "track_bar": {
        "lap_time_per_click": 0.04,    # per click height adjustment
        "straight_speed": 0.0,
        "corner_speed": 0.4,
        "balance": "oversteer",        # raising track bar = higher roll centre = looser
        "tire_wear": "minimal",
        "confidence": 0.70,
    },
    "shock_rf_bump": {
        "lap_time_per_click": 0.015,
        "straight_speed": 0.0,
        "corner_speed": 0.2,
        "balance": "understeer",       # stiffer RF bump = more RF load = tighter
        "tire_wear": "minimal",
        "confidence": 0.55,
    },
    "shock_lf_bump": {
        "lap_time_per_click": 0.015,
        "straight_speed": 0.0,
        "corner_speed": 0.2,
        "balance": "oversteer",        # stiffer LF bump = less LF load = looser
        "tire_wear": "minimal",
        "confidence": 0.55,
    },
    "front_tape": {
        "lap_time_per_click": 0.04,    # per strip of grill tape (reduces cooling drag)
        "straight_speed": 0.8,
        "corner_speed": -0.05,
        "balance": "neutral",
        "tire_wear": "minimal",
        "confidence": 0.65,
    },

    # ── Dirt-specific parameters ───────────────────────────────────────────
    "bite_bar": {
        "lap_time_per_click": 0.04,    # per notch of bite bar
        "straight_speed": 0.0,
        "corner_speed": -0.3,
        "balance": "understeer",       # more bite = tight = understeer
        "tire_wear": "minimal",
        "confidence": 0.65,
    },
    "wing_angle": {
        "lap_time_per_click": 0.03,    # per degree of wing angle
        "straight_speed": -0.5,
        "corner_speed": 0.4,
        "balance": "understeer",       # more rear wing = more rear grip = understeer
        "tire_wear": "decreased",
        "confidence": 0.65,
    },
    "shock_compression": {
        "lap_time_per_click": 0.02,    # per click
        "straight_speed": 0.0,
        "corner_speed": -0.25,
        "balance": "neutral",
        "tire_wear": "increased",      # stiffer = less conformity over bumps/dirt
        "confidence": 0.55,
    },
    "nose_weight": {
        "lap_time_per_click": 0.03,    # per lb of nose weight
        "straight_speed": 0.0,
        "corner_speed": 0.3,
        "balance": "oversteer",        # more nose weight = more front grip = rotation
        "tire_wear": "minimal",
        "confidence": 0.60,
    },
}


# ── Car-class-specific physics overrides ────────────────────────────────────
# Each entry overrides one or more fields in _EFFECT_MODELS for a specific class.
# Multipliers are applied to lap_time_per_click, corner_speed, straight_speed.
# confidence overrides the flat confidence value.
#
# Sources: iRacing physics community data, telemetry analysis, lap-time sensitivity
# studies from GT3/GTP/Formula class communities.
_CLASS_MODELS: Dict[str, Dict[str, Dict[str, Any]]] = {
    # ── GT3 ─────────────────────────────────────────────────────────────────
    "gt3": {
        # Base models are calibrated for GT3 — no changes needed
    },
    # ── GT4 ─────────────────────────────────────────────────────────────────
    "gt4": {
        # Lower downforce, more mechanically-dependent than GT3
        "rear_wing":       {"lap_time_per_click": 0.03,  "corner_speed": 0.5,  "straight_speed": -1.0, "confidence": 0.65},
        "front_wing":      {"lap_time_per_click": 0.02,  "corner_speed": 0.3,  "straight_speed": -0.5, "confidence": 0.65},
        "rear_arb":        {"lap_time_per_click": 0.02,  "corner_speed": 0.25, "confidence": 0.65},
        "front_arb":       {"lap_time_per_click": 0.02,  "corner_speed": 0.25, "confidence": 0.65},
        "tire_pressure":   {"lap_time_per_click": 0.05,  "confidence": 0.70},   # GT4 tires very sensitive
        "rear_spring":     {"lap_time_per_click": 0.025, "confidence": 0.55},
        "front_spring":    {"lap_time_per_click": 0.025, "confidence": 0.55},
    },
    # ── GTP ─────────────────────────────────────────────────────────────────
    "gtp": {
        # Massive downforce — wing changes have huge effect; very stiff cars
        "rear_wing":       {"lap_time_per_click": 0.10,  "corner_speed": 1.8,  "straight_speed": -2.5, "confidence": 0.80},
        "front_wing":      {"lap_time_per_click": 0.07,  "corner_speed": 1.2,  "straight_speed": -1.5, "confidence": 0.80},
        "rear_spring":     {"lap_time_per_click": 0.015, "corner_speed": -0.4, "confidence": 0.60},
        "front_spring":    {"lap_time_per_click": 0.015, "corner_speed": -0.4, "confidence": 0.60},
        "rear_arb":        {"lap_time_per_click": 0.02,  "corner_speed": 0.3,  "confidence": 0.65},
        "front_arb":       {"lap_time_per_click": 0.02,  "corner_speed": 0.3,  "confidence": 0.65},
        "ride_height_rear":{"lap_time_per_click": 0.06,  "corner_speed": 0.6,  "straight_speed": -1.0, "confidence": 0.70},
        "ride_height_front":{"lap_time_per_click": 0.05, "corner_speed": 0.5,  "straight_speed": -0.8, "confidence": 0.70},
        "tire_pressure":   {"lap_time_per_click": 0.05,  "confidence": 0.70},
    },
    # ── LMP2 ────────────────────────────────────────────────────────────────
    "lmp2": {
        "rear_wing":       {"lap_time_per_click": 0.08,  "corner_speed": 1.4,  "straight_speed": -2.0, "confidence": 0.75},
        "front_wing":      {"lap_time_per_click": 0.05,  "corner_speed": 0.9,  "straight_speed": -1.2, "confidence": 0.75},
        "rear_spring":     {"lap_time_per_click": 0.015, "confidence": 0.55},
        "front_spring":    {"lap_time_per_click": 0.015, "confidence": 0.55},
        "ride_height_rear":{"lap_time_per_click": 0.05,  "corner_speed": 0.5,  "confidence": 0.65},
        "ride_height_front":{"lap_time_per_click": 0.04, "corner_speed": 0.4,  "confidence": 0.65},
        "tire_pressure":   {"lap_time_per_click": 0.05,  "confidence": 0.70},
    },
    # ── GTE ─────────────────────────────────────────────────────────────────
    "gte": {
        # Similar to GT3 but slightly more downforce-sensitive
        "rear_wing":       {"lap_time_per_click": 0.06,  "corner_speed": 0.9,  "straight_speed": -1.7, "confidence": 0.72},
        "front_wing":      {"lap_time_per_click": 0.04,  "corner_speed": 0.6,  "straight_speed": -0.9, "confidence": 0.72},
        "tire_pressure":   {"lap_time_per_click": 0.045, "confidence": 0.68},
    },
    # ── Formula / Open Wheel ─────────────────────────────────────────────────
    "formula": {
        # Extreme downforce sensitivity; 1 wing step = major lap time swing
        "rear_wing":       {"lap_time_per_click": 0.12,  "corner_speed": 2.2,  "straight_speed": -3.0, "confidence": 0.85},
        "front_wing":      {"lap_time_per_click": 0.09,  "corner_speed": 1.8,  "straight_speed": -2.0, "confidence": 0.85},
        "rear_spring":     {"lap_time_per_click": 0.03,  "corner_speed": -0.5, "confidence": 0.65},
        "front_spring":    {"lap_time_per_click": 0.03,  "corner_speed": -0.5, "confidence": 0.65},
        "rear_arb":        {"lap_time_per_click": 0.025, "corner_speed": 0.35, "confidence": 0.70},
        "front_arb":       {"lap_time_per_click": 0.025, "corner_speed": 0.35, "confidence": 0.70},
        "ride_height_rear":{"lap_time_per_click": 0.07,  "corner_speed": 0.8,  "straight_speed": -1.2, "confidence": 0.75},
        "ride_height_front":{"lap_time_per_click": 0.06, "corner_speed": 0.7,  "straight_speed": -1.0, "confidence": 0.75},
        "tire_pressure":   {"lap_time_per_click": 0.06,  "confidence": 0.75},
        "brake_bias":      {"lap_time_per_click": 0.015, "confidence": 0.80},
        "tc_level":        {"lap_time_per_click": 0.10,  "confidence": 0.85},
    },
    # ── Porsche Cup (one-make, minimal adjustment range) ────────────────────
    "porsche_cup": {
        # No wing adjustment — suspension and tire pressure dominate
        "rear_wing":       {"lap_time_per_click": 0.0,   "corner_speed": 0.0, "straight_speed": 0.0, "confidence": 0.1},  # fixed
        "front_wing":      {"lap_time_per_click": 0.0,   "corner_speed": 0.0, "straight_speed": 0.0, "confidence": 0.1},  # fixed
        "rear_arb":        {"lap_time_per_click": 0.025, "corner_speed": 0.3, "confidence": 0.75},   # very sensitive
        "front_arb":       {"lap_time_per_click": 0.025, "corner_speed": 0.3, "confidence": 0.75},
        "tire_pressure":   {"lap_time_per_click": 0.06,  "confidence": 0.80},  # critical in Porsche
        "rear_spring":     {"lap_time_per_click": 0.03,  "confidence": 0.70},
        "front_spring":    {"lap_time_per_click": 0.03,  "confidence": 0.70},
        "brake_bias":      {"lap_time_per_click": 0.012, "confidence": 0.80},
    },
    # ── TCR (FWD touring car) ────────────────────────────────────────────────
    "tcr": {
        # FWD — front-heavy sensitivity; no rear wing
        "rear_wing":       {"lap_time_per_click": 0.0,   "corner_speed": 0.0, "straight_speed": 0.0, "confidence": 0.1},  # none
        "front_wing":      {"lap_time_per_click": 0.02,  "corner_speed": 0.3, "straight_speed": -0.4, "confidence": 0.60},
        "front_arb":       {"lap_time_per_click": 0.03,  "corner_speed": 0.4, "confidence": 0.75},   # primary balance tool FWD
        "rear_arb":        {"lap_time_per_click": 0.02,  "corner_speed": 0.3, "confidence": 0.70},
        "tire_pressure":   {"lap_time_per_click": 0.07,  "confidence": 0.80},  # FWD tires work very hard
        "front_spring":    {"lap_time_per_click": 0.04,  "confidence": 0.70},  # more sensitive FWD
        "rear_spring":     {"lap_time_per_click": 0.02,  "confidence": 0.60},
        "tc_level":        {"lap_time_per_click": 0.06,  "confidence": 0.80},
        "brake_bias":      {"lap_time_per_click": 0.02,  "confidence": 0.80},  # critical — FWD braking
    },
    # ── Stock Car (NASCAR-style oval/road, no aero wings) ───────────────────
    "stock": {
        "rear_wing":       {"lap_time_per_click": 0.0,  "corner_speed": 0.0, "straight_speed": 0.0, "confidence": 0.1},
        "front_wing":      {"lap_time_per_click": 0.0,  "corner_speed": 0.0, "straight_speed": 0.0, "confidence": 0.1},
        "rear_spring":     {"lap_time_per_click": 0.04, "corner_speed": -0.5, "confidence": 0.65},   # stiffer → less bite
        "front_spring":    {"lap_time_per_click": 0.04, "corner_speed": -0.5, "confidence": 0.65},
        "rear_arb":        {"lap_time_per_click": 0.03, "corner_speed": 0.4,  "confidence": 0.70},
        "front_arb":       {"lap_time_per_click": 0.03, "corner_speed": 0.4,  "confidence": 0.70},
        "tire_pressure":   {"lap_time_per_click": 0.08, "confidence": 0.80},  # oval tire sensitivity is high
        "brake_bias":      {"lap_time_per_click": 0.015,"confidence": 0.80},
        "tc_level":        {"lap_time_per_click": 0.05, "confidence": 0.75},
    },
    # ── Road Rookie / Sports Car (entry-level) ───────────────────────────────
    "road_rookie": {
        "rear_wing":       {"lap_time_per_click": 0.02,  "corner_speed": 0.3,  "straight_speed": -0.6, "confidence": 0.55},
        "front_wing":      {"lap_time_per_click": 0.015, "corner_speed": 0.2,  "straight_speed": -0.4, "confidence": 0.55},
        "tire_pressure":   {"lap_time_per_click": 0.035, "confidence": 0.65},
        "rear_arb":        {"lap_time_per_click": 0.012, "confidence": 0.55},
        "front_arb":       {"lap_time_per_click": 0.012, "confidence": 0.55},
    },

    # ── Oval (short track / intermediate) ────────────────────────────────────
    "oval": {
        # Oval-specific params are more sensitive
        "stagger":       {"lap_time_per_click": 0.06,  "confidence": 0.80},
        "wedge":         {"lap_time_per_click": 0.04,  "confidence": 0.75},
        "track_bar":     {"lap_time_per_click": 0.05,  "confidence": 0.75},
        "shock_rf_bump": {"lap_time_per_click": 0.02,  "confidence": 0.60},
        "shock_lf_bump": {"lap_time_per_click": 0.02,  "confidence": 0.60},
        "front_tape":    {"lap_time_per_click": 0.06,  "confidence": 0.70},
        "tire_pressure": {"lap_time_per_click": 0.08,  "confidence": 0.80},
        "rear_spring":   {"lap_time_per_click": 0.04,  "confidence": 0.65},
        "front_spring":  {"lap_time_per_click": 0.04,  "confidence": 0.65},
        "brake_bias":    {"lap_time_per_click": 0.012, "confidence": 0.75},
        # No traditional wings
        "rear_wing":     {"lap_time_per_click": 0.0, "corner_speed": 0.0, "straight_speed": 0.0, "confidence": 0.05},
        "front_wing":    {"lap_time_per_click": 0.0, "corner_speed": 0.0, "straight_speed": 0.0, "confidence": 0.05},
    },

    # ── Superspeedway (Daytona / Talladega style) ─────────────────────────────
    "superspeedway": {
        "stagger":       {"lap_time_per_click": 0.08,  "confidence": 0.80},
        "wedge":         {"lap_time_per_click": 0.05,  "confidence": 0.75},
        "front_tape":    {"lap_time_per_click": 0.10,  "confidence": 0.80},  # tape critical at high speed
        "tire_pressure": {"lap_time_per_click": 0.06,  "confidence": 0.75},
        "track_bar":     {"lap_time_per_click": 0.04,  "confidence": 0.70},
        "rear_wing":     {"lap_time_per_click": 0.0, "corner_speed": 0.0, "straight_speed": 0.0, "confidence": 0.05},
        "front_wing":    {"lap_time_per_click": 0.0, "corner_speed": 0.0, "straight_speed": 0.0, "confidence": 0.05},
    },

    # ── Dirt Oval (late models, sprint cars, modifieds) ───────────────────────
    "dirt_oval": {
        "bite_bar":          {"lap_time_per_click": 0.05,  "confidence": 0.70},
        "nose_weight":       {"lap_time_per_click": 0.04,  "confidence": 0.65},
        "wing_angle":        {"lap_time_per_click": 0.04,  "confidence": 0.70},
        "shock_compression": {"lap_time_per_click": 0.025, "confidence": 0.60},
        "tire_pressure":     {"lap_time_per_click": 0.07,  "confidence": 0.75},
        "rear_spring":       {"lap_time_per_click": 0.05,  "confidence": 0.65},
        "front_spring":      {"lap_time_per_click": 0.05,  "confidence": 0.65},
        "wedge":             {"lap_time_per_click": 0.04,  "confidence": 0.70},
        "rear_wing":         {"lap_time_per_click": 0.0, "corner_speed": 0.0, "straight_speed": 0.0, "confidence": 0.05},
        "front_wing":        {"lap_time_per_click": 0.0, "corner_speed": 0.0, "straight_speed": 0.0, "confidence": 0.05},
    },

    # ── Dirt Road (rallycross / dirt road course) ─────────────────────────────
    "dirt_road": {
        "shock_compression": {"lap_time_per_click": 0.03,  "confidence": 0.60},
        "tire_pressure":     {"lap_time_per_click": 0.06,  "confidence": 0.70},
        "rear_spring":       {"lap_time_per_click": 0.04,  "confidence": 0.60},
        "front_spring":      {"lap_time_per_click": 0.04,  "confidence": 0.60},
        "rear_arb":          {"lap_time_per_click": 0.02,  "confidence": 0.60},
        "front_arb":         {"lap_time_per_click": 0.02,  "confidence": 0.60},
        "ride_height_rear":  {"lap_time_per_click": 0.04,  "confidence": 0.60},
        "ride_height_front": {"lap_time_per_click": 0.04,  "confidence": 0.60},
    },
}

# Aliases for fuzzy car-class name matching
_CLASS_ALIASES = {
    "gtp": "gtp", "lmp2": "lmp2", "lmp": "lmp2",
    "gt3": "gt3", "gt4": "gt4", "gte": "gte",
    "formula": "formula", "open_wheel": "formula", "f3": "formula", "ir18": "formula",
    "porsche_cup": "porsche_cup", "cup": "porsche_cup",
    "tcr": "tcr", "touring": "tcr",
    "stock": "stock", "nascar": "stock",
    "road_rookie": "road_rookie", "rookie": "road_rookie",
    "sports_car": "gt3",
    "prototype": "lmp2",
    # Oval
    "oval": "oval", "short_track": "oval", "nascar_oval": "oval",
    "intermediate": "oval", "cup_oval": "oval",
    # Superspeedway
    "superspeedway": "superspeedway", "super_speedway": "superspeedway",
    "daytona": "superspeedway", "talladega": "superspeedway",
    # Dirt
    "dirt_oval": "dirt_oval", "dirt": "dirt_oval",
    "sprint_car": "dirt_oval", "late_model": "dirt_oval",
    "modified": "dirt_oval", "dirt_late_model": "dirt_oval",
    "dirt_road": "dirt_road", "rallycross": "dirt_road",
}


def _get_model_for_class(car_class: Optional[str]) -> Dict[str, Dict]:
    """
    Return a merged _EFFECT_MODELS dict with class-specific overrides applied.
    Falls back to base GT3 models if class not recognised.
    """
    import copy
    models = copy.deepcopy(_EFFECT_MODELS)
    if not car_class:
        return models
    key = _CLASS_ALIASES.get(car_class.lower().replace(' ', '_'), car_class.lower().replace(' ', '_'))
    overrides = _CLASS_MODELS.get(key, {})
    for param, fields in overrides.items():
        if param in models:
            models[param].update(fields)
    return models


def predict_impact(changes: List[Dict[str, float]],
                   current_balance: float = 0.0,
                   issues: Optional[List[str]] = None,
                   car_class: Optional[str] = None) -> ImpactReport:
    """
    Predict impact of setup changes.

    Parameters
    ----------
    changes : list of dicts with keys: 'parameter', 'delta'
        e.g. [{'parameter': 'rear_wing', 'delta': 1}, {'parameter': 'tire_pressure', 'delta': 0.5}]
    current_balance : float
        Balance score from telemetry (+ve = oversteer, -ve = understeer)
    issues : list of str
        Detected issues from telemetry analysis

    Returns ImpactReport with predictions for each change.
    """
    issues = issues or []
    predictions: List[ImpactPrediction] = []
    effect_models = _get_model_for_class(car_class)

    for change in changes:
        param = change.get('parameter', '')
        delta = change.get('delta', 0.0)
        if param not in effect_models or delta == 0:
            continue

        model = effect_models[param]
        direction = "increase" if delta > 0 else "decrease"
        magnitude = abs(delta)

        # Compute effects
        lt_delta = model["lap_time_per_click"] * delta
        straight = model["straight_speed"] * delta
        corner = model["corner_speed"] * delta

        # Balance
        if delta > 0:
            balance = f"more {model['balance']}" if model['balance'] != 'neutral' else 'neutral'
        else:
            # Reversed
            opp = {"oversteer": "understeer", "understeer": "oversteer", "neutral": "neutral"}
            balance = f"more {opp[model['balance']]}" if model['balance'] != 'neutral' else 'neutral'

        # Tire wear
        wear = model["tire_wear"]
        if delta < 0 and wear in ("increased", "decreased"):
            wear = "decreased" if wear == "increased" else "increased"

        desc = f"{'+'if delta>0 else ''}{delta:g} {param.replace('_',' ')}"
        explanation = _explain(param, delta, lt_delta, straight, corner, balance,
                               current_balance=current_balance, issues=issues)

        predictions.append(ImpactPrediction(
            change_description=desc,
            parameter=param,
            direction=direction,
            magnitude=magnitude,
            lap_time_delta_s=lt_delta,
            straight_speed_delta_kmh=straight,
            corner_speed_delta_kmh=corner,
            balance_shift=balance,
            tire_wear_impact=wear,
            confidence=model["confidence"],
            explanation=explanation,
        ))

    net_lt = sum(p.lap_time_delta_s for p in predictions)
    # Net balance
    os_count = sum(1 for p in predictions if 'oversteer' in p.balance_shift)
    us_count = sum(1 for p in predictions if 'understeer' in p.balance_shift)
    if os_count > us_count:
        net_bal = "more oversteer"
    elif us_count > os_count:
        net_bal = "more understeer"
    else:
        net_bal = "neutral"

    direction_word = "slower" if net_lt > 0 else "faster" if net_lt < 0 else "neutral"
    summary = (
        f"Net effect: {abs(net_lt):.3f}s {direction_word} per lap, "
        f"balance shift: {net_bal}."
    )

    return ImpactReport(
        predictions=predictions,
        net_lap_time_delta_s=net_lt,
        net_balance_shift=net_bal,
        summary=summary,
    )


def _explain(param: str, delta: float, lt: float, straight: float,
             corner: float, balance: str,
             current_balance: float = 0.0,
             issues: Optional[List[str]] = None) -> str:
    """
    Generate a detailed, contextual explanation for a setup change.
    Includes the problem being addressed, the physics mechanism,
    what the driver will feel, and the expected performance impact.
    """
    issues = issues or []
    inc = delta > 0
    mag = abs(delta)
    unit_str = f"{mag:g} click{'s' if mag != 1 else ''}"

    # Describe current balance situation for context
    if abs(current_balance) < 0.05:
        bal_ctx = "your balance is currently close to neutral"
    elif current_balance > 0:
        severity = "significant" if current_balance > 0.3 else "mild"
        bal_ctx = f"your telemetry shows {severity} oversteer (balance: {current_balance:+.2f})"
    else:
        severity = "significant" if current_balance < -0.3 else "mild"
        bal_ctx = f"your telemetry shows {severity} understeer (balance: {current_balance:+.2f})"

    lt_gain = -lt  # negative lt_delta = faster
    lt_str = (f"estimated {lt_gain:.3f}s faster" if lt_gain > 0
              else f"estimated {abs(lt_gain):.3f}s slower") if abs(lt) > 0.001 else ""

    if param == "front_arb":
        if inc:
            return (
                f"WHY: {bal_ctx.capitalize()}. Stiffening the front ARB by {unit_str} "
                f"increases the load transfer rate to the outside front tyre in corners, "
                f"raising front grip relative to the rear. "
                f"EFFECT: Reduces oversteer on corner entry and mid-corner. "
                f"You should feel the front bite harder and the rear sit more securely. "
                f"Expect ~{abs(corner):.1f} km/h more corner speed. "
                + (f"{lt_str} per lap." if lt_str else "")
            )
        else:
            return (
                f"WHY: {bal_ctx.capitalize()}. Softening the front ARB by {unit_str} "
                f"reduces front lateral stiffness, allowing the front tyres more time to "
                f"load up in corners and improving turn-in response. "
                f"EFFECT: Reduces understeer — the car will rotate more readily. "
                f"Be cautious: too soft can cause instability on kerbs or over bumps. "
                + (f"{lt_str} per lap." if lt_str else "")
            )

    if param == "rear_arb":
        if inc:
            return (
                f"WHY: {bal_ctx.capitalize()}. Stiffening the rear ARB by {unit_str} "
                f"couples the rear wheels more tightly, reducing rear roll and increasing "
                f"rear lateral stiffness. "
                f"EFFECT: More high-speed stability but increases rear oversteer tendency "
                f"on corner entry. Only increase if you feel the rear is too loose at speed. "
                + (f"{lt_str} per lap." if lt_str else "")
            )
        else:
            return (
                f"WHY: {bal_ctx.capitalize()}. Softening the rear ARB by {unit_str} "
                f"lets the rear wheels move more independently, improving rear traction "
                f"especially on corner exit and over uneven surfaces. "
                f"EFFECT: Reduces oversteer — you should feel more confidence to apply "
                f"throttle earlier out of slow corners without the rear stepping out. "
                + (f"{lt_str} per lap." if lt_str else "")
            )

    if param == "front_spring":
        if inc:
            return (
                f"WHY: {bal_ctx.capitalize()}. Raising the front spring perch offset by "
                f"{unit_str} effectively stiffens the front end, reducing body roll. "
                f"EFFECT: Less front grip — turn-in feels sharper but the tyre has less "
                f"time to load fully. Can increase understeer in slow corners. "
                f"Only increase if the car feels too soft and floaty over bumps. "
                + (f"{lt_str} per lap." if lt_str else "")
            )
        else:
            return (
                f"WHY: {bal_ctx.capitalize()}. Lowering the front spring perch offset by "
                f"{unit_str} softens the front suspension, giving the tyre more contact "
                f"time with the road surface. "
                f"EFFECT: More front grip and better turn-in, especially in slow corners. "
                f"You should feel the front load up more progressively. "
                + (f"{lt_str} per lap." if lt_str else "")
            )

    if param == "rear_spring":
        if inc:
            return (
                f"WHY: {bal_ctx.capitalize()}. Raising the rear spring perch offset by "
                f"{unit_str} stiffens the rear suspension. "
                f"EFFECT: Reduces rear squat under acceleration and improves high-speed "
                f"stability but reduces rear grip in slow corners, increasing oversteer. "
                f"Best used if the car feels too soft and wallowy at the rear. "
                + (f"{lt_str} per lap." if lt_str else "")
            )
        else:
            return (
                f"WHY: {bal_ctx.capitalize()}. Lowering the rear spring perch offset by "
                f"{unit_str} softens the rear, allowing more rear grip and traction. "
                f"EFFECT: Better rear stability under braking and on corner exit. "
                f"You should feel the car more planted when getting on throttle. "
                + (f"{lt_str} per lap." if lt_str else "")
            )

    if param == "rear_wing":
        if inc:
            return (
                f"WHY: {bal_ctx.capitalize()}. Increasing rear wing angle by {unit_str} "
                f"adds rear downforce, pushing the rear tyres harder into the track. "
                f"EFFECT: More rear grip reduces oversteer through high-speed corners. "
                f"Trade-off: ~{abs(straight):.1f} km/h less top speed on straights, "
                f"but ~{abs(corner):.1f} km/h faster through corners. "
                f"Worth it on tight tracks with few long straights. "
                + (f"{lt_str} per lap." if lt_str else "")
            )
        else:
            return (
                f"WHY: {bal_ctx.capitalize()}. Reducing rear wing angle by {unit_str} "
                f"cuts drag, increasing top speed at the cost of rear downforce. "
                f"EFFECT: ~{abs(straight):.1f} km/h more top speed but ~{abs(corner):.1f} km/h "
                f"less corner speed. Can increase oversteer in fast corners. "
                f"Best on tracks with long straights. "
                + (f"{lt_str} per lap." if lt_str else "")
            )

    if param == "front_wing":
        if inc:
            return (
                f"Adding front wing by {unit_str} increases front downforce. "
                f"EFFECT: More front grip, helping turn-in and reducing understeer. "
                f"~{abs(straight):.1f} km/h top speed cost, ~{abs(corner):.1f} km/h corner gain. "
                + (f"{lt_str} per lap." if lt_str else "")
            )
        else:
            return (
                f"Reducing front wing by {unit_str} cuts front downforce and drag. "
                f"EFFECT: ~{abs(straight):.1f} km/h more top speed. Can increase understeer "
                f"in high-speed corners — monitor front tyre temps after the change. "
                + (f"{lt_str} per lap." if lt_str else "")
            )

    if param == "tire_pressure":
        if inc:
            return (
                f"WHY: Increasing starting pressure by {mag:.1f} psi on all corners. "
                f"EFFECT: Higher pressure reduces the tyre contact patch size — the tyre "
                f"runs hotter faster but provides less peak grip. "
                f"Use this if tyres are currently running cold (below 80°C) or if you "
                f"want slightly sharper initial response at the cost of peak cornering grip. "
                + (f"{lt_str} per lap." if lt_str else "")
            )
        else:
            return (
                f"WHY: Reducing starting pressure by {mag:.1f} psi on all corners. "
                f"EFFECT: Lower pressure increases the contact patch, improving peak grip "
                f"and traction. Particularly effective if tyres are running hot or showing "
                f"center wear. You should feel more mechanical grip through slow corners. "
                + (f"{lt_str} per lap." if lt_str else "")
            )

    if param == "ride_height_front":
        if inc:
            return (
                f"Raising front ride height by {unit_str}. "
                f"EFFECT: Increases front-end aero platform height, slightly reducing "
                f"front downforce. Also changes the front suspension geometry and roll "
                f"centre. Can reduce understeer in some setups. "
                + (f"{lt_str} per lap." if lt_str else "")
            )
        else:
            return (
                f"Lowering front ride height by {unit_str}. "
                f"EFFECT: Reduces front aero platform height, adding downforce and "
                f"improving front grip. Increases risk of bottoming on kerbs — "
                f"check for ground contact after the change. "
                + (f"{lt_str} per lap." if lt_str else "")
            )

    if param == "ride_height_rear":
        if inc:
            return (
                f"Raising rear ride height by {unit_str}. "
                f"EFFECT: Increases rear aero platform, slightly reducing rear downforce. "
                f"Softens the rear's aerodynamic balance — can help if the rear is "
                f"too planted and causing understeer at high speed. "
                + (f"{lt_str} per lap." if lt_str else "")
            )
        else:
            return (
                f"Lowering rear ride height by {unit_str}. "
                f"EFFECT: Increases rear downforce and plants the rear tyres harder. "
                f"Helps oversteer in high-speed corners but can bottom out on kerbs. "
                + (f"{lt_str} per lap." if lt_str else "")
            )

    if param == "brake_bias":
        if inc:
            return (
                f"WHY: Shifting brake bias {mag:.1f}% more toward the front. "
                f"EFFECT: Front brakes do more work on corner entry — allows later "
                f"braking but risks front lock-up and wash-out on entry. "
                f"Good if you're currently suffering rear lock-up or the car feels "
                f"nervous under braking. "
                f"Current bias: check your IBT data — if fronts are locking, move rearward instead. "
                + (f"{lt_str} per lap." if lt_str else "")
            )
        else:
            return (
                f"WHY: Shifting brake bias {mag:.1f}% more toward the rear. "
                f"EFFECT: Rear brakes contribute more on entry — helps rotation and "
                f"trail-braking feel. Reduces front lock risk but can cause rear instability "
                f"under heavy braking if overdone. Adjust in small steps and check for "
                f"rear lock-up under trail braking. "
                + (f"{lt_str} per lap." if lt_str else "")
            )

    if param == "tc_level":
        if inc:
            return (
                f"Increasing TC by {unit_str}. "
                f"EFFECT: The traction control intervenes earlier and more aggressively "
                f"on corner exit, preventing wheel spin. This costs ~{abs(straight):.1f} km/h "
                f"exit speed but reduces tyre wear and protects against high-speed slides. "
                f"Useful in wet conditions or if you're struggling with exit oversteer. "
                + (f"{lt_str} per lap." if lt_str else "")
            )
        else:
            return (
                f"Reducing TC by {unit_str}. "
                f"EFFECT: The system intervenes less on exit, giving you more throttle "
                f"response and ~{abs(straight):.1f} km/h more exit speed — but demands "
                f"more precise throttle application. Only reduce if you're confident "
                f"managing oversteer on exit. "
                + (f"{lt_str} per lap." if lt_str else "")
            )

    if param == "abs_level":
        if inc:
            return (
                f"Increasing ABS by {unit_str}. "
                f"EFFECT: ABS releases brake pressure earlier and more conservatively, "
                f"giving a longer braking zone but preventing lock-up. Improves "
                f"consistency under heavy braking. Use if you're struggling to hit "
                f"consistent brake markers or experiencing lock-up on entry. "
                + (f"{lt_str} per lap." if lt_str else "")
            )
        else:
            return (
                f"Reducing ABS by {unit_str}. "
                f"EFFECT: ABS allows slightly more brake pressure before intervening, "
                f"enabling shorter braking distances with precise inputs. "
                f"Only reduce if you have strong, consistent braking technique — "
                f"too low risks lock-up and flat spots. "
                + (f"{lt_str} per lap." if lt_str else "")
            )

    if param == "stagger":
        if inc:
            return (
                f"WHY: {bal_ctx.capitalize()}. Increasing stagger by {mag:.2f}\" makes the "
                f"right-side tires larger in circumference than the left, causing the car to "
                f"naturally rotate left — adding oversteer through left-hand turns. "
                f"EFFECT: More rotation, easier entry into left corners. "
                f"Can feel loose if overdone. {lt_str} per lap." if lt_str else
                f"WHY: Increasing stagger adds left-turn rotation. Monitor for excess looseness."
            )
        else:
            return (
                f"WHY: {bal_ctx.capitalize()}. Reducing stagger tightens the handling, "
                f"making the car more neutral or tight (understeer) through left turns. "
                f"EFFECT: More stable but may push (understeer) in left-hand corners. "
                + (f"{lt_str} per lap." if lt_str else "")
            )

    if param == "wedge":
        if inc:
            return (
                f"WHY: {bal_ctx.capitalize()}. Adding wedge increases cross weight "
                f"(LF + RR diagonal), tightening the car through corners. "
                f"EFFECT: More understeer — the car pushes rather than rotates. "
                f"Use if the car is too loose (oversteering) mid-corner. "
                + (f"{lt_str} per lap." if lt_str else "")
            )
        else:
            return (
                f"WHY: {bal_ctx.capitalize()}. Removing wedge reduces cross weight, "
                f"making the car freer (more oversteer) through corners. "
                f"EFFECT: Better rotation but can cause instability if too loose. "
                + (f"{lt_str} per lap." if lt_str else "")
            )

    if param == "track_bar":
        if inc:
            return (
                f"WHY: {bal_ctx.capitalize()}. Raising the track bar (panhard bar) "
                f"raises the rear roll centre, increasing rear lateral stiffness. "
                f"EFFECT: Car becomes looser (more oversteer) — better rotation but "
                f"can cause snap oversteer if raised too far. "
                + (f"{lt_str} per lap." if lt_str else "")
            )
        else:
            return (
                f"WHY: {bal_ctx.capitalize()}. Lowering the track bar reduces the "
                f"rear roll centre, giving the rear more compliance. "
                f"EFFECT: Car tightens up (more understeer) — more stable but less rotation. "
                + (f"{lt_str} per lap." if lt_str else "")
            )

    if param == "front_tape":
        if inc:
            return (
                f"Adding {unit_str} of front grill tape reduces radiator opening area. "
                f"EFFECT: ~{abs(straight):.1f} km/h gain on straights from reduced drag. "
                f"Watch coolant temps — too much tape risks overheating. "
                + (f"{lt_str} per lap." if lt_str else "")
            )
        else:
            return (
                f"Removing {unit_str} of front grill tape increases cooling airflow. "
                f"EFFECT: Safer coolant temps, slight drag increase (~{abs(straight):.1f} km/h loss). "
                f"Use if engine temps are borderline or track is hot. "
                + (f"{lt_str} per lap." if lt_str else "")
            )

    if param == "bite_bar":
        if inc:
            return (
                f"WHY: {bal_ctx.capitalize()}. Adding bite bar notches increases cross "
                f"weight on the left-rear/right-front diagonal, tightening the car. "
                f"EFFECT: Less rotation, more push (understeer). Use if the car is too "
                f"loose and hard to keep straight exiting corners. "
                + (f"{lt_str} per lap." if lt_str else "")
            )
        else:
            return (
                f"WHY: {bal_ctx.capitalize()}. Removing bite bar notches reduces cross "
                f"weight, freeing up the car for more rotation. "
                f"EFFECT: More oversteer — better entry rotation but can get slippery. "
                + (f"{lt_str} per lap." if lt_str else "")
            )

    if param == "wing_angle":
        if inc:
            return (
                f"Increasing rear wing angle by {mag:.0f}°. "
                f"EFFECT: More rear downforce, ~{abs(corner):.1f} km/h more corner speed, "
                f"~{abs(straight):.1f} km/h top speed loss. Reduces oversteer on the cushion. "
                + (f"{lt_str} per lap." if lt_str else "")
            )
        else:
            return (
                f"Reducing rear wing angle by {mag:.0f}°. "
                f"EFFECT: ~{abs(straight):.1f} km/h more top speed, less rear grip. "
                f"Can cause oversteer in high-speed sections — good if the car is too tight. "
                + (f"{lt_str} per lap." if lt_str else "")
            )

    if param == "shock_compression":
        if inc:
            return (
                f"Stiffening shock compression by {unit_str}. "
                f"EFFECT: Less body movement over bumps and rough dirt surface. "
                f"Car feels more planted but can skip over rough patches — monitor for "
                f"loss of grip on bumpy sections. "
                + (f"{lt_str} per lap." if lt_str else "")
            )
        else:
            return (
                f"Softening shock compression by {unit_str}. "
                f"EFFECT: More wheel travel, better compliance over rough dirt. "
                f"Car should hook up better through rutted sections. "
                + (f"{lt_str} per lap." if lt_str else "")
            )

    if param == "nose_weight":
        if inc:
            return (
                f"Adding {mag:.0f} lb of nose weight. "
                f"EFFECT: More front grip, car rotates more freely. "
                f"Use if the car is tight (pushing) and won't turn into corners. "
                + (f"{lt_str} per lap." if lt_str else "")
            )
        else:
            return (
                f"Removing {mag:.0f} lb of nose weight. "
                f"EFFECT: Less front grip, car tightens up. "
                f"Use if the car is too loose or darting on entry. "
                + (f"{lt_str} per lap." if lt_str else "")
            )

    if param in ("shock_rf_bump", "shock_lf_bump"):
        corner_label = "RF" if param == "shock_rf_bump" else "LF"
        return (
            f"{'Stiffening' if inc else 'Softening'} {corner_label} bump damping by {unit_str}. "
            f"EFFECT: {'More' if inc else 'Less'} resistance to body roll at that corner. "
            f"Fine-tune this after spring and wedge changes are dialled in. "
            + (f"{lt_str} per lap." if lt_str else "")
        )

    # Fallback
    return (
        f"Adjusting {param.replace('_', ' ')} by {delta:+g}. "
        f"Balance shifts toward {balance}. "
        + (f"{lt_str} per lap." if lt_str else "")
    )


def get_available_parameters() -> List[str]:
    """Return list of adjustable parameters."""
    return list(_EFFECT_MODELS.keys())


def compute_sensitivity_matrix():
    """
    Build a sensitivity matrix for all parameters and metrics.

    For each parameter, shows the effect of a +1 unit change across 6 metrics.
    Intended for heatmap visualization in the Impact tab.

    Returns
    -------
    param_labels : List[str]   — row labels (parameter names)
    metric_labels : List[str]  — column labels
    matrix : np.ndarray        — shape (n_params, n_metrics), raw values
    norm_matrix : np.ndarray   — column-normalized to [-1, 1] for coloring
    """
    params = list(_EFFECT_MODELS.keys())
    metrics = ['Lap Time\n(s / +1)', 'Corner\nSpeed', 'Straight\nSpeed',
               'Balance\nEffect', 'Tire\nWear', 'Confidence']

    _WEAR = {'increased': 1.0, 'minimal': 0.0, 'decreased': -1.0}
    _BAL  = {'oversteer': 1.0, 'neutral':  0.0, 'understeer': -1.0}

    n_p, n_m = len(params), len(metrics)
    matrix = np.zeros((n_p, n_m))

    for i, p in enumerate(params):
        m = _EFFECT_MODELS[p]
        matrix[i, 0] = m['lap_time_per_click']    # positive = slower
        matrix[i, 1] = m['corner_speed']
        matrix[i, 2] = m['straight_speed']
        matrix[i, 3] = _BAL.get(m['balance'], 0.0)
        matrix[i, 4] = _WEAR.get(m['tire_wear'], 0.0)
        matrix[i, 5] = m['confidence']

    # Normalize each column to [-1, 1] for consistent colormap scaling
    norm = matrix.copy()
    for j in range(n_m):
        col = norm[:, j]
        mx = np.max(np.abs(col))
        if mx > 1e-9:
            norm[:, j] = col / mx

    # Invert lap-time column so redder = worse (more costly)
    norm[:, 0] = -norm[:, 0]

    param_labels = [p.replace('_', ' ').title() for p in params]
    return param_labels, metrics, matrix, norm
