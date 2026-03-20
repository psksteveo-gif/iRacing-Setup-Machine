"""
Setup Optimizer — Genetic Algorithm for iRacing setup optimization.

Given the current telemetry analysis (balance score, severity issues), evolves
a population of candidate setup-change vectors to find the combination that
best achieves the chosen target (fix balance, minimize lap time, or both).

No external dependencies beyond NumPy.
"""

import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional, Dict

from core.setup_impact import _EFFECT_MODELS, _CLASS_ALIASES, _get_model_for_class, predict_impact, ImpactReport


# ── Data types ────────────────────────────────────────────────────────────────

@dataclass
class OptimizationTarget:
    """Defines what the optimizer is trying to achieve."""
    mode: str = "balance_and_time"   # "lap_time" | "fix_balance" | "balance_and_time"
    target_balance: float = 0.0      # desired end balance (-1=US, +1=OS; 0=neutral)
    balance_weight: float = 2.0      # relative importance vs lap-time cost
    max_delta_per_param: float = 3.0 # max ±clicks / turns / psi per parameter
    stint_mode: str = "race"         # "qualifying" | "race" | "endurance"


@dataclass
class OptimizationResult:
    """Result of one GA optimization run."""
    changes: List[Dict]          # [{'parameter': str, 'delta': float}, ...]
    impact: ImpactReport
    projected_balance: float     # estimated balance after changes
    fitness: float               # lower = better (internal score)
    description: str             # human-readable summary


# ── GA core ───────────────────────────────────────────────────────────────────

# Road course parameters (default)
_ROAD_PARAMS = [
    "rear_wing", "front_wing", "rear_spring", "front_spring",
    "rear_arb", "front_arb", "tire_pressure", "ride_height_rear",
    "ride_height_front", "brake_bias", "tc_level", "abs_level",
]

# Oval parameters (replaces road params for oval classes)
_OVAL_PARAMS = [
    "stagger", "wedge", "track_bar", "tire_pressure",
    "brake_bias", "rear_spring", "front_spring",
    "shock_rf_bump", "shock_lf_bump", "front_tape", "tc_level",
]

# Superspeedway parameters
_SUPERSPEEDWAY_PARAMS = [
    "stagger", "wedge", "track_bar", "tire_pressure",
    "front_tape", "rear_spring", "front_spring", "brake_bias",
]

# Dirt oval parameters
_DIRT_OVAL_PARAMS = [
    "bite_bar", "nose_weight", "wing_angle", "shock_compression",
    "tire_pressure", "rear_spring", "front_spring", "wedge",
]

# Dirt road parameters
_DIRT_ROAD_PARAMS = [
    "shock_compression", "tire_pressure", "rear_spring", "front_spring",
    "rear_arb", "front_arb", "brake_bias",
    "ride_height_rear", "ride_height_front",
]

# Default fallback (all road params)
_PARAMS = _ROAD_PARAMS
_N = len(_PARAMS)


def _get_class_params(car_class: Optional[str]) -> List[str]:
    """Return the appropriate parameter list for the given car class."""
    if not car_class:
        return _ROAD_PARAMS
    key = _CLASS_ALIASES.get(car_class.lower().replace(' ', '_'),
                              car_class.lower().replace(' ', '_'))
    if key == "superspeedway":
        return _SUPERSPEEDWAY_PARAMS
    if key == "oval":
        return _OVAL_PARAMS
    if key == "dirt_oval":
        return _DIRT_OVAL_PARAMS
    if key == "dirt_road":
        return _DIRT_ROAD_PARAMS
    return _ROAD_PARAMS

# Map balance strings → numeric delta for scoring
_BAL_DELTA = {'oversteer': 0.35, 'understeer': -0.35, 'neutral': 0.0,
               'more oversteer': 0.35, 'more understeer': -0.35}


def optimize_setup(
    current_balance: float = 0.0,
    current_issues: Optional[List[str]] = None,
    target: Optional[OptimizationTarget] = None,
    n_generations: int = 60,
    pop_size: int = 80,
    rng_seed: int = 0,
    car_class: Optional[str] = None,
    balance_entry: float = 0.0,
    balance_mid: float = 0.0,
    balance_exit: float = 0.0,
) -> OptimizationResult:
    """
    Run a genetic algorithm to find the optimal set of setup changes.

    Parameters
    ----------
    current_balance : float
        Current car balance score (-1 = full understeer, +1 = full oversteer).
    current_issues : list of str
        Issue titles from the analysis report (used for display only).
    target : OptimizationTarget
        Optimization objectives. Defaults to balanced mode.
    n_generations : int
        Number of GA generations (default 60 — typically converges by gen 30).
    pop_size : int
        Population size (default 80).
    rng_seed : int
        Random seed for reproducibility.
    car_class : str, optional
        Car class string (e.g. 'gt3', 'formula', 'tcr') — selects appropriate
        physics model coefficients for lap-time and balance predictions.
    balance_entry : float
        Corner-entry (trail-brake) balance phase score (-1=US, +1=OS).
    balance_mid : float
        Mid-corner balance phase score.
    balance_exit : float
        Corner-exit (power-on) balance phase score.

    Returns
    -------
    OptimizationResult with the best found setup changes.
    """
    if target is None:
        target = OptimizationTarget()
    if current_issues is None:
        current_issues = []

    # Build car-class-specific effect models and parameter list
    effect_models = _get_model_for_class(car_class)
    local_params = _get_class_params(car_class)
    local_n = len(local_params)

    rng = np.random.RandomState(rng_seed)
    max_d = target.max_delta_per_param

    # ── Fitness function ──────────────────────────────────────────────────────
    # Corner-phase params adapted for both road and oval/dirt contexts
    _PHASE_PARAMS = {
        "entry":  {"brake_bias", "front_arb", "front_spring", "wedge", "track_bar"},
        "mid":    {"front_spring", "rear_spring", "front_arb", "rear_arb",
                   "ride_height_front", "ride_height_rear", "stagger", "bite_bar"},
        "exit":   {"tc_level", "rear_spring", "rear_arb", "tire_pressure",
                   "shock_compression", "nose_weight"},
    }
    _phase_scores = {
        "entry": balance_entry,
        "mid":   balance_mid,
        "exit":  balance_exit,
    }

    def _phase_bonus(param: str, delta: float) -> float:
        """Extra fitness reward for changes that fix the worst corner phase."""
        bonus = 0.0
        for phase, phase_params in _PHASE_PARAMS.items():
            if param not in phase_params:
                continue
            ph_bal = _phase_scores[phase]
            if abs(ph_bal) < 0.10:
                continue  # phase is neutral — no bonus
            param_bal = effect_models.get(param, {}).get("balance", "neutral")
            opp = {"oversteer": "understeer", "understeer": "oversteer", "neutral": "neutral"}
            # Reward if this change moves balance opposite to the phase's imbalance
            if ph_bal < 0 and delta > 0 and param_bal == "oversteer":
                bonus += abs(ph_bal) * 0.15   # phase understeers, change adds oversteer → good
            elif ph_bal > 0 and delta > 0 and param_bal == "understeer":
                bonus += abs(ph_bal) * 0.15
            elif ph_bal < 0 and delta < 0 and opp.get(param_bal) == "oversteer":
                bonus += abs(ph_bal) * 0.15
            elif ph_bal > 0 and delta < 0 and opp.get(param_bal) == "understeer":
                bonus += abs(ph_bal) * 0.15
        return bonus

    def _fitness(ind: np.ndarray) -> float:
        changes = [{'parameter': local_params[i], 'delta': float(ind[i])}
                   for i in range(local_n) if abs(ind[i]) >= 0.5]
        if not changes:
            return 1e6

        report = predict_impact(changes, current_balance=current_balance,
                                car_class=car_class)

        # Balance improvement
        bal_shift = _BAL_DELTA.get(report.net_balance_shift, 0.0)
        projected = np.clip(current_balance + bal_shift, -1.0, 1.0)
        balance_error = abs(projected - target.target_balance)

        # Lap-time cost (magnitude of total change — any change has a cost)
        lt_cost = abs(report.net_lap_time_delta_s)

        # Complexity penalty (prefer fewer changes) — relaxed for qualifying (one shot)
        if target.stint_mode == "qualifying":
            complexity = len(changes) * 0.01   # almost no penalty — squeeze every tenth
        else:
            complexity = len(changes) * 0.04

        # Confidence reward (prefer high-confidence parameters)
        avg_conf = np.mean([effect_models.get(c['parameter'], _EFFECT_MODELS.get(c['parameter'], {})).get('confidence', 0.5)
                            for c in changes])
        conf_reward = (1.0 - avg_conf) * 0.3

        # Tire-wear penalty for endurance stints
        wear_penalty = 0.0
        if target.stint_mode == "endurance":
            for c in changes:
                wear = effect_models.get(c['parameter'], _EFFECT_MODELS.get(c['parameter'], {})).get('tire_wear', 'neutral')
                if wear == 'increased':
                    wear_penalty += abs(c['delta']) * 0.05
                elif wear == 'reduced':
                    wear_penalty -= abs(c['delta']) * 0.02  # reward wear-saving changes

        # Corner-phase bonus (reward changes that fix the worst phase)
        phase_bonus = sum(_phase_bonus(c['parameter'], c['delta']) for c in changes)

        if target.mode == "lap_time":
            return lt_cost + complexity + conf_reward + balance_error * 0.3 - phase_bonus + wear_penalty
        elif target.mode == "fix_balance":
            return balance_error * target.balance_weight + lt_cost * 0.5 + complexity + conf_reward - phase_bonus + wear_penalty
        else:  # balance_and_time
            return (balance_error * target.balance_weight
                    + lt_cost * 1.0
                    + complexity
                    + conf_reward
                    - phase_bonus
                    + wear_penalty)

    # ── Initialise population ─────────────────────────────────────────────────
    bias = _balance_bias(current_balance, local_params)
    pop = rng.uniform(-max_d, max_d, (pop_size, local_n))
    pop += bias * rng.uniform(0.0, 1.5, (pop_size, local_n))
    pop = _snap_and_clip(pop, max_d)

    best_ind = pop[0].copy()
    best_fit = _fitness(best_ind)

    # ── Evolution ─────────────────────────────────────────────────────────────
    elite_n = max(3, pop_size // 8)

    for gen in range(n_generations):
        scores = np.array([_fitness(ind) for ind in pop])
        order = np.argsort(scores)
        pop = pop[order]
        scores = scores[order]

        if scores[0] < best_fit:
            best_fit = scores[0]
            best_ind = pop[0].copy()

        # Adaptive mutation rate decays with generation
        sigma = max_d * max(0.05, 0.6 * (1.0 - gen / n_generations))

        new_pop = [pop[i].copy() for i in range(elite_n)]

        while len(new_pop) < pop_size:
            # Tournament selection (size 3) from top half
            half = max(4, pop_size // 2)
            t1 = rng.choice(half, size=3, replace=False)
            t2 = rng.choice(half, size=3, replace=False)
            p1 = pop[int(t1.min())]
            p2 = pop[int(t2.min())]
            # Uniform crossover
            mask = rng.rand(local_n) > 0.5
            child = np.where(mask, p1, p2)
            # Gaussian mutation
            child = child + rng.randn(local_n) * sigma
            child = _snap_and_clip(child, max_d)
            new_pop.append(child)

        pop = np.array(new_pop)

    # ── Build result from best individual ─────────────────────────────────────
    raw_changes = [
        {'parameter': local_params[i], 'delta': float(best_ind[i])}
        for i in range(local_n) if abs(best_ind[i]) >= 0.5
    ]

    # Sort by predicted absolute lap-time impact (most impactful first)
    raw_changes.sort(
        key=lambda c: abs(effect_models.get(c['parameter'], _EFFECT_MODELS.get(c['parameter'], {})).get('lap_time_per_click', 0.0) * c['delta']),
        reverse=True,
    )

    # Cap at 5 changes — more than that is impractical between sessions
    best_changes = raw_changes[:5]

    if not best_changes:
        # Fallback: return the single highest-impact parameter
        idx = int(np.argmax(np.abs(best_ind)))
        best_changes = [{'parameter': local_params[idx], 'delta': float(best_ind[idx])}]

    final_report = predict_impact(best_changes, current_balance=current_balance,
                                  car_class=car_class)
    bal_shift = _BAL_DELTA.get(final_report.net_balance_shift, 0.0)
    projected_balance = float(np.clip(current_balance + bal_shift, -1.0, 1.0))

    description = _describe(best_changes, current_balance, projected_balance,
                             target, final_report)

    return OptimizationResult(
        changes=best_changes,
        impact=final_report,
        projected_balance=projected_balance,
        fitness=best_fit,
        description=description,
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _snap_and_clip(arr: np.ndarray, max_d: float) -> np.ndarray:
    """Round to 0.5 increments (click-based) and clip to ±max_d. Zero near-zero."""
    arr = np.round(arr * 2.0) / 2.0
    arr = np.clip(arr, -max_d, max_d)
    arr[np.abs(arr) < 0.5] = 0.0
    return arr


def _balance_bias(balance: float, params: Optional[List[str]] = None) -> np.ndarray:
    """
    Per-parameter bias vector that nudges initial population toward fixing
    the current balance imbalance.
    """
    if params is None:
        params = _ROAD_PARAMS
    n = len(params)
    bias = np.zeros(n)
    for i, p in enumerate(params):
        param_bal = _EFFECT_MODELS.get(p, {}).get('balance', 'neutral')
        if balance < -0.15:                 # car understeers → want oversteer-inducing changes
            if param_bal == 'oversteer':
                bias[i] = 0.8
            elif param_bal == 'understeer':
                bias[i] = -0.8
        elif balance > 0.15:                # car oversteers → want understeer-inducing changes
            if param_bal == 'understeer':
                bias[i] = 0.8
            elif param_bal == 'oversteer':
                bias[i] = -0.8
    return bias


def _describe(changes: List[Dict], cur_bal: float, proj_bal: float,
              target: OptimizationTarget, report: ImpactReport) -> str:
    if abs(cur_bal) < 0.15:
        context = "Neutral car — optimising for lap time."
    elif cur_bal < 0:
        context = f"Correcting understeer (balance {cur_bal:+.2f} → projected {proj_bal:+.2f})."
    else:
        context = f"Correcting oversteer (balance {cur_bal:+.2f} → projected {proj_bal:+.2f})."

    lt_str = f"Predicted net: {report.net_lap_time_delta_s:+.3f}s"
    n_str = f"{len(changes)} change{'s' if len(changes) != 1 else ''}"
    return f"{context}  •  {lt_str}  •  {n_str} recommended."


def priority_label(change: Dict) -> str:
    """Return a short priority string for display (P1, P2, …)."""
    return ""   # caller assigns based on list index
