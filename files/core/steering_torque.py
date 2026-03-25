"""
Steering Torque Analyzer
========================
Analyzes SteeringWheelTorque to detect understeer (torque drops) and
oversteer (torque spikes) zones mapped to track position.

Understeer signature: steering angle is increasing but torque is dropping
  — the front is washing out, so the rack feeds back less force.

Oversteer signature: torque spikes with simultaneous yaw rate increase
  — the rear is stepping out, driver naturally countersteers.
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from core.ibt_parser import TelemetryData

MIN_SAMPLES = 500
SPEED_THRESHOLD_MS = 10.0   # ignore below 36 kph
# Torque thresholds (N·m)
US_DROP_THRESHOLD  = -2.0   # torque drop rate faster than this = understeer
OS_SPIKE_THRESHOLD =  3.0   # torque spike rate faster than this = oversteer

# Number of track-position bins for the heatmap
N_BINS = 200


@dataclass
class TorqueZone:
    lap_dist_pct: float      # track position 0-1
    event_type: str          # 'understeer' | 'oversteer'
    severity: float          # 0-1
    lap: int
    torque_nm: float
    speed_ms: float


@dataclass
class SteeringTorqueReport:
    has_data: bool = False
    # Per-bin heatmap: 0-1 (fraction of time each bin had significant torque anomaly)
    understeer_map: List[float] = field(default_factory=list)   # len=N_BINS
    oversteer_map:  List[float] = field(default_factory=list)   # len=N_BINS
    bin_edges: List[float] = field(default_factory=list)        # len=N_BINS+1

    # Top zones
    worst_us_pct: float = 0.0   # track position % of worst understeer
    worst_os_pct: float = 0.0   # track position % of worst oversteer
    events: List[TorqueZone] = field(default_factory=list)

    # Overall stats
    us_fraction: float = 0.0    # fraction of laps with significant understeer
    os_fraction: float = 0.0
    avg_torque_nm: float = 0.0
    peak_torque_nm: float = 0.0

    # Summaries
    balance_summary: str = ""
    setup_hint: str = ""


class SteeringTorqueAnalyzer:

    def analyze(self, data: TelemetryData) -> SteeringTorqueReport:
        report = SteeringTorqueReport()

        torque_ch = data.get_channel('SteeringWheelTorque')
        steer_ch  = data.get_channel('SteeringWheelAngle')
        speed_ch  = data.get_channel('Speed')
        lap_dist  = data.get_channel('LapDistPct')

        if torque_ch is None or len(torque_ch) < MIN_SAMPLES:
            return report
        if lap_dist is None or speed_ch is None:
            return report

        report.has_data = True
        torque = torque_ch.astype(float)
        speed  = speed_ch.astype(float)
        dist   = lap_dist.astype(float)

        # Only analyse above speed threshold
        moving = speed > SPEED_THRESHOLD_MS

        report.avg_torque_nm  = float(np.mean(np.abs(torque[moving]))) if np.any(moving) else 0.0
        report.peak_torque_nm = float(np.max(np.abs(torque[moving])))  if np.any(moving) else 0.0

        # Rate of torque change (N·m per frame)
        torque_rate = np.gradient(torque)

        # Build heatmap bins
        bins = np.linspace(0.0, 1.0, N_BINS + 1)
        report.bin_edges = bins.tolist()

        us_counts  = np.zeros(N_BINS)
        os_counts  = np.zeros(N_BINS)
        total_counts = np.zeros(N_BINS)

        bin_idx = np.digitize(dist, bins) - 1
        bin_idx = np.clip(bin_idx, 0, N_BINS - 1)

        us_mask = (torque_rate < US_DROP_THRESHOLD) & moving
        os_mask = (torque_rate > OS_SPIKE_THRESHOLD) & moving

        np.add.at(us_counts,    bin_idx[us_mask],    1)
        np.add.at(os_counts,    bin_idx[os_mask],    1)
        np.add.at(total_counts, bin_idx[moving],     1)

        safe_total = np.where(total_counts > 0, total_counts, 1)
        report.understeer_map = (us_counts / safe_total).tolist()
        report.oversteer_map  = (os_counts / safe_total).tolist()

        # Worst zones
        if np.max(us_counts) > 0:
            worst_us_bin = int(np.argmax(us_counts))
            report.worst_us_pct = float(bins[worst_us_bin] + 0.5 / N_BINS)
        if np.max(os_counts) > 0:
            worst_os_bin = int(np.argmax(os_counts))
            report.worst_os_pct = float(bins[worst_os_bin] + 0.5 / N_BINS)

        # Overall fractions
        n_moving = max(int(np.sum(moving)), 1)
        report.us_fraction = float(np.sum(us_mask)) / n_moving
        report.os_fraction = float(np.sum(os_mask)) / n_moving

        # Per-event records (top 15 events each)
        boundaries = data.lap_boundaries or []
        _record_events(report, torque_rate, dist, speed, torque, moving,
                       us_mask, os_mask, boundaries)

        # Summaries
        _build_summary(report)
        return report


def _record_events(
    report: SteeringTorqueReport,
    torque_rate: np.ndarray,
    dist: np.ndarray,
    speed: np.ndarray,
    torque: np.ndarray,
    moving: np.ndarray,
    us_mask: np.ndarray,
    os_mask: np.ndarray,
    boundaries: list,
) -> None:
    for mask, etype in [(us_mask, 'understeer'), (os_mask, 'oversteer')]:
        indices = np.where(mask)[0]
        # Debounce: min 20 frames between events
        prev = -100
        count = 0
        for idx in indices:
            i = int(idx)
            if i - prev < 20:
                continue
            prev = i
            lap_idx = _find_lap(i, boundaries)
            severity = min(1.0, abs(float(torque_rate[i])) /
                          (abs(US_DROP_THRESHOLD) if etype == 'understeer' else OS_SPIKE_THRESHOLD) / 3)
            report.events.append(TorqueZone(
                lap_dist_pct=float(dist[i]),
                event_type=etype,
                severity=round(severity, 3),
                lap=lap_idx + 1,
                torque_nm=round(float(torque[i]), 2),
                speed_ms=round(float(speed[i]), 1),
            ))
            count += 1
            if count >= 15:
                break


def _build_summary(report: SteeringTorqueReport) -> None:
    us_pct = report.us_fraction * 100
    os_pct = report.os_fraction * 100

    if us_pct > os_pct * 2 and us_pct > 1.0:
        report.balance_summary = f"Predominantly understeering — {us_pct:.1f}% of cornering time"
        report.setup_hint = (
            "Reduce front ARB stiffness, increase front wing (if available), "
            "or increase front tire pressure to sharpen turn-in."
        )
    elif os_pct > us_pct * 2 and os_pct > 1.0:
        report.balance_summary = f"Predominantly oversteering — {os_pct:.1f}% of cornering time"
        report.setup_hint = (
            "Increase rear ARB stiffness, reduce rear wing angle, "
            "or check rear tire pressures are not too high."
        )
    elif us_pct < 0.5 and os_pct < 0.5:
        report.balance_summary = "Neutral balance — minimal torque anomalies detected"
        report.setup_hint = "Setup is well-balanced — focus on driver technique refinement."
    else:
        report.balance_summary = (
            f"Mixed balance: {us_pct:.1f}% understeer / {os_pct:.1f}% oversteer"
        )
        report.setup_hint = (
            f"Worst understeer at {report.worst_us_pct*100:.0f}% track — "
            f"worst oversteer at {report.worst_os_pct*100:.0f}% track. "
            "Check corner-specific setup: ARB, spring rates, differential."
        )


def _find_lap(sample_idx: int, boundaries: list) -> int:
    for i in range(len(boundaries) - 1):
        if boundaries[i] <= sample_idx < boundaries[i + 1]:
            return i
    return max(0, len(boundaries) - 2)
