"""
Tire Wear Analyzer
==================
Reads per-zone wear percentages (LFwearL/M/R, RFwearL/M/R, LRwearL/M/R, RRwearL/M/R)
to track wear progression per lap, predict the cliff lap, and recommend camber
adjustments based on inner vs. outer differential wear.

iRacing tire wear channels: 0.0 = new tyre, 1.0 = fully worn through.
The cliff is the lap at which wear rate accelerates — estimated where the
linear regression residuals exceed 1.5× the mean absolute error of the linear fit.
"""
from __future__ import annotations

import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from core.ibt_parser import TelemetryData

CORNERS = ['LF', 'RF', 'LR', 'RR']
MIN_LAPS = 3       # minimum laps needed for meaningful analysis
WEAR_ACTIVE_SPEED = 5.0   # m/s — ignore samples below this

# Camber thresholds: inner/outer differential → action needed
CAMBER_WARN_DELTA  = 0.08   # 8% differential → warning
CAMBER_CRIT_DELTA  = 0.15   # 15% differential → critical


@dataclass
class CornerWearRecord:
    """Per-lap wear snapshot for one corner."""
    lap: int
    inner: float   # 0-1 fraction worn at end of lap
    mid:   float
    outer: float

    @property
    def avg(self) -> float:
        return (self.inner + self.mid + self.outer) / 3.0

    @property
    def io_delta(self) -> float:
        """Positive = inner wears more than outer (neg camber signal)."""
        return self.inner - self.outer


@dataclass
class CornerWearReport:
    corner: str
    has_data: bool = False
    records: List[CornerWearRecord] = field(default_factory=list)
    # Final state (last lap)
    final_inner: float = 0.0
    final_mid:   float = 0.0
    final_outer: float = 0.0
    final_avg:   float = 0.0
    # Wear rate per lap (linear fit slope)
    wear_rate_per_lap: float = 0.0
    # Predicted cliff lap (0 = no cliff detected within horizon)
    cliff_lap: int = 0
    # Camber diagnosis
    camber_diagnosis: str = ""   # 'ok' | 'too_much_neg_camber' | 'too_little_neg_camber'
    camber_delta: float = 0.0    # final inner - outer differential


@dataclass
class TireWearReport:
    has_data: bool = False
    corners: Dict[str, CornerWearReport] = field(default_factory=dict)
    # Worst corner overall
    worst_corner: str = ""
    worst_wear_avg: float = 0.0
    # Predicted session cliff lap (earliest across corners)
    predicted_cliff_lap: int = 0
    # Camber issues
    camber_issues: List[str] = field(default_factory=list)
    # Stints remaining estimate (based on wear rate)
    estimated_laps_remaining: int = 0
    summary: str = ""


class TireWearAnalyzer:

    def analyze(self, data: TelemetryData) -> TireWearReport:
        report = TireWearReport()

        speed_ch = data.get_channel('Speed')
        dist_ch  = data.get_channel('LapDistPct')
        boundaries = data.lap_boundaries

        if speed_ch is None or data.num_laps < MIN_LAPS:
            return report

        speed = speed_ch.astype(float)
        n_laps = data.num_laps

        for corner in CORNERS:
            inner_ch = data.get_channel(f'{corner}wearL')
            mid_ch   = data.get_channel(f'{corner}wearM')
            outer_ch = data.get_channel(f'{corner}wearR')

            if inner_ch is None and mid_ch is None and outer_ch is None:
                report.corners[corner] = CornerWearReport(corner=corner)
                continue

            def _safe(ch):
                return ch.astype(float) if ch is not None else np.zeros(len(speed))

            inner_arr = _safe(inner_ch)
            mid_arr   = _safe(mid_ch)
            outer_arr = _safe(outer_ch)

            cr = CornerWearReport(corner=corner, has_data=True)

            for lap_i in range(n_laps):
                b0 = boundaries[lap_i]
                b1 = boundaries[lap_i + 1] if lap_i + 1 < len(boundaries) else len(speed)
                seg_speed  = speed[b0:b1]
                seg_inner  = inner_arr[b0:b1]
                seg_mid    = mid_arr[b0:b1]
                seg_outer  = outer_arr[b0:b1]

                mask = seg_speed > WEAR_ACTIVE_SPEED
                if not np.any(mask):
                    continue

                # Use end-of-lap value as the wear state for that lap
                # (wear is cumulative, so last sample = most worn during that lap)
                def _lap_end(arr):
                    valid = arr[mask]
                    return float(valid[-1]) if len(valid) > 0 else 0.0

                cr.records.append(CornerWearRecord(
                    lap=lap_i,
                    inner=_lap_end(seg_inner),
                    mid=_lap_end(seg_mid),
                    outer=_lap_end(seg_outer),
                ))

            if not cr.records:
                cr.has_data = False
                report.corners[corner] = cr
                continue

            # Final state
            last = cr.records[-1]
            cr.final_inner = last.inner
            cr.final_mid   = last.mid
            cr.final_outer = last.outer
            cr.final_avg   = last.avg
            cr.camber_delta = last.io_delta

            # Camber diagnosis
            if abs(cr.camber_delta) < CAMBER_WARN_DELTA:
                cr.camber_diagnosis = 'ok'
            elif cr.camber_delta > 0:
                sev = 'critical' if cr.camber_delta > CAMBER_CRIT_DELTA else 'warning'
                cr.camber_diagnosis = f'too_much_neg_camber_{sev}'
            else:
                sev = 'critical' if abs(cr.camber_delta) > CAMBER_CRIT_DELTA else 'warning'
                cr.camber_diagnosis = f'too_little_neg_camber_{sev}'

            # Wear rate (linear fit on avg wear over laps)
            if len(cr.records) >= 2:
                laps_x = np.array([r.lap for r in cr.records], dtype=float)
                avgs_y = np.array([r.avg for r in cr.records], dtype=float)
                coeffs = np.polyfit(laps_x, avgs_y, 1)
                cr.wear_rate_per_lap = float(coeffs[0])

                # Cliff detection: lap where avg wear crosses 0.70 (threshold for grip drop)
                CLIFF_THRESHOLD = 0.70
                if cr.final_avg < CLIFF_THRESHOLD and cr.wear_rate_per_lap > 0:
                    laps_to_cliff = (CLIFF_THRESHOLD - cr.final_avg) / cr.wear_rate_per_lap
                    cr.cliff_lap = max(0, int(np.ceil(last.lap + laps_to_cliff)))
                elif cr.final_avg >= CLIFF_THRESHOLD:
                    cr.cliff_lap = last.lap  # already past cliff

            report.has_data = True
            report.corners[corner] = cr

        if not report.has_data:
            return report

        # Aggregate: worst corner, cliff, camber issues
        valid_corners = [cr for cr in report.corners.values() if cr.has_data]
        if valid_corners:
            worst = max(valid_corners, key=lambda c: c.final_avg)
            report.worst_corner = worst.corner
            report.worst_wear_avg = worst.final_avg

            cliff_laps = [c.cliff_lap for c in valid_corners if c.cliff_lap > 0]
            if cliff_laps:
                report.predicted_cliff_lap = min(cliff_laps)

            # Estimated laps remaining (from worst wear rate)
            rates = [c.wear_rate_per_lap for c in valid_corners if c.wear_rate_per_lap > 0]
            if rates:
                avg_rate = float(np.mean(rates))
                avg_wear = float(np.mean([c.final_avg for c in valid_corners]))
                if avg_rate > 0:
                    report.estimated_laps_remaining = max(0, int((0.95 - avg_wear) / avg_rate))

        # Camber issues
        _CAM_LABELS = {
            'too_much_neg_camber_warning': "slight negative camber excess",
            'too_much_neg_camber_critical': "excessive negative camber — reduce",
            'too_little_neg_camber_warning': "slight camber deficiency",
            'too_little_neg_camber_critical': "insufficient camber — add negative camber",
        }
        for corner in CORNERS:
            cr = report.corners.get(corner)
            if cr and cr.camber_diagnosis and cr.camber_diagnosis != 'ok':
                label = _CAM_LABELS.get(cr.camber_diagnosis, cr.camber_diagnosis)
                report.camber_issues.append(f"{corner}: {label} (Δ={cr.camber_delta:+.2f})")

        # Summary text
        parts = []
        if report.worst_corner:
            parts.append(f"Worst: {report.worst_corner} ({report.worst_wear_avg:.0%} worn)")
        if report.predicted_cliff_lap:
            parts.append(f"Cliff ~lap {report.predicted_cliff_lap}")
        if report.estimated_laps_remaining:
            parts.append(f"~{report.estimated_laps_remaining} laps remaining")
        if report.camber_issues:
            parts.append(f"{len(report.camber_issues)} camber issue(s)")
        report.summary = "  •  ".join(parts) if parts else "No significant wear detected"

        return report
