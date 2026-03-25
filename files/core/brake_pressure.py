"""
Brake Pressure Analyzer
=======================
Analyzes front brake line pressure channels (LFbrakeLinePress, RFbrakeLinePress)
to verify brake balance matches dcBrakeBias setting, detect brake fade (pressure
drop mid-application), and identify hard braking zones.

iRacing channel units: kPa (kilopascals)
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from core.ibt_parser import TelemetryData

MIN_SAMPLES = 300
SPEED_MIN_MS = 15.0         # ignore below ~54 kph
BRAKE_ACTIVE_THRESH = 200.0  # kPa — consider brake "applied" above this
FADE_DROP_RATE = -50.0       # kPa/s — pressure falling during sustained braking = fade
N_BINS = 200


@dataclass
class BrakeZone:
    lap_dist_pct: float
    lap: int
    max_pressure_kpa: float   # peak pressure in this zone
    duration_frames: int
    fade_detected: bool
    lf_fraction: float        # LF share of total pressure (actual balance)
    rf_fraction: float


@dataclass
class BrakePressureReport:
    has_data: bool = False
    has_lf: bool = False
    has_rf: bool = False

    # Balance stats
    avg_lf_fraction: float = 0.0   # average front-left share of brake pressure
    avg_rf_fraction: float = 0.0
    avg_front_bias:  float = 0.0   # (LF+RF) / total if rear channels available
    bias_vs_setting: float = 0.0   # actual - dcBrakeBias setting (if available)

    # Per-zone records
    brake_zones: List[BrakeZone] = field(default_factory=list)

    # Fade events
    fade_count: int = 0
    fade_zones: List[float] = field(default_factory=list)  # track pcts where fade occurred

    # Track-position pressure map
    bin_edges: List[float] = field(default_factory=list)
    lf_pressure_map: List[float] = field(default_factory=list)
    rf_pressure_map: List[float] = field(default_factory=list)

    # Stats
    peak_pressure_kpa: float = 0.0
    avg_application_kpa: float = 0.0
    hard_brake_count: int = 0     # applications above 800 kPa

    summary: str = ""


class BrakePressureAnalyzer:

    def analyze(self, data: TelemetryData) -> BrakePressureReport:
        report = BrakePressureReport()

        lf_ch    = data.get_channel('LFbrakeLinePress')
        rf_ch    = data.get_channel('RFbrakeLinePress')
        dist_ch  = data.get_channel('LapDistPct')
        speed_ch = data.get_channel('Speed')
        time_ch  = data.get_channel('SessionTime')
        bias_ch  = data.get_channel('dcBrakeBias')

        if dist_ch is None or (lf_ch is None and rf_ch is None):
            return report
        if len(dist_ch) < MIN_SAMPLES:
            return report

        report.has_data = True
        report.has_lf = lf_ch is not None
        report.has_rf = rf_ch is not None

        dist  = dist_ch.astype(float)
        speed = speed_ch.astype(float) if speed_ch is not None else np.ones(len(dist)) * 30
        moving = speed > SPEED_MIN_MS

        lf = lf_ch.astype(float) if lf_ch is not None else np.zeros(len(dist))
        rf = rf_ch.astype(float) if rf_ch is not None else np.zeros(len(dist))
        lf = np.clip(lf, 0, 20000)  # sanity: max 20 MPa
        rf = np.clip(rf, 0, 20000)

        total = lf + rf
        brake_active = (total > BRAKE_ACTIVE_THRESH) & moving

        # ── Balance ───────────────────────────────────────────────────────────
        active_total = total[brake_active]
        active_lf    = lf[brake_active]
        active_rf    = rf[brake_active]
        if len(active_total) > 10 and np.mean(active_total) > 0:
            safe_total = np.where(active_total > 0, active_total, 1)
            report.avg_lf_fraction = float(np.mean(active_lf / safe_total))
            report.avg_rf_fraction = float(np.mean(active_rf / safe_total))
            report.avg_front_bias  = report.avg_lf_fraction + report.avg_rf_fraction

        # Bias vs setting
        if bias_ch is not None and len(bias_ch) > 0:
            avg_setting = float(np.mean(bias_ch[brake_active])) if np.any(brake_active) else 0.0
            if avg_setting > 0:
                # dcBrakeBias is front bias fraction (0.5 = 50/50)
                report.bias_vs_setting = report.avg_front_bias - avg_setting

        # ── Stats ─────────────────────────────────────────────────────────────
        if np.any(brake_active):
            report.peak_pressure_kpa  = float(np.max(total[brake_active]))
            report.avg_application_kpa = float(np.mean(total[brake_active]))
            report.hard_brake_count   = int(np.sum(total > 800) & np.sum(moving))

        # ── Track-position map ────────────────────────────────────────────────
        bins    = np.linspace(0, 1, N_BINS + 1)
        bin_idx = np.clip(np.digitize(dist, bins) - 1, 0, N_BINS - 1)
        report.bin_edges = bins.tolist()

        lf_sum = np.zeros(N_BINS); rf_sum = np.zeros(N_BINS)
        cnt    = np.zeros(N_BINS)
        np.add.at(lf_sum, bin_idx[brake_active], lf[brake_active])
        np.add.at(rf_sum, bin_idx[brake_active], rf[brake_active])
        np.add.at(cnt,    bin_idx[brake_active], 1)
        safe = np.where(cnt > 0, cnt, 1)
        report.lf_pressure_map = (lf_sum / safe).tolist()
        report.rf_pressure_map = (rf_sum / safe).tolist()

        # ── Brake zones ───────────────────────────────────────────────────────
        boundaries = data.lap_boundaries or []
        _extract_brake_zones(report, lf, rf, total, dist, brake_active, time_ch, boundaries)

        # ── Summary ───────────────────────────────────────────────────────────
        parts = []
        if report.peak_pressure_kpa > 0:
            parts.append(f"Peak: {report.peak_pressure_kpa:.0f} kPa")
        if report.avg_lf_fraction > 0:
            parts.append(f"LF/RF balance: {report.avg_lf_fraction*100:.0f}%/{report.avg_rf_fraction*100:.0f}%")
        if abs(report.bias_vs_setting) > 0.01:
            diff_pct = report.bias_vs_setting * 100
            parts.append(f"Bias vs setting: {diff_pct:+.1f}%")
        if report.fade_count > 0:
            parts.append(f"⚠ {report.fade_count} fade events")
        report.summary = "  |  ".join(parts) if parts else "No brake pressure data"
        return report


def _extract_brake_zones(
    report: BrakePressureReport,
    lf: np.ndarray, rf: np.ndarray, total: np.ndarray,
    dist: np.ndarray,
    brake_active: np.ndarray,
    time_ch,
    boundaries: list,
) -> None:
    """Find contiguous brake applications and record them as BrakeZone objects."""
    in_zone = False
    zone_start = 0

    for i in range(len(brake_active)):
        if brake_active[i] and not in_zone:
            in_zone = True
            zone_start = i
        elif not brake_active[i] and in_zone:
            in_zone = False
            duration = i - zone_start
            if duration < 5:
                continue

            seg_total = total[zone_start:i]
            seg_lf    = lf[zone_start:i]
            seg_rf    = rf[zone_start:i]
            peak      = float(np.max(seg_total))

            # Fade check: is pressure declining during this application?
            fade = False
            if time_ch is not None and len(seg_total) >= 10:
                # Linear regression of pressure over time
                t_seg = np.arange(len(seg_total), dtype=float)
                slope = float(np.polyfit(t_seg, seg_total, 1)[0])
                # Pressure should rise then hold; if it keeps falling, that's fade
                if slope < FADE_DROP_RATE / 60:  # per frame to per second
                    fade = True
                    report.fade_count += 1
                    report.fade_zones.append(float(dist[zone_start]))

            avg_total_seg = float(np.mean(seg_total)) if np.mean(seg_total) > 0 else 1.0
            lf_frac = float(np.mean(seg_lf)) / avg_total_seg
            rf_frac = float(np.mean(seg_rf)) / avg_total_seg

            lap_idx = _find_lap(zone_start, boundaries)
            report.brake_zones.append(BrakeZone(
                lap_dist_pct=float(dist[zone_start]),
                lap=lap_idx + 1,
                max_pressure_kpa=round(peak, 0),
                duration_frames=duration,
                fade_detected=fade,
                lf_fraction=round(lf_frac, 3),
                rf_fraction=round(rf_frac, 3),
            ))
    # Cap at 50 zones
    report.brake_zones = report.brake_zones[:50]


def _find_lap(sample_idx: int, boundaries: list) -> int:
    for i in range(len(boundaries) - 1):
        if boundaries[i] <= sample_idx < boundaries[i + 1]:
            return i
    return max(0, len(boundaries) - 2)
