"""
Incident Analyzer
=================
Tracks PlayerCarDriverIncidentCount to detect exactly when incidents occur,
mapping each to lap number, track position, and severity.

iRacing incident point values:
  1x — off-track or minor contact
  2x — moderate contact
  4x — hard contact with wall or another car

The raw channel is cumulative, so incidents are detected as positive deltas.
"""
from __future__ import annotations

import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional
from core.ibt_parser import TelemetryData

N_BINS = 200
MIN_SAMPLES = 60   # need at least 60 samples to be meaningful


@dataclass
class Incident:
    lap: int
    lap_dist_pct: float   # 0-1
    session_time_s: float
    severity: int         # 1, 2, or 4 (iRacing incident points)
    label: str            # 'minor' | 'moderate' | 'contact'


@dataclass
class IncidentReport:
    has_data: bool = False
    incidents: List[Incident] = field(default_factory=list)
    total_points: int = 0
    total_incidents: int = 0
    # Per-lap counts
    by_lap: List[int] = field(default_factory=list)   # incident points per lap
    # Track-position heatmap (0-1 intensity per bin)
    heatmap: List[float] = field(default_factory=list)
    bin_edges: List[float] = field(default_factory=list)
    # Worst zone
    worst_zone_pct: float = 0.0
    worst_lap: int = 0
    summary: str = ""


class IncidentAnalyzer:

    def analyze(self, data: TelemetryData) -> IncidentReport:
        report = IncidentReport()

        inc_ch  = data.get_channel('PlayerCarDriverIncidentCount')
        dist_ch = data.get_channel('LapDistPct')
        time_ch = data.get_channel('SessionTime')

        if inc_ch is None or len(inc_ch) < MIN_SAMPLES:
            return report

        inc  = inc_ch.astype(float)
        dist = dist_ch.astype(float) if dist_ch is not None else np.zeros(len(inc))
        t    = time_ch.astype(float)  if time_ch is not None else np.arange(len(inc), dtype=float)

        boundaries = data.lap_boundaries
        n_laps = data.num_laps

        # Detect positive deltas (incident events)
        deltas = np.diff(inc, prepend=inc[0])
        # Snap to valid values: 1, 2, 4 — filter noise
        valid_magnitudes = {1, 2, 4}
        event_indices = [i for i in range(1, len(deltas))
                         if int(round(deltas[i])) in valid_magnitudes]

        if not event_indices:
            report.has_data = (len(inc) > MIN_SAMPLES)
            report.summary = "No incidents recorded"
            return report

        report.has_data = True

        for idx in event_indices:
            sev = int(round(deltas[idx]))
            lap_idx = _find_lap(int(idx), boundaries)
            label = {1: 'minor', 2: 'moderate', 4: 'contact'}.get(sev, 'unknown')
            report.incidents.append(Incident(
                lap=lap_idx,
                lap_dist_pct=round(float(dist[idx]), 3),
                session_time_s=round(float(t[idx]), 1),
                severity=sev,
                label=label,
            ))

        report.total_incidents = len(report.incidents)
        report.total_points    = sum(i.severity for i in report.incidents)

        # Per-lap points
        report.by_lap = [0] * n_laps
        for inc_ev in report.incidents:
            if 0 <= inc_ev.lap < n_laps:
                report.by_lap[inc_ev.lap] += inc_ev.severity

        worst_lap_idx = int(np.argmax(report.by_lap)) if report.by_lap else 0
        report.worst_lap = worst_lap_idx

        # Track position heatmap
        bins = np.linspace(0.0, 1.0, N_BINS + 1)
        report.bin_edges = bins.tolist()
        heatmap = np.zeros(N_BINS)
        for inc_ev in report.incidents:
            bin_idx = min(N_BINS - 1, int(inc_ev.lap_dist_pct * N_BINS))
            heatmap[bin_idx] += inc_ev.severity
        # Normalize to 0-1
        mx = heatmap.max()
        if mx > 0:
            heatmap = heatmap / mx
        report.heatmap = heatmap.tolist()

        # Worst zone: track position with highest incident density
        if heatmap.max() > 0:
            report.worst_zone_pct = float((np.argmax(heatmap) + 0.5) / N_BINS)

        # Summary
        labels_count = {}
        for inc_ev in report.incidents:
            labels_count[inc_ev.label] = labels_count.get(inc_ev.label, 0) + 1
        parts = [f"{v} {k}" for k, v in sorted(labels_count.items(), key=lambda x: -x[1])]
        report.summary = (f"{report.total_incidents} incident(s) — {report.total_points}x total  •  "
                          + ", ".join(parts))
        if report.worst_zone_pct > 0:
            report.summary += f"  •  Worst zone: {report.worst_zone_pct*100:.0f}% track"

        return report


def _find_lap(sample_idx: int, boundaries: list) -> int:
    if not boundaries:
        return 0
    for i in range(len(boundaries) - 1):
        if boundaries[i] <= sample_idx < boundaries[i + 1]:
            return i
    return len(boundaries) - 2
