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

from core.setup_impact import _EFFECT_MODELS, predict_impact, ImpactReport


# ── Data types ────────────────────────────────────────────────────────────────

@dataclass
class OptimizationTarget:
    """Defines what the optimizer is trying to achieve."""
    mode: str = "balance_and_time"   # "lap_time" | "fix_balance" | "balance_and_time"
    target_balance: float = 0.0      # desired end balance (-1=US, +1=OS; 0=neutral)
    balance_weight: float = 2.0      # relative importance vs lap-time cost
    max_delta_per_param: float = 3.0 # max ±clicks / turns / psi per parameter


@dataclass
class OptimizationResult:
    """Result of one GA optimization run."""
    changes: List[Dict]          # [{'parameter': str, 'delta': float}, ...]
    impact: ImpactReport
    projected_balance: float     # estimated balance after changes
    fitness: float               # lower = better (internal score)
    description: str             # human-readable summary


# ── GA core ───────────────────────────────────────────────────────────────────

_PARAMS = list(_EFFECT_MODELS.keys())
_N = len(_PARAMS)

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

    Returns
    -------
    OptimizationResult with the best found setup changes.
    """
    if target is None:
        target = OptimizationTarget()
    if current_issues is None:
        current_issues = []

    rng = np.random.RandomState(rng_seed)
    max_d = target.max_delta_per_param

    # ── Fitness function ──────────────────────────────────────────────────────
    def _fitness(ind: np.ndarray) -> float:
        changes = [{'parameter': _PARAMS[i], 'delta': float(ind[i])}
                   for i in range(_N) if abs(ind[i]) >= 0.5]
        if not changes:
            return 1e6

        report = predict_impact(changes)

        # Balance improvement
        bal_shift = _BAL_DELTA.get(report.net_balance_shift, 0.0)
        projected = np.clip(current_balance + bal_shift, -1.0, 1.0)
        balance_error = abs(projected - target.target_balance)

        # Lap-time cost (magnitude of total change — any change has a cost)
        lt_cost = abs(report.net_lap_time_delta_s)

        # Complexity penalty (prefer fewer changes)
        complexity = len(changes) * 0.04

        # Confidence reward (prefer high-confidence parameters)
        avg_conf = np.mean([_EFFECT_MODELS[c['parameter']]['confidence']
                            for c in changes])
        conf_reward = (1.0 - avg_conf) * 0.3

        if target.mode == "lap_time":
            # Minimise absolute lap time impact (already near-neutral car)
            return lt_cost + complexity + conf_reward + balance_error * 0.3
        elif target.mode == "fix_balance":
            # Strongly minimise balance error, lap time secondary
            return balance_error * target.balance_weight + lt_cost * 0.5 + complexity + conf_reward
        else:  # balance_and_time
            return (balance_error * target.balance_weight
                    + lt_cost * 1.0
                    + complexity
                    + conf_reward)

    # ── Initialise population ─────────────────────────────────────────────────
    # Seed initial population with balance-aware bias
    bias = _balance_bias(current_balance)
    pop = rng.uniform(-max_d, max_d, (pop_size, _N))
    pop += bias * rng.uniform(0.0, 1.5, (pop_size, _N))
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
            mask = rng.rand(_N) > 0.5
            child = np.where(mask, p1, p2)
            # Gaussian mutation
            child = child + rng.randn(_N) * sigma
            child = _snap_and_clip(child, max_d)
            new_pop.append(child)

        pop = np.array(new_pop)

    # ── Build result from best individual ─────────────────────────────────────
    raw_changes = [
        {'parameter': _PARAMS[i], 'delta': float(best_ind[i])}
        for i in range(_N) if abs(best_ind[i]) >= 0.5
    ]

    # Sort by predicted absolute lap-time impact (most impactful first)
    raw_changes.sort(
        key=lambda c: abs(_EFFECT_MODELS[c['parameter']]['lap_time_per_click'] * c['delta']),
        reverse=True,
    )

    # Cap at 5 changes — more than that is impractical between sessions
    best_changes = raw_changes[:5]

    if not best_changes:
        # Fallback: return the single highest-impact parameter
        idx = int(np.argmax(np.abs(best_ind)))
        best_changes = [{'parameter': _PARAMS[idx], 'delta': float(best_ind[idx])}]

    final_report = predict_impact(best_changes)
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


def _balance_bias(balance: float) -> np.ndarray:
    """
    Per-parameter bias vector that nudges initial population toward fixing
    the current balance imbalance.
    """
    bias = np.zeros(_N)
    for i, p in enumerate(_PARAMS):
        param_bal = _EFFECT_MODELS[p].get('balance', 'neutral')
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
