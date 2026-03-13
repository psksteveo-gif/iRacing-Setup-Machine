"""
G-G Diagram per Corner — Friction circle analysis for individual corners.
Extracts lateral and longitudinal G-forces per corner zone.
"""

import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class CornerGG:
    """G-G data for a single corner."""
    corner_num: int
    lat_g: np.ndarray            # lateral acceleration samples
    long_g: np.ndarray           # longitudinal acceleration samples
    speed: np.ndarray            # speed at each sample
    max_lat_g: float
    max_long_g: float
    max_combined_g: float        # max sqrt(lat^2 + long^2)
    avg_combined_g: float
    utilization_pct: float       # % of friction circle used


@dataclass
class GGReport:
    """G-G analysis across all corners."""
    corners: List[CornerGG]
    overall_max_lat: float
    overall_max_long: float
    overall_max_combined: float
    overall_utilization: float
    findings: List[str] = field(default_factory=list)


def analyze_gg_per_corner(data, corner_zones=None) -> Optional[GGReport]:
    """
    Compute G-G data for each corner zone.

    Parameters
    ----------
    data : TelemetryData
    corner_zones : list of (brake_pct, apex_pct, exit_pct) — if None, auto-detects

    Returns GGReport or None.
    """
    lat_ch = data.get_channel('LatAccel')
    long_ch = data.get_channel('LongAccel')
    speed_ch = data.get_channel('Speed')
    ld = data.get_channel('LapDistPct')
    if lat_ch is None or long_ch is None or ld is None:
        return None
    if data.num_laps < 1:
        return None

    if corner_zones is None:
        corner_zones = _auto_detect_corners(data)
    if not corner_zones:
        return None

    corners: List[CornerGG] = []
    all_combined = []

    for ci, (bp, ap, ep) in enumerate(corner_zones):
        lat_samples = []
        long_samples = []
        spd_samples = []

        for li in range(data.num_laps):
            s = data.lap_boundaries[li]
            e = data.lap_boundaries[li + 1]
            lap_ld = ld[s:e]
            mask = (lap_ld >= bp) & (lap_ld <= ep)
            if np.sum(mask) < 3:
                continue
            lat_samples.append(lat_ch[s:e][mask])
            long_samples.append(long_ch[s:e][mask])
            spd_samples.append(speed_ch[s:e][mask] if speed_ch is not None else np.zeros(np.sum(mask)))

        if not lat_samples:
            continue

        lat_arr = np.concatenate(lat_samples)
        long_arr = np.concatenate(long_samples)
        spd_arr = np.concatenate(spd_samples)

        combined = np.sqrt(lat_arr**2 + long_arr**2)
        max_comb = float(np.max(combined)) if len(combined) > 0 else 0.0
        avg_comb = float(np.mean(combined)) if len(combined) > 0 else 0.0
        all_combined.extend(combined.tolist())

        # Friction circle utilization: how much of the max-G envelope is used
        # Compute as: average combined / max combined
        util = (avg_comb / max_comb * 100) if max_comb > 0 else 0.0

        corners.append(CornerGG(
            corner_num=ci + 1,
            lat_g=lat_arr,
            long_g=long_arr,
            speed=spd_arr,
            max_lat_g=float(np.max(np.abs(lat_arr))) if len(lat_arr) > 0 else 0.0,
            max_long_g=float(np.max(np.abs(long_arr))) if len(long_arr) > 0 else 0.0,
            max_combined_g=max_comb,
            avg_combined_g=avg_comb,
            utilization_pct=util,
        ))

    if not corners:
        return None

    overall_lat = max(c.max_lat_g for c in corners)
    overall_long = max(c.max_long_g for c in corners)
    overall_comb = max(c.max_combined_g for c in corners)
    overall_util = float(np.mean([c.utilization_pct for c in corners]))

    findings = _generate_findings(corners, overall_util)

    return GGReport(
        corners=corners,
        overall_max_lat=overall_lat,
        overall_max_long=overall_long,
        overall_max_combined=overall_comb,
        overall_utilization=overall_util,
        findings=findings,
    )


def _auto_detect_corners(data) -> List[Tuple[float, float, float]]:
    """Simple brake-zone corner detection for GG analysis."""
    brake = data.get_channel('Brake')
    speed = data.get_channel('Speed')
    ld = data.get_channel('LapDistPct')
    if brake is None or speed is None or ld is None:
        return []

    # Use first lap
    s = data.lap_boundaries[0]
    e = data.lap_boundaries[1] if data.num_laps > 0 else len(brake)
    lap_brk = brake[s:e]
    lap_spd = speed[s:e]
    lap_ld = ld[s:e]

    zones = []
    is_braking = lap_brk > 0.10
    in_zone = False
    zone_start = 0
    for i in range(len(is_braking)):
        if is_braking[i] and not in_zone:
            zone_start = i
            in_zone = True
        elif not is_braking[i] and in_zone:
            if i - zone_start >= 20:
                extend = min(len(lap_spd), i + (i - zone_start))
                apex_idx = zone_start + np.argmin(lap_spd[zone_start:extend])
                exit_idx = min(extend, apex_idx + (apex_idx - zone_start))
                zones.append((
                    float(lap_ld[zone_start]),
                    float(lap_ld[min(apex_idx, len(lap_ld) - 1)]),
                    float(lap_ld[min(exit_idx, len(lap_ld) - 1)]),
                ))
            in_zone = False
    return zones


def _generate_findings(corners: List[CornerGG], overall_util: float) -> List[str]:
    findings = []
    if overall_util > 80:
        findings.append("Excellent tire utilization — driving near the friction limit.")
    elif overall_util > 60:
        findings.append("Good tire utilization. Some corners have room for more aggressive driving.")
    else:
        findings.append("Low friction circle utilization — you can push harder in corners.")

    # Find weakest corner
    worst = min(corners, key=lambda c: c.utilization_pct)
    if worst.utilization_pct < overall_util - 10:
        findings.append(
            f"Corner {worst.corner_num} has the lowest utilization ({worst.utilization_pct:.0f}%) — "
            f"focus on carrying more speed or braking later here."
        )

    # Max G stats
    best = max(corners, key=lambda c: c.max_combined_g)
    findings.append(
        f"Highest combined G: {best.max_combined_g:.2f}G in Corner {best.corner_num}."
    )

    return findings
