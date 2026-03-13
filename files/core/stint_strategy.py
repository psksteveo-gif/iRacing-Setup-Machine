"""
Stint Strategy Calculator — Optimal pit windows, fuel loads, and tire strategy.
Given race length, fuel consumption, tire wear, computes optimal pit strategy.
"""

import math
import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class PitStop:
    """Planned pit stop."""
    lap: int
    fuel_to_add_l: float
    tire_change: bool
    estimated_stop_time_s: float   # pit lane + service time


@dataclass
class StintPlan:
    """Plan for a single stint."""
    start_lap: int
    end_lap: int
    num_laps: int
    fuel_start_l: float
    fuel_end_l: float
    expected_avg_lap: float        # accounting for tire deg
    expected_total_s: float


@dataclass
class StrategyReport:
    """Complete race strategy."""
    race_laps: int
    race_time_min: float
    num_stops: int
    pit_stops: List[PitStop]
    stints: List[StintPlan]
    total_fuel_needed_l: float
    fuel_per_stop_l: List[float]
    total_race_time_s: float
    # Alternatives
    one_fewer_stop_possible: bool
    one_more_stop_delta_s: float   # time saved/lost by +1 stop
    findings: List[str] = field(default_factory=list)


# Pit stop constants
PIT_LANE_TIME_S = 25.0          # avg pit lane transit
TIRE_CHANGE_TIME_S = 3.0        # additional time for tire change
FUEL_FLOW_RATE_L_S = 5.0        # liters per second refuelling


def calculate_strategy(
    race_laps: int,
    fuel_per_lap_l: float,
    fuel_tank_capacity_l: float,
    base_lap_time_s: float,
    tire_deg_rate_s: float = 0.03,    # seconds lost per lap from tire wear
    tire_cliff_lap: int = 30,          # lap at which tires fall off cliff
    pit_delta_s: float = PIT_LANE_TIME_S,
    fuel_safety_margin: float = 1.05,  # 5% safety margin
) -> StrategyReport:
    """
    Compute optimal pit strategy.

    Tries strategies from 0 stops up to 5 stops and picks the fastest.
    """
    if fuel_per_lap_l <= 0 or race_laps <= 0 or base_lap_time_s <= 0:
        return StrategyReport(
            race_laps=race_laps, race_time_min=0, num_stops=0,
            pit_stops=[], stints=[], total_fuel_needed_l=0,
            fuel_per_stop_l=[], total_race_time_s=0,
            one_fewer_stop_possible=False, one_more_stop_delta_s=0,
            findings=["Insufficient data for strategy calculation."],
        )

    total_fuel_needed = fuel_per_lap_l * race_laps * fuel_safety_margin
    max_laps_per_tank = int(fuel_tank_capacity_l / fuel_per_lap_l) if fuel_per_lap_l > 0 else race_laps
    min_stops_fuel = max(0, math.ceil(race_laps / max_laps_per_tank) - 1)

    # Try different stop counts
    candidates = []
    for n_stops in range(min_stops_fuel, min(min_stops_fuel + 4, 6)):
        plan = _build_strategy(
            race_laps, n_stops, fuel_per_lap_l, fuel_tank_capacity_l,
            base_lap_time_s, tire_deg_rate_s, tire_cliff_lap, pit_delta_s,
            fuel_safety_margin,
        )
        if plan is not None:
            candidates.append(plan)

    if not candidates:
        return StrategyReport(
            race_laps=race_laps, race_time_min=0, num_stops=0,
            pit_stops=[], stints=[], total_fuel_needed_l=total_fuel_needed,
            fuel_per_stop_l=[], total_race_time_s=0,
            one_fewer_stop_possible=False, one_more_stop_delta_s=0,
            findings=["Could not compute a viable strategy."],
        )

    # Best = lowest total time
    best = min(candidates, key=lambda c: c.total_race_time_s)

    # Check alternatives
    fewer_possible = any(c.num_stops < best.num_stops for c in candidates)
    more_delta = 0.0
    more_stop = [c for c in candidates if c.num_stops == best.num_stops + 1]
    if more_stop:
        more_delta = more_stop[0].total_race_time_s - best.total_race_time_s

    best.one_fewer_stop_possible = fewer_possible
    best.one_more_stop_delta_s = more_delta
    best.findings = _generate_findings(best, total_fuel_needed, max_laps_per_tank, tire_cliff_lap)

    return best


def _build_strategy(
    race_laps: int, n_stops: int, fpl: float, tank: float,
    base_lap: float, deg: float, cliff: int, pit_delta: float,
    safety: float,
) -> Optional[StrategyReport]:
    """Build a strategy with n_stops pit stops."""
    n_stints = n_stops + 1
    laps_per_stint = race_laps // n_stints
    remainder = race_laps % n_stints

    stints: List[StintPlan] = []
    pit_stops: List[PitStop] = []
    fuel_per_stop: List[float] = []
    total_time = 0.0
    current_lap = 0

    for si in range(n_stints):
        stint_laps = laps_per_stint + (1 if si < remainder else 0)
        fuel_needed = fpl * stint_laps * safety

        # Check if fuel exceeds tank
        if fuel_needed > tank:
            return None

        # Tire deg within stint
        stint_times = []
        for lap_in_stint in range(stint_laps):
            actual_lap = current_lap + lap_in_stint
            tire_age = lap_in_stint  # fresh tires each stint (if changing)
            deg_penalty = deg * tire_age
            if tire_age > cliff:
                deg_penalty += (tire_age - cliff) * deg * 3  # cliff penalty
            stint_times.append(base_lap + deg_penalty)

        stint_total = sum(stint_times)
        avg_lap = stint_total / stint_laps if stint_laps > 0 else base_lap

        stints.append(StintPlan(
            start_lap=current_lap + 1,
            end_lap=current_lap + stint_laps,
            num_laps=stint_laps,
            fuel_start_l=fuel_needed,
            fuel_end_l=fuel_needed - fpl * stint_laps,
            expected_avg_lap=avg_lap,
            expected_total_s=stint_total,
        ))

        total_time += stint_total
        current_lap += stint_laps

        # Pit stop after each stint (except last)
        if si < n_stints - 1:
            next_fuel = fpl * (laps_per_stint + (1 if si + 1 < remainder else 0)) * safety
            fuel_time = next_fuel / FUEL_FLOW_RATE_L_S
            stop_time = pit_delta + TIRE_CHANGE_TIME_S + fuel_time
            pit_stops.append(PitStop(
                lap=current_lap,
                fuel_to_add_l=next_fuel,
                tire_change=True,
                estimated_stop_time_s=stop_time,
            ))
            fuel_per_stop.append(next_fuel)
            total_time += stop_time

    return StrategyReport(
        race_laps=race_laps,
        race_time_min=total_time / 60.0,
        num_stops=n_stops,
        pit_stops=pit_stops,
        stints=stints,
        total_fuel_needed_l=fpl * race_laps * safety,
        fuel_per_stop_l=fuel_per_stop,
        total_race_time_s=total_time,
        one_fewer_stop_possible=False,
        one_more_stop_delta_s=0.0,
    )


def _generate_findings(best: StrategyReport, total_fuel: float,
                       max_laps_tank: int, cliff: int) -> List[str]:
    findings = []
    findings.append(
        f"Optimal: {best.num_stops}-stop strategy — "
        f"total race time {best.race_time_min:.1f} min."
    )
    if best.stints:
        avg_stint = np.mean([s.num_laps for s in best.stints])
        findings.append(f"Average stint length: {avg_stint:.0f} laps.")
    if best.one_fewer_stop_possible:
        findings.append("A strategy with one fewer stop is possible but slower.")
    if best.one_more_stop_delta_s > 0:
        findings.append(
            f"An extra pit stop would cost +{best.one_more_stop_delta_s:.1f}s."
        )
    for s in best.stints:
        if s.num_laps > cliff:
            findings.append(
                f"Stint laps {s.start_lap}–{s.end_lap} exceeds tire cliff ({cliff} laps) — "
                f"consider an earlier stop."
            )
            break
    return findings
