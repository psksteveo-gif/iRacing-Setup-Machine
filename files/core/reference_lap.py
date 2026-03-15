"""
Reference Lap — Cross-session lap delta computation.

Compares the best lap of an external reference IBT file against the best lap
of the current session, aligned by LapDistPct, to produce a cumulative
time-delta trace (positive = slower than reference).
"""

import numpy as np
from dataclasses import dataclass
from typing import Optional

from core.ibt_parser import TelemetryData


@dataclass
class ReferenceLapDelta:
    """Time delta trace between current session best lap and an external reference."""
    dist_pct: np.ndarray    # common LapDistPct grid (0–1)
    delta_s: np.ndarray     # cumulative time delta; positive = slower than reference
    ref_best: float         # reference best lap time (s)
    cur_best: float         # current session best lap time (s)
    total_delta: float      # cur_best - ref_best (s); negative = current is faster
    ref_name: str = ""      # display label for the reference session


def compute_reference_delta(
    cur_data: TelemetryData,
    ref_data: TelemetryData,
    n_points: int = 500,
) -> Optional[ReferenceLapDelta]:
    """
    Compute a cumulative time-delta trace comparing the best laps of two sessions.

    Both laps are interpolated onto a shared LapDistPct grid. The delta at each
    position represents how many seconds the current-session driver is ahead
    of (negative) or behind (positive) the reference driver at that point.

    Parameters
    ----------
    cur_data  : TelemetryData for the active (current) session
    ref_data  : TelemetryData for the reference (ghost) session
    n_points  : number of interpolation grid points (default 500)

    Returns None if either session lacks enough data.
    """
    if cur_data is None or ref_data is None:
        return None
    if cur_data.num_laps < 1 or ref_data.num_laps < 1:
        return None

    def _best_lap_trace(data: TelemetryData):
        """Return (dist_pct_array, elapsed_time_array) for the best lap."""
        best_idx = int(np.argmin(data.lap_times)) if data.lap_times else 0
        if best_idx + 1 >= len(data.lap_boundaries):
            return None, None
        s = data.lap_boundaries[best_idx]
        e = data.lap_boundaries[best_idx + 1]
        if e - s < 10:
            return None, None
        lap_dist = data.get_channel('LapDistPct')
        session_time = data.get_channel('SessionTime')
        if lap_dist is None or session_time is None:
            return None, None
        dist = lap_dist[s:e].copy()
        elapsed = session_time[s:e].copy() - session_time[s]
        # Guard against non-monotonic LapDistPct (rare but possible at S/F crossing)
        # Keep only the monotonically increasing prefix
        mono_end = len(dist)
        for i in range(1, len(dist)):
            if dist[i] < dist[i - 1] - 0.1:
                mono_end = i
                break
        return dist[:mono_end], elapsed[:mono_end]

    cur_dist, cur_t = _best_lap_trace(cur_data)
    ref_dist, ref_t = _best_lap_trace(ref_data)

    if cur_dist is None or ref_dist is None:
        return None
    if len(cur_dist) < 10 or len(ref_dist) < 10:
        return None

    # Interpolate both onto a common grid
    grid = np.linspace(
        max(cur_dist[0], ref_dist[0]) + 0.001,
        min(cur_dist[-1], ref_dist[-1]) - 0.001,
        n_points
    )
    if len(grid) < 2:
        return None

    try:
        cur_interp = np.interp(grid, cur_dist, cur_t)
        ref_interp = np.interp(grid, ref_dist, ref_t)
    except Exception:
        return None

    delta = cur_interp - ref_interp

    cur_best = float(cur_data.lap_times[int(np.argmin(cur_data.lap_times))])
    ref_best = float(ref_data.lap_times[int(np.argmin(ref_data.lap_times))])

    ref_label = f"{ref_data.car_name} @ {ref_data.track_name}"

    return ReferenceLapDelta(
        dist_pct=grid,
        delta_s=delta,
        ref_best=ref_best,
        cur_best=cur_best,
        total_delta=cur_best - ref_best,
        ref_name=ref_label,
    )
