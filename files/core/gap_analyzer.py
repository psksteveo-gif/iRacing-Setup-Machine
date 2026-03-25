"""
Gap Analyzer
============
Uses iRacing's CarIdxLapDistPct and CarIdxLap array channels to compute
the gap (in seconds) between the player and nearby cars on every lap.

CarIdxLapDistPct[n] = car n's track position as fraction 0-1
CarIdxLap[n]        = car n's current lap number
These are arrays of 64 values — one per car slot.

The player's car index is stored in session_info['driver_car_idx'].
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from core.ibt_parser import TelemetryData


@dataclass
class CarGapSample:
    session_time: float
    lap: int
    gap_ahead_s: float    # positive = car is ahead, seconds
    gap_behind_s: float   # positive = car is behind
    car_idx_ahead: int
    car_idx_behind: int


@dataclass
class LapGapSummary:
    lap: int
    min_gap_ahead_s: float    # closest car ahead this lap
    min_gap_behind_s: float   # closest car behind this lap
    traffic_exposure_s: float # seconds within 2.0s of another car


@dataclass
class GapReport:
    has_data: bool = False
    player_car_idx: int = -1
    lap_summaries: List[LapGapSummary] = field(default_factory=list)
    # Top-level stats
    min_gap_overall_s: float = 999.0
    laps_with_traffic: int = 0
    traffic_threshold_s: float = 2.0
    summary: str = ""


# Approx seconds per % of track at typical GT3 pace (6 km track @ 90s lap)
_PCT_TO_SECONDS = 90.0   # will be overridden by actual lap times if available


def analyze_gaps(data: TelemetryData) -> GapReport:
    report = GapReport()

    # Get player car idx
    si = data.session_info or {}
    player_idx = si.get('driver_car_idx', -1)
    report.player_car_idx = player_idx

    # Check for CarIdxLapDistPct — this is a multi-value channel
    # In the IBT parser it comes through as a flat array of 64 * num_samples values
    # The parser stores it as a single channel named 'CarIdxLapDistPct'
    # However our parser only stores scalar channels by name. For array channels,
    # iRacing stores 64 sequential floats per tick in the buffer.
    # Check if we have it as individual indexed channels (CarIdxLapDistPct_0 etc.)
    # or as the raw multi-value channel.

    # Try to find player channel and adjacent car channels
    player_dist_ch = data.get_channel('LapDistPct')  # player's own lap dist
    if player_dist_ch is None:
        return report

    # Look for multi-car channels (indexed variants)
    car_dists: Dict[int, np.ndarray] = {}
    # Try CarIdxLapDistPct_0 through CarIdxLapDistPct_63
    for idx in range(64):
        ch = data.get_channel(f'CarIdxLapDistPct_{idx}')
        if ch is not None and len(ch) > 0:
            car_dists[idx] = ch.astype(float)

    # Fallback: also check plain 'CarIdxLapDistPct' — may be the player's own
    if not car_dists:
        # No multi-car data available
        report.summary = "Multi-car gap data not available in this IBT file"
        return report

    report.has_data = True

    # Estimate seconds-per-pct conversion from actual lap times
    if data.lap_times:
        valid_times = [t for t in data.lap_times if t and 30 < t < 600]
        if valid_times:
            global _PCT_TO_SECONDS
            _PCT_TO_SECONDS = float(np.median(valid_times))

    player_dist = player_dist_ch
    session_time = data.get_channel('SessionTime')
    boundaries   = data.lap_boundaries

    if not boundaries or len(boundaries) < 2:
        return report

    # Per-lap analysis
    for lap_idx in range(data.num_laps):
        b0 = boundaries[lap_idx]
        b1 = boundaries[lap_idx + 1] if lap_idx + 1 < len(boundaries) else len(player_dist)
        if b1 <= b0:
            continue

        p_dist = player_dist[b0:b1]
        min_gap_ahead  = 999.0
        min_gap_behind = 999.0
        traffic_frames = 0

        for car_idx, car_dist_full in car_dists.items():
            if car_idx == player_idx:
                continue
            if len(car_dist_full) < b1:
                continue
            c_dist = car_dist_full[b0:b1]

            # Gap = difference in track position, converted to seconds
            # Positive = car is ahead
            raw_gap = c_dist - p_dist
            # Handle lap-wrap: normalise to [-0.5, 0.5]
            raw_gap = np.where(raw_gap > 0.5, raw_gap - 1.0, raw_gap)
            raw_gap = np.where(raw_gap < -0.5, raw_gap + 1.0, raw_gap)
            gap_s = raw_gap * _PCT_TO_SECONDS

            # Car ahead (gap_s > 0)
            ahead_mask = gap_s > 0
            if np.any(ahead_mask):
                min_gap_ahead_this = float(np.min(gap_s[ahead_mask]))
                min_gap_ahead = min(min_gap_ahead, min_gap_ahead_this)

            # Car behind (gap_s < 0)
            behind_mask = gap_s < 0
            if np.any(behind_mask):
                min_gap_behind_this = float(np.min(np.abs(gap_s[behind_mask])))
                min_gap_behind = min(min_gap_behind, min_gap_behind_this)

            # Traffic: within 2s of any car
            traffic_mask = np.abs(gap_s) < report.traffic_threshold_s
            traffic_frames += int(np.sum(traffic_mask))

        tick = data.tick_rate or 60
        traffic_s = traffic_frames / tick  # convert to seconds (may double-count)

        summary = LapGapSummary(
            lap=lap_idx + 1,
            min_gap_ahead_s=round(min_gap_ahead, 2) if min_gap_ahead < 999.0 else -1.0,
            min_gap_behind_s=round(min_gap_behind, 2) if min_gap_behind < 999.0 else -1.0,
            traffic_exposure_s=round(traffic_s, 1),
        )
        report.lap_summaries.append(summary)

        if min_gap_ahead < report.min_gap_overall_s:
            report.min_gap_overall_s = min_gap_ahead

    report.laps_with_traffic = sum(
        1 for s in report.lap_summaries if s.traffic_exposure_s > 3.0
    )
    if report.lap_summaries:
        report.summary = (
            f"{report.laps_with_traffic} lap{'s' if report.laps_with_traffic != 1 else ''} "
            f"with traffic  |  closest gap: {report.min_gap_overall_s:.2f}s"
            if report.min_gap_overall_s < 999.0 else
            f"{report.laps_with_traffic} laps with traffic"
        )

    return report
