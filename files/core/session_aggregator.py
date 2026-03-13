"""
Multi-Session Aggregation — Trend analysis across multiple sessions.
Tracks best lap, consistency, tire wear, fuel usage across loaded sessions.
"""

import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime


@dataclass
class SessionSummary:
    """Summary of a single session for cross-session trending."""
    index: int
    car_name: str
    track_name: str
    num_laps: int
    best_lap: float
    avg_lap: float
    worst_lap: float
    consistency_pct: float        # std_dev / mean * 100 (lower = more consistent)
    avg_tire_temp: float          # average of all tire temps
    fuel_per_lap: float           # estimated fuel consumption per lap
    session_type: str
    label: str                    # short display label


@dataclass
class AggregationReport:
    """Cross-session trend analysis."""
    summaries: List[SessionSummary]
    num_sessions: int
    # Overall trends
    best_lap_trend: List[float]     # best lap per session
    avg_lap_trend: List[float]
    consistency_trend: List[float]  # consistency score per session
    # Improvement
    total_improvement: float        # first best lap - last best lap (positive = improvement)
    improving: bool
    improvement_per_session: float  # seconds gained per session
    # Car/Track grouping
    car_track_combos: Dict[str, List[int]]  # "car@track" → session indices
    findings: List[str] = field(default_factory=list)


def aggregate_sessions(sessions: list) -> Optional[AggregationReport]:
    """
    Build cross-session trend report.

    Parameters
    ----------
    sessions : list of (TelemetryData, AnalysisReport) tuples

    Returns None if fewer than 2 sessions.
    """
    if len(sessions) < 2:
        return None

    summaries: List[SessionSummary] = []
    car_track: Dict[str, List[int]] = {}

    for i, (data, rpt) in enumerate(sessions):
        times = data.lap_times
        if not times:
            continue

        arr = np.array(times)
        best = float(np.min(arr))
        avg = float(np.mean(arr))
        worst = float(np.max(arr))
        std = float(np.std(arr))
        con = (std / avg * 100) if avg > 0 else 0.0

        # Average tire temp
        temps = []
        for corner in ['LF', 'RF', 'LR', 'RR']:
            ch = data.get_channel(f'{corner}tempCM')
            if ch is not None:
                temps.append(float(np.mean(ch)))
        avg_temp = float(np.mean(temps)) if temps else 0.0

        # Fuel per lap
        fuel = data.get_channel('FuelLevel')
        if fuel is not None and data.num_laps > 1:
            fuel_start = float(fuel[data.lap_boundaries[0]])
            fuel_end = float(fuel[min(data.lap_boundaries[-1], len(fuel) - 1)])
            fpl = (fuel_start - fuel_end) / data.num_laps
        else:
            fpl = 0.0

        stype = data.session_info.get('session_type', 'Unknown')
        label = f"S{i+1}: {data.car_name[:15]}"

        ss = SessionSummary(
            index=i, car_name=data.car_name, track_name=data.track_name,
            num_laps=data.num_laps, best_lap=best, avg_lap=avg, worst_lap=worst,
            consistency_pct=con, avg_tire_temp=avg_temp, fuel_per_lap=fpl,
            session_type=stype, label=label,
        )
        summaries.append(ss)

        key = f"{data.car_name}@{data.track_name}"
        car_track.setdefault(key, []).append(i)

    if len(summaries) < 2:
        return None

    best_trend = [s.best_lap for s in summaries]
    avg_trend = [s.avg_lap for s in summaries]
    con_trend = [s.consistency_pct for s in summaries]

    total_imp = best_trend[0] - best_trend[-1]
    imp_per = total_imp / (len(summaries) - 1) if len(summaries) > 1 else 0.0

    findings = _generate_findings(summaries, total_imp, car_track)

    return AggregationReport(
        summaries=summaries,
        num_sessions=len(summaries),
        best_lap_trend=best_trend,
        avg_lap_trend=avg_trend,
        consistency_trend=con_trend,
        total_improvement=total_imp,
        improving=total_imp > 0,
        improvement_per_session=imp_per,
        car_track_combos=car_track,
        findings=findings,
    )


def _generate_findings(summaries: List[SessionSummary],
                       total_imp: float,
                       car_track: Dict[str, List[int]]) -> List[str]:
    findings = []
    if total_imp > 0.5:
        findings.append(f"Improved by {total_imp:.2f}s over {len(summaries)} sessions — great progression!")
    elif total_imp < -0.5:
        findings.append(f"Lap times increased by {abs(total_imp):.2f}s — review track conditions or setup changes.")

    # Consistency trend
    con = [s.consistency_pct for s in summaries]
    if len(con) >= 3 and con[-1] < con[0]:
        findings.append("Consistency is improving across sessions.")

    # Best session
    best_session = min(summaries, key=lambda s: s.best_lap)
    findings.append(f"Best overall lap: {best_session.best_lap:.3f}s in Session {best_session.index + 1}.")

    # Multiple cars/tracks
    if len(car_track) > 1:
        findings.append(f"Data spans {len(car_track)} car/track combinations.")

    return findings
