"""
Suspension Analyzer
===================
Analyzes shock deflection (travel) and velocity channels to detect kerb strikes,
bottoming events, damper mismatches, and ride height trends.

Channels used:
  LFshockDefl, RFshockDefl, LRshockDefl, RRshockDefl  — travel in mm
  LFshockVel,  RFshockVel,  LRshockVel,  RRshockVel   — velocity in m/s
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from core.ibt_parser import TelemetryData

CORNERS = ['LF', 'RF', 'LR', 'RR']

# Thresholds
KERB_VEL_THRESHOLD   = 0.30   # m/s — velocity spike above this = kerb strike
BOTTOM_DEFL_FRAC     = 0.92   # fraction of per-corner max → bottoming
MISMATCH_STD_RATIO   = 0.25   # std/mean ratio difference between corners
MIN_SAMPLES          = 500


@dataclass
class CornerSuspension:
    corner: str
    has_data: bool = False
    mean_defl_mm: float = 0.0
    max_defl_mm:  float = 0.0
    std_defl_mm:  float = 0.0
    mean_vel_ms:  float = 0.0
    max_vel_ms:   float = 0.0
    kerb_strike_count: int = 0
    bottom_out_count:  int = 0
    # Per-lap averages
    lap_mean_defl: List[float] = field(default_factory=list)


@dataclass
class SuspensionEvent:
    corner: str
    lap: int
    lap_dist_pct: float
    event_type: str      # 'kerb_strike' | 'bottom_out'
    severity: float      # 0-1
    velocity_ms: float
    defl_mm: float


@dataclass
class SuspensionReport:
    corners: Dict[str, CornerSuspension] = field(default_factory=dict)
    events: List[SuspensionEvent] = field(default_factory=list)
    has_data: bool = False
    # Overall findings
    worst_corner: str = ""
    ride_height_trend: str = ""   # 'stable', 'rising', 'falling'
    mismatch_warning: str = ""    # e.g. "LF/RF stiffness mismatch"
    total_kerb_strikes: int = 0
    total_bottom_outs: int = 0


class SuspensionAnalyzer:

    def analyze(self, data: TelemetryData) -> SuspensionReport:
        report = SuspensionReport()

        lap_dist    = data.get_channel('LapDistPct')
        session_time = data.get_channel('SessionTime')
        boundaries  = data.lap_boundaries

        for corner in CORNERS:
            defl_ch = data.get_channel(f'{corner}shockDefl')
            vel_ch  = data.get_channel(f'{corner}shockVel')
            cs = CornerSuspension(corner=corner)

            if defl_ch is not None and len(defl_ch) >= MIN_SAMPLES:
                defl = defl_ch.astype(float)
                cs.has_data = True
                cs.mean_defl_mm = float(np.mean(defl))
                cs.max_defl_mm  = float(np.max(defl))
                cs.std_defl_mm  = float(np.std(defl))
                report.has_data = True

                # Per-lap deflection averages
                if boundaries:
                    for i in range(data.num_laps):
                        b0 = boundaries[i]
                        b1 = boundaries[i + 1] if i + 1 < len(boundaries) else len(defl)
                        seg = defl[b0:b1]
                        cs.lap_mean_defl.append(float(np.mean(seg)) if len(seg) > 0 else 0.0)

                if vel_ch is not None and len(vel_ch) >= MIN_SAMPLES:
                    vel = vel_ch.astype(float)
                    cs.mean_vel_ms = float(np.mean(np.abs(vel)))
                    cs.max_vel_ms  = float(np.max(np.abs(vel)))

                    # Detect kerb strikes: velocity spikes
                    kerb_mask = np.abs(vel) > KERB_VEL_THRESHOLD
                    # Debounce: minimum 15 frames between events
                    kerb_indices = np.where(kerb_mask)[0]
                    kerb_events = _debounce(kerb_indices, gap=15)
                    cs.kerb_strike_count = len(kerb_events)
                    report.total_kerb_strikes += len(kerb_events)

                    # Build per-event records (up to 20 per corner)
                    if lap_dist is not None and boundaries:
                        for idx in kerb_events[:20]:
                            lap_idx = _find_lap(idx, boundaries)
                            report.events.append(SuspensionEvent(
                                corner=corner, lap=lap_idx + 1,
                                lap_dist_pct=float(lap_dist[idx]) if idx < len(lap_dist) else 0.0,
                                event_type='kerb_strike',
                                severity=min(1.0, float(abs(vel[idx])) / (KERB_VEL_THRESHOLD * 3)),
                                velocity_ms=round(float(vel[idx]), 3),
                                defl_mm=round(float(defl[idx]), 1),
                            ))

                # Detect bottoming: deflection near max travel
                if cs.max_defl_mm > 0:
                    bottom_mask = defl >= cs.max_defl_mm * BOTTOM_DEFL_FRAC
                    bottom_indices = np.where(bottom_mask)[0]
                    bottom_events = _debounce(bottom_indices, gap=30)
                    cs.bottom_out_count = len(bottom_events)
                    report.total_bottom_outs += len(bottom_events)

            report.corners[corner] = cs

        if not report.has_data:
            return report

        # Find worst corner (most kerb strikes)
        kerb_by_corner = {c: report.corners[c].kerb_strike_count for c in CORNERS
                          if report.corners[c].has_data}
        if kerb_by_corner:
            report.worst_corner = max(kerb_by_corner, key=kerb_by_corner.get)

        # Ride height trend: does mean deflection increase over session?
        _check_ride_height_trend(report)

        # Mismatch check: compare LF/RF and LR/RR std ratios
        _check_mismatch(report)

        # Sort events by severity
        report.events.sort(key=lambda e: e.severity, reverse=True)
        return report


# ── Helpers ────────────────────────────────────────────────────────────────────

def _debounce(indices: np.ndarray, gap: int) -> List[int]:
    """Return indices with at least `gap` frames between them."""
    if len(indices) == 0:
        return []
    result = [int(indices[0])]
    for i in indices[1:]:
        if int(i) - result[-1] >= gap:
            result.append(int(i))
    return result


def _find_lap(sample_idx: int, boundaries: List[int]) -> int:
    """Return 0-based lap index for a sample index."""
    for i in range(len(boundaries) - 1):
        if boundaries[i] <= sample_idx < boundaries[i + 1]:
            return i
    return max(0, len(boundaries) - 2)


def _check_ride_height_trend(report: SuspensionReport) -> None:
    """Infer ride height trend from deflection progression across laps."""
    lr = report.corners.get('LR')
    rr = report.corners.get('RR')
    if not lr or not rr or not lr.has_data or not rr.has_data:
        return
    rear_laps = [(a + b) / 2 for a, b in zip(lr.lap_mean_defl, rr.lap_mean_defl)]
    if len(rear_laps) < 3:
        return
    first_half = np.mean(rear_laps[:len(rear_laps)//2])
    second_half = np.mean(rear_laps[len(rear_laps)//2:])
    diff = second_half - first_half
    if abs(diff) < 1.0:
        report.ride_height_trend = 'stable'
    elif diff > 0:
        report.ride_height_trend = 'rising (fuel load decreasing?)'
    else:
        report.ride_height_trend = 'falling (check ride height setting)'


def _check_mismatch(report: SuspensionReport) -> None:
    """Detect left/right damper mismatch."""
    pairs = [('LF', 'RF'), ('LR', 'RR')]
    warnings = []
    for left, right in pairs:
        lc = report.corners.get(left)
        rc = report.corners.get(right)
        if not lc or not rc or not lc.has_data or not rc.has_data:
            continue
        if lc.mean_defl_mm == 0 or rc.mean_defl_mm == 0:
            continue
        ratio = abs(lc.mean_defl_mm - rc.mean_defl_mm) / max(lc.mean_defl_mm, rc.mean_defl_mm)
        if ratio > 0.15:
            higher = left if lc.mean_defl_mm > rc.mean_defl_mm else right
            warnings.append(f"{left}/{right} mismatch — {higher} compressing more")
    if warnings:
        report.mismatch_warning = "  |  ".join(warnings)
