"""
Brake Trace Analysis — Per-corner brake profiling.
Measures initial bite, modulation, trail-brake duration, and release speed.
"""

import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class BrakeProfile:
    """Brake metrics for a single corner across all laps."""
    corner_num: int
    brake_start_pct: float        # track % where braking begins
    apex_pct: float               # track % of apex
    # Metrics (averaged across laps)
    initial_bite: float           # peak brake pressure in first 20% of brake zone (0–1)
    peak_pressure: float          # max brake pressure in zone (0–1)
    modulation_score: float       # 0–100: low variance = smooth = higher score
    trail_brake_pct: float        # % of corner from apex where brake > 5%
    release_speed: float          # rate of brake release (units/sec at 60Hz)
    avg_brake_duration_s: float   # time from first brake to full release
    # Per-lap values
    lap_initial_bites: List[float]
    lap_peak_pressures: List[float]
    lap_trail_pcts: List[float]
    # Coaching
    coaching_note: str = ""


@dataclass
class BrakeAnalysisReport:
    """Full brake analysis across all detected braking zones."""
    profiles: List[BrakeProfile]
    overall_modulation_score: float   # average modulation across all corners
    weakest_corner: int               # corner_num with worst braking
    findings: List[str] = field(default_factory=list)


def analyze_braking(data, corners=None) -> Optional[BrakeAnalysisReport]:
    """
    Analyze brake traces per corner.

    Parameters
    ----------
    data : TelemetryData
    corners : list of (brake_pct, apex_pct, exit_pct) tuples, or None to auto-detect

    Returns None if insufficient data.
    """
    if data.num_laps < 1:
        return None

    brake_ch = data.get_channel('Brake')
    ld = data.get_channel('LapDistPct')
    if brake_ch is None or ld is None:
        return None

    # Auto-detect brake zones if not provided
    if corners is None:
        corners = _detect_brake_zones(data)
    if not corners:
        return None

    profiles: List[BrakeProfile] = []

    for ci, (bp, ap, ep) in enumerate(corners):
        lap_bites: List[float] = []
        lap_peaks: List[float] = []
        lap_trails: List[float] = []
        lap_modulations: List[float] = []
        lap_release_speeds: List[float] = []
        lap_durations: List[float] = []

        for li in range(data.num_laps):
            s = data.lap_boundaries[li]
            e = data.lap_boundaries[li + 1]
            lap_ld = ld[s:e]
            lap_brk = brake_ch[s:e]

            # Samples in brake zone (brake_start to exit)
            mask = (lap_ld >= bp) & (lap_ld <= ep)
            if np.sum(mask) < 5:
                continue
            zone_brk = lap_brk[mask]
            zone_ld = lap_ld[mask]

            # Initial bite: peak in first 20% of brake zone
            zone_len = len(zone_brk)
            first_20 = zone_brk[:max(1, zone_len // 5)]
            bite = float(np.max(first_20))
            lap_bites.append(bite)

            # Peak pressure
            peak = float(np.max(zone_brk))
            lap_peaks.append(peak)

            # Modulation: inverse of variance (smoother = higher)
            if len(zone_brk) > 2:
                diff = np.diff(zone_brk)
                variance = float(np.var(diff))
                # Scale: 0 variance = 100, high variance = low score
                mod = max(0.0, 100.0 - variance * 5000)
                lap_modulations.append(mod)

            # Trail brake: % of post-apex zone where brake > 5%
            post_apex = (zone_ld >= ap) & (zone_brk > 0.05)
            apex_to_exit = zone_ld >= ap
            if np.sum(apex_to_exit) > 0:
                trail = float(np.sum(post_apex) / np.sum(apex_to_exit) * 100)
            else:
                trail = 0.0
            lap_trails.append(trail)

            # Release speed: average derivative in last 30% of brake zone
            last_30 = zone_brk[max(0, int(zone_len * 0.7)):]
            if len(last_30) > 2:
                release = float(np.mean(np.abs(np.diff(last_30)))) * data.tick_rate
            else:
                release = 0.0
            lap_release_speeds.append(release)

            # Duration
            braking_samples = np.sum(zone_brk > 0.05)
            duration = float(braking_samples) / data.tick_rate
            lap_durations.append(duration)

        if not lap_bites:
            continue

        avg_mod = float(np.mean(lap_modulations)) if lap_modulations else 50.0
        avg_release = float(np.mean(lap_release_speeds)) if lap_release_speeds else 0.0
        avg_duration = float(np.mean(lap_durations)) if lap_durations else 0.0

        # Coaching note
        note = _coaching_note(
            float(np.mean(lap_bites)), float(np.mean(lap_peaks)),
            avg_mod, float(np.mean(lap_trails)), avg_release,
        )

        profiles.append(BrakeProfile(
            corner_num=ci + 1,
            brake_start_pct=bp,
            apex_pct=ap,
            initial_bite=float(np.mean(lap_bites)),
            peak_pressure=float(np.mean(lap_peaks)),
            modulation_score=avg_mod,
            trail_brake_pct=float(np.mean(lap_trails)),
            release_speed=avg_release,
            avg_brake_duration_s=avg_duration,
            lap_initial_bites=lap_bites,
            lap_peak_pressures=lap_peaks,
            lap_trail_pcts=lap_trails,
            coaching_note=note,
        ))

    if not profiles:
        return None

    overall_mod = float(np.mean([p.modulation_score for p in profiles]))
    weakest = min(profiles, key=lambda p: p.modulation_score)
    findings = _generate_findings(profiles)

    return BrakeAnalysisReport(
        profiles=profiles,
        overall_modulation_score=overall_mod,
        weakest_corner=weakest.corner_num,
        findings=findings,
    )


def _detect_brake_zones(data) -> List[tuple]:
    """Detect brake zones from telemetry as (brake_pct, apex_pct, exit_pct)."""
    brake = data.get_channel('Brake')
    speed = data.get_channel('Speed')
    ld = data.get_channel('LapDistPct')
    if brake is None or speed is None or ld is None:
        return []

    # Use first lap to detect zones
    s = data.lap_boundaries[0]
    e = data.lap_boundaries[1] if data.num_laps > 0 else len(brake)
    lap_brk = brake[s:e]
    lap_spd = speed[s:e]
    lap_ld = ld[s:e]

    # Find braking events: brake > 0.1 for at least 0.5s (30 samples at 60Hz)
    is_braking = lap_brk > 0.10
    zones = []
    in_zone = False
    zone_start = 0
    for i in range(len(is_braking)):
        if is_braking[i] and not in_zone:
            zone_start = i
            in_zone = True
        elif not is_braking[i] and in_zone:
            if i - zone_start >= 30:
                # Find apex (min speed) in zone + 50% after
                extend = min(len(lap_spd), i + (i - zone_start) // 2)
                apex_idx = zone_start + np.argmin(lap_spd[zone_start:extend])
                exit_idx = min(extend, apex_idx + (apex_idx - zone_start))
                zones.append((
                    float(lap_ld[zone_start]),
                    float(lap_ld[min(apex_idx, len(lap_ld) - 1)]),
                    float(lap_ld[min(exit_idx, len(lap_ld) - 1)]),
                ))
            in_zone = False

    return zones


def _coaching_note(bite: float, peak: float, mod: float,
                   trail: float, release: float) -> str:
    notes = []
    if bite > 0.85:
        notes.append("Strong initial bite — good threshold braking.")
    elif bite < 0.5:
        notes.append("Soft initial brake application. Try hitting the pedal harder initially.")
    if mod > 80:
        notes.append("Smooth brake modulation.")
    elif mod < 50:
        notes.append("Inconsistent brake modulation. Work on smoother pedal control.")
    if trail > 40:
        notes.append("Good trail-braking past the apex — transferring weight to front.")
    elif trail < 10:
        notes.append("Minimal trail-brake. Try maintaining light brake pressure past the apex.")
    if release > 20:
        notes.append("Quick brake release — could unsettle the car. Try releasing more gradually.")
    return " ".join(notes) if notes else "Solid braking technique in this zone."


def _generate_findings(profiles: List[BrakeProfile]) -> List[str]:
    findings = []
    avg_bite = np.mean([p.initial_bite for p in profiles])
    avg_trail = np.mean([p.trail_brake_pct for p in profiles])
    if avg_bite < 0.5:
        findings.append("Overall brake application is soft. Focus on stronger initial threshold braking.")
    if avg_trail < 15:
        findings.append("Trail-braking is under-utilized. Maintaining light brake past the apex helps rotation.")
    low_mod = [p for p in profiles if p.modulation_score < 50]
    if low_mod:
        corners = ", ".join(str(p.corner_num) for p in low_mod)
        findings.append(f"Inconsistent brake modulation in corners: {corners}.")
    return findings
