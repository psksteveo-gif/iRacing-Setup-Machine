"""
Setup Change Impact Predictor — Physics-based prediction of setup change effects.
Estimates sector time, balance, tire wear impact from adjustments.
"""

import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional, Dict


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
}


def predict_impact(changes: List[Dict[str, float]]) -> ImpactReport:
    """
    Predict impact of setup changes.

    Parameters
    ----------
    changes : list of dicts with keys: 'parameter', 'delta'
        e.g. [{'parameter': 'rear_wing', 'delta': 1}, {'parameter': 'tire_pressure', 'delta': 0.5}]

    Returns ImpactReport with predictions for each change.
    """
    predictions: List[ImpactPrediction] = []

    for change in changes:
        param = change.get('parameter', '')
        delta = change.get('delta', 0.0)
        if param not in _EFFECT_MODELS or delta == 0:
            continue

        model = _EFFECT_MODELS[param]
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
        explanation = _explain(param, delta, lt_delta, straight, corner, balance)

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
             corner: float, balance: str) -> str:
    name = param.replace('_', ' ').title()
    parts = []
    if "wing" in param:
        if delta > 0:
            parts.append(f"Adding {name} increases downforce.")
            parts.append(f"Expect ~{abs(straight):.1f} km/h less top speed but ~{abs(corner):.1f} km/h more corner speed.")
        else:
            parts.append(f"Reducing {name} decreases downforce.")
            parts.append(f"Expect ~{abs(straight):.1f} km/h more top speed but ~{abs(corner):.1f} km/h less corner speed.")
    elif "spring" in param or "arb" in param:
        stiffer = delta > 0
        parts.append(f"{'Stiffening' if stiffer else 'Softening'} the {name}.")
        parts.append(f"Balance shifts toward {balance}.")
    elif "pressure" in param:
        parts.append(f"{'Increasing' if delta > 0 else 'Decreasing'} {name} by {abs(delta):.1f} PSI.")
        parts.append("Higher pressure reduces contact patch but improves response.")
    elif "bias" in param:
        parts.append(f"Shifting brake bias {'forward' if delta > 0 else 'rearward'} by {abs(delta):.1f}%.")
    elif "tc" in param or "abs" in param:
        parts.append(f"{'Increasing' if delta > 0 else 'Decreasing'} {name} — less driver control, more safety.")
    else:
        parts.append(f"Adjusting {name} by {delta:+g}.")

    return " ".join(parts)


def get_available_parameters() -> List[str]:
    """Return list of adjustable parameters."""
    return list(_EFFECT_MODELS.keys())
