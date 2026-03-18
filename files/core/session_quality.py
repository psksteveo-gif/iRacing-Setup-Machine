"""
Session Quality Analyzer
========================
Two independent analyzers that clean up and contextualize session statistics:

1. IncidentDetector
   Flags laps that contain hard-contact events (G-spike) or track resets
   (LapDistPct jumps backward mid-lap) so they can be excluded from
   consistency scores, tire averages, and AI prompts.

2. TrackEvolutionAnalyzer
   Detects whether the track is "rubbering in" — i.e., lap times are
   systematically improving due to grip build-up rather than driver
   improvement.  Separates track evolution from genuine skill gains.
"""

import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from core.ibt_parser import TelemetryData  # type: ignore[import-unresolved]


# ─────────────────────────────────────────────────────────────────────────────
# Section 1 — Incident / Slow-Lap Detection
# ─────────────────────────────────────────────────────────────────────────────

# Thresholds
_IMPACT_LONG_G      = 3.5   # longitudinal deceleration (g) that suggests contact
_IMPACT_LAT_G       = 4.5   # lateral spike that suggests contact / wall tap
_IMPACT_MIN_DUR_S   = 0.05  # impact must persist at least this many seconds
_RESET_DIST_JUMP    = 0.10  # LapDistPct drops by this much → assumed track reset
_SLOW_LAP_FACTOR    = 1.25  # lap time > median * this → flagged as slow/incident lap


@dataclass
class IncidentEvent:
    """A single detected incident within a lap."""
    lap_idx: int
    lap_dist_pct: float          # approximate position around the track
    session_time_s: float        # absolute session timestamp
    type: str                    # "impact_lateral" | "impact_longitudinal" | "track_reset"
    magnitude: float             # G reading or dist-jump magnitude


@dataclass
class LapQuality:
    """Quality assessment for one lap."""
    lap_idx: int
    lap_time_s: float
    is_incident: bool = False
    is_slow: bool = False
    incidents: List[IncidentEvent] = field(default_factory=list)
    exclude_reason: str = ""     # human-readable reason for exclusion

    @property
    def is_clean(self) -> bool:
        return not self.is_incident and not self.is_slow


@dataclass
class IncidentReport:
    laps: List[LapQuality] = field(default_factory=list)
    clean_lap_indices: List[int] = field(default_factory=list)
    incident_lap_indices: List[int] = field(default_factory=list)
    slow_lap_indices: List[int] = field(default_factory=list)
    total_incidents: int = 0

    @property
    def clean_lap_times(self) -> List[float]:
        return [lq.lap_time_s for lq in self.laps if lq.is_clean]

    def summary_text(self) -> str:
        """Short text for the AI prompt."""
        if not self.laps:
            return ""
        lines = []
        if self.incident_lap_indices:
            lines.append(
                f"Incident laps (excluded from stats): "
                f"{[i+1 for i in self.incident_lap_indices]} "
                f"({self.total_incidents} events)"
            )
        if self.slow_lap_indices:
            lines.append(
                f"Slow / outlier laps (excluded from averages): "
                f"{[i+1 for i in self.slow_lap_indices]}"
            )
        clean = len(self.clean_lap_indices)
        total = len(self.laps)
        lines.append(f"Clean laps used for analysis: {clean}/{total}")
        return "  ".join(lines)


class IncidentDetector:
    """Scan every lap for contact events and track resets."""

    def analyze(self, data: TelemetryData) -> IncidentReport:
        report = IncidentReport()

        if data.num_laps < 1 or len(data.lap_boundaries) < 2:
            return report

        lat_accel  = data.get_channel("LatAccel")
        long_accel = data.get_channel("LongAccel")
        lap_dist   = data.get_channel("LapDistPct")
        session_t  = data.get_channel("SessionTime")

        tick_rate  = data.tick_rate or 60
        min_impact_ticks = max(1, int(_IMPACT_MIN_DUR_S * tick_rate))

        laps: List[LapQuality] = []

        for lap_idx in range(data.num_laps):
            if lap_idx + 1 >= len(data.lap_boundaries):
                break
            s, e = data.lap_boundaries[lap_idx], data.lap_boundaries[lap_idx + 1]
            if e - s < 60:
                continue

            lap_time = data.lap_times[lap_idx] if lap_idx < len(data.lap_times) else 0.0
            lq = LapQuality(lap_idx=lap_idx, lap_time_s=lap_time)
            incidents: List[IncidentEvent] = []

            # ── Track reset detection (LapDistPct jumps backward) ─────────
            if lap_dist is not None:
                ld_seg = lap_dist[s:e]
                for i in range(1, len(ld_seg)):
                    jump = ld_seg[i - 1] - ld_seg[i]
                    if jump > _RESET_DIST_JUMP:
                        t_val = float(session_t[s + i]) if session_t is not None else 0.0
                        incidents.append(IncidentEvent(
                            lap_idx=lap_idx,
                            lap_dist_pct=float(ld_seg[i]),
                            session_time_s=t_val,
                            type="track_reset",
                            magnitude=jump,
                        ))

            # ── Longitudinal G spike (hard braking / rear-end collision) ──
            if long_accel is not None:
                la_seg = long_accel[s:e]
                # Positive LongAccel = deceleration in iRacing convention (varies)
                # We look for magnitude > threshold
                spike_mask = np.abs(la_seg) > _IMPACT_LONG_G
                self._collect_spikes(
                    spike_mask, la_seg, lap_dist, session_t,
                    s, lap_idx, "impact_longitudinal", incidents, min_impact_ticks
                )

            # ── Lateral G spike (wall tap, spin contact) ──────────────────
            if lat_accel is not None:
                lat_seg = lat_accel[s:e]
                spike_mask = np.abs(lat_seg) > _IMPACT_LAT_G
                self._collect_spikes(
                    spike_mask, lat_seg, lap_dist, session_t,
                    s, lap_idx, "impact_lateral", incidents, min_impact_ticks
                )

            lq.incidents = incidents
            lq.is_incident = len(incidents) > 0
            if lq.is_incident:
                reasons = list({ev.type for ev in incidents})
                lq.exclude_reason = ", ".join(reasons)

            laps.append(lq)

        # ── Mark slow laps (outlier removal) ─────────────────────────────
        all_times = [lq.lap_time_s for lq in laps if lq.lap_time_s > 0]
        if all_times:
            median_time = float(np.median(all_times))
            for lq in laps:
                if not lq.is_incident and lq.lap_time_s > median_time * _SLOW_LAP_FACTOR:
                    lq.is_slow = True
                    lq.exclude_reason = (
                        f"lap time {lq.lap_time_s:.1f}s is >{_SLOW_LAP_FACTOR:.0%} "
                        f"of session median ({median_time:.1f}s)"
                    )

        report.laps = laps
        report.clean_lap_indices   = [lq.lap_idx for lq in laps if lq.is_clean]
        report.incident_lap_indices = [lq.lap_idx for lq in laps if lq.is_incident]
        report.slow_lap_indices     = [lq.lap_idx for lq in laps if lq.is_slow]
        report.total_incidents      = sum(len(lq.incidents) for lq in laps)
        return report

    # ── internal ──────────────────────────────────────────────────────────

    def _collect_spikes(
        self, spike_mask, accel_seg, lap_dist, session_t,
        lap_start, lap_idx, event_type, incidents, min_ticks
    ):
        """Find contiguous spike regions and record one event per region."""
        in_spike = False
        spike_start = 0
        for i in range(len(spike_mask)):
            if spike_mask[i] and not in_spike:
                in_spike = True
                spike_start = i
            elif not spike_mask[i] and in_spike:
                in_spike = False
                duration = i - spike_start
                if duration >= min_ticks:
                    peak_idx = spike_start + int(np.argmax(np.abs(accel_seg[spike_start:i])))
                    ld_val = (float(lap_dist[lap_start + peak_idx])
                              if lap_dist is not None else 0.0)
                    t_val  = (float(session_t[lap_start + peak_idx])
                              if session_t is not None else 0.0)
                    incidents.append(IncidentEvent(
                        lap_idx=lap_idx,
                        lap_dist_pct=ld_val,
                        session_time_s=t_val,
                        type=event_type,
                        magnitude=float(np.max(np.abs(accel_seg[spike_start:i]))),
                    ))
        # Handle spike that runs to end of lap
        if in_spike and (len(spike_mask) - spike_start) >= min_ticks:
            peak_idx = spike_start + int(np.argmax(np.abs(accel_seg[spike_start:])))
            ld_val = (float(lap_dist[lap_start + peak_idx])
                      if lap_dist is not None else 0.0)
            t_val  = (float(session_t[lap_start + peak_idx])
                      if session_t is not None else 0.0)
            incidents.append(IncidentEvent(
                lap_idx=lap_idx,
                lap_dist_pct=ld_val,
                session_time_s=t_val,
                type=event_type,
                magnitude=float(np.max(np.abs(accel_seg[spike_start:]))),
            ))


# ─────────────────────────────────────────────────────────────────────────────
# Section 2 — Track Evolution / Rubber Buildup
# ─────────────────────────────────────────────────────────────────────────────

# How many consecutive improving laps to call it "evolution" (not noise)
_MIN_IMPROVING_LAPS  = 3
# Minimum time improvement per lap (seconds) to count as meaningful
_MIN_IMPROVE_S_PER_LAP = 0.05
# Once evolution ends (improvement flattens), how flat must it be (s/lap)?
_FLAT_THRESHOLD_S    = 0.03


@dataclass
class TrackEvolutionReport:
    """Summary of track evolution / grip buildup detected in a session."""
    detected: bool = False
    evolution_rate_s_per_lap: float = 0.0   # negative = getting faster
    evolution_laps: int = 0                  # how many laps of steady improvement
    grip_gain_total_s: float = 0.0           # total time gain attributable to track
    peaked_at_lap: Optional[int] = None      # lap number where improvement plateaued
    driver_gain_s: float = 0.0               # residual gain after track evolution ends
    confidence: str = "low"                  # "low" | "medium" | "high"
    summary: str = ""

    def for_prompt(self) -> str:
        """Short text block for the AI advisor prompt."""
        if not self.detected:
            return "Track evolution: none detected (stable grip or too few laps)."
        lines = [
            f"Track evolution detected over first {self.evolution_laps} laps.",
            f"  Improvement rate: {abs(self.evolution_rate_s_per_lap):.3f} s/lap",
            f"  Total track-induced gain: {self.grip_gain_total_s:.2f}s",
        ]
        if self.peaked_at_lap is not None:
            lines.append(f"  Grip plateaued at lap {self.peaked_at_lap + 1}")
        if self.driver_gain_s > 0.05:
            lines.append(
                f"  Driver improvement after plateau: {self.driver_gain_s:.2f}s "
                f"(genuine technique gain, not track evolution)"
            )
        lines.append(f"  Confidence: {self.confidence}")
        return "\n".join(lines)


class TrackEvolutionAnalyzer:
    """
    Detect rubber buildup / grip increase from lap time trends.

    Method:
        1. Use only clean laps (no incident, no slow laps).
        2. Fit a rolling regression over the first N laps.
        3. If the slope is consistently negative (improving) with low residual,
           attribute the improvement to track evolution.
        4. Once laps flatten (slope → 0), any further improvement is genuine.
    """

    def analyze(
        self,
        data: TelemetryData,
        incident_report: Optional[IncidentReport] = None,
    ) -> TrackEvolutionReport:
        report = TrackEvolutionReport()

        # Determine which lap times to use
        if incident_report and incident_report.clean_lap_indices:
            lap_times = [
                (lq.lap_idx, lq.lap_time_s)
                for lq in incident_report.laps
                if lq.is_clean and lq.lap_time_s > 0
            ]
        else:
            lap_times = [
                (i, t) for i, t in enumerate(data.lap_times)
                if t > 0
            ]

        if len(lap_times) < _MIN_IMPROVING_LAPS + 1:
            report.summary = "Too few clean laps to detect track evolution."
            return report

        lap_nums = np.array([lt[0] for lt in lap_times], dtype=float)
        times    = np.array([lt[1] for lt in lap_times], dtype=float)

        # Find how many laps are consistently improving at the start
        improving_until = self._find_improvement_end(times)

        if improving_until < _MIN_IMPROVING_LAPS:
            report.summary = "Lap times did not show consistent early improvement — no track evolution detected."
            return report

        # Fit a line through the improving phase
        x_evo = lap_nums[:improving_until]
        y_evo = times[:improving_until]
        slope, intercept = np.polyfit(x_evo, y_evo, 1)

        # Slope must be meaningfully negative (faster laps)
        if slope > -_MIN_IMPROVE_S_PER_LAP:
            report.summary = "Improvement rate too small to distinguish from noise."
            return report

        total_gain = float(slope * (improving_until - 1))  # negative
        peaked_at  = int(lap_nums[improving_until - 1])

        # Driver improvement after the plateau
        driver_gain = 0.0
        if improving_until < len(times):
            post_times = times[improving_until:]
            if len(post_times) >= 2:
                post_best  = float(np.min(post_times))
                plateau_t  = float(times[improving_until])
                driver_gain = max(0.0, plateau_t - post_best)

        # Confidence: based on R² of the fit and number of laps
        residuals  = y_evo - (slope * x_evo + intercept)
        ss_res     = float(np.sum(residuals ** 2))
        ss_tot     = float(np.sum((y_evo - np.mean(y_evo)) ** 2))
        r_squared  = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0

        if r_squared > 0.80 and improving_until >= 6:
            confidence = "high"
        elif r_squared > 0.55 and improving_until >= 4:
            confidence = "medium"
        else:
            confidence = "low"

        report.detected = True
        report.evolution_rate_s_per_lap = float(slope)
        report.evolution_laps = improving_until
        report.grip_gain_total_s = abs(total_gain)
        report.peaked_at_lap = peaked_at
        report.driver_gain_s = driver_gain
        report.confidence = confidence
        report.summary = (
            f"Track rubbered in over {improving_until} laps "
            f"({abs(slope):.3f} s/lap improvement, total {abs(total_gain):.2f}s). "
            f"Grip plateaued around lap {peaked_at + 1}."
        )
        return report

    def _find_improvement_end(self, times: np.ndarray) -> int:
        """
        Walk forward; return the index at which consistent improvement stops.
        Uses a small smoothing window to avoid reacting to single-lap noise.
        """
        n = len(times)
        if n < 2:
            return 0

        # Smooth with a 3-lap rolling mean to reduce noise
        smoothed = np.convolve(times, np.ones(3) / 3, mode="valid")
        # Add padding so indices align with original
        padded = np.concatenate([times[:1], smoothed, times[-1:]])[:n]

        improving_run = 0
        last_improving = 0

        for i in range(1, n):
            if padded[i] < padded[i - 1] - _FLAT_THRESHOLD_S:
                improving_run += 1
                last_improving = i
            else:
                # If we had a run, check if it's already long enough to declare
                if improving_run >= _MIN_IMPROVING_LAPS - 1:
                    break
                improving_run = 0

        return last_improving + 1 if improving_run >= _MIN_IMPROVING_LAPS - 1 else 0


# ─────────────────────────────────────────────────────────────────────────────
# Convenience: run both analyzers in one call
# ─────────────────────────────────────────────────────────────────────────────

def analyze_session_quality(
    data: TelemetryData,
) -> Tuple[IncidentReport, TrackEvolutionReport]:
    """Run incident detection and track evolution analysis together."""
    inc = IncidentDetector().analyze(data)
    evo = TrackEvolutionAnalyzer().analyze(data, inc)
    return inc, evo
