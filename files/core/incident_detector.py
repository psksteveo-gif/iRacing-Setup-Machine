"""
Incident Detector
=================
Scans IBT telemetry for driving incidents:
  • Lock-ups  : high brake pressure + sudden speed drop
  • Spins     : sharp yaw-rate spike while moving
  • Big slides : sustained high yaw-rate

All detection uses simple signal-processing on existing IBT channels so no
additional hardware or data is needed.
"""
from __future__ import annotations

import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Incident:
    lap: int
    lap_dist_pct: float      # 0.0–1.0 position on track
    incident_type: str       # 'lockup', 'spin', 'slide'
    severity: float          # 0.0–1.0 (1.0 = most severe)
    duration_frames: int
    timestamp_s: float       # approx session time in seconds
    description: str


@dataclass
class IncidentReport:
    incidents: List[Incident] = field(default_factory=list)
    lockup_count: int = 0
    spin_count: int = 0
    slide_count: int = 0

    # Estimated total time lost (seconds) from all incidents combined
    time_lost_s: float = 0.0


class IncidentDetector:
    """
    Detect lock-ups, spins, and big slides from IBT telemetry.

    Thresholds are intentionally conservative so false positives are rare
    even on noisy data.
    """

    LOCKUP_BRAKE = 0.72        # brake fraction (0–1) above which to look for locks
    LOCKUP_SPEED_DROP = 1.8    # kph/frame drop that signals a locked wheel
    LOCKUP_MIN_SPEED = 30.0    # kph — ignore very slow events

    SPIN_YAW_DEG = 28.0        # deg/s yaw-rate threshold
    SPIN_MIN_SPEED = 25.0      # kph

    SLIDE_YAW_DEG = 18.0       # deg/s sustained threshold
    SLIDE_MIN_FRAMES = 25      # must persist at least this many frames

    MIN_GAP_FRAMES = 45        # minimum separation between same-type events

    # Approx time lost per event type (seconds) — used for summary estimate
    TIME_LOST = {'lockup': 0.08, 'spin': 0.4, 'slide': 0.15}

    # ── Public API ─────────────────────────────────────────────────────────────

    def analyze(self, data) -> IncidentReport:
        """Return an IncidentReport for the given TelemetryData object."""
        report = IncidentReport()
        if not data or not data.lap_boundaries or len(data.lap_boundaries) < 2:
            return report

        brake = _ch(data, 'Brake')
        speed = _ch(data, 'Speed')   # kph
        yaw   = _ch(data, 'YawRate') # rad/s
        dist  = _ch(data, 'LapDistPct')
        tick  = float(getattr(data, 'tick_rate', None) or 60)
        bounds = list(data.lap_boundaries)

        if brake is not None and speed is not None:
            self._detect_lockups(report, brake, speed, dist, bounds, tick)

        if yaw is not None and speed is not None:
            self._detect_yaw(report, yaw, speed, dist, bounds, tick)

        # Sort by (lap, position) and count
        report.incidents.sort(key=lambda i: (i.lap, i.lap_dist_pct))
        report.lockup_count = sum(1 for i in report.incidents if i.incident_type == 'lockup')
        report.spin_count   = sum(1 for i in report.incidents if i.incident_type == 'spin')
        report.slide_count  = sum(1 for i in report.incidents if i.incident_type == 'slide')
        report.time_lost_s  = round(
            report.lockup_count * self.TIME_LOST['lockup'] +
            report.spin_count   * self.TIME_LOST['spin'] +
            report.slide_count  * self.TIME_LOST['slide'],
            2)
        return report

    # ── Detection helpers ──────────────────────────────────────────────────────

    def _detect_lockups(self, report, brake, speed, dist, bounds, tick):
        brake = np.asarray(brake, float)
        speed = np.asarray(speed, float)
        speed_drop = np.diff(speed, prepend=speed[0])
        mask = (
            (brake > self.LOCKUP_BRAKE) &
            (speed_drop < -self.LOCKUP_SPEED_DROP) &
            (speed > self.LOCKUP_MIN_SPEED)
        )
        self._extract(report, mask, 'lockup', brake, dist, bounds, tick,
                      severity_arr=brake, severity_max=1.0)

    def _detect_yaw(self, report, yaw, speed, dist, bounds, tick):
        yaw   = np.asarray(yaw,   float)
        speed = np.asarray(speed, float)
        yaw_deg = np.abs(yaw) * (180.0 / np.pi)

        # Spins: sharp spike above SPIN threshold
        spin_mask = (yaw_deg > self.SPIN_YAW_DEG) & (speed > self.SPIN_MIN_SPEED)
        self._extract(report, spin_mask, 'spin', yaw_deg, dist, bounds, tick,
                      severity_arr=yaw_deg, severity_max=90.0)

        # Slides: sustained yaw above lower threshold
        slide_mask = (yaw_deg > self.SLIDE_YAW_DEG) & (speed > self.SPIN_MIN_SPEED)
        self._extract(report, slide_mask, 'slide', yaw_deg, dist, bounds, tick,
                      severity_arr=yaw_deg, severity_max=45.0,
                      min_duration=self.SLIDE_MIN_FRAMES)

    def _extract(self, report, mask, incident_type, magnitude,
                 dist, bounds, tick, severity_arr, severity_max=1.0,
                 min_duration=1):
        if dist is None:
            dist_arr = None
        else:
            dist_arr = np.asarray(dist, float)

        n = len(mask)
        last_end = -self.MIN_GAP_FRAMES
        i = 0
        while i < n:
            if not mask[i]:
                i += 1
                continue
            j = i
            while j < n and mask[j]:
                j += 1
            duration = j - i
            if duration >= min_duration and i - last_end >= self.MIN_GAP_FRAMES:
                lap_idx = _lap_of(i, bounds)
                d_pct   = float(dist_arr[i]) if dist_arr is not None and i < len(dist_arr) else 0.0
                sev     = float(np.clip(
                    severity_arr[i:j].max() / max(severity_max, 1e-6), 0.0, 1.0))
                ts      = float(i) / tick
                report.incidents.append(Incident(
                    lap=lap_idx,
                    lap_dist_pct=d_pct,
                    incident_type=incident_type,
                    severity=sev,
                    duration_frames=duration,
                    timestamp_s=ts,
                    description=_describe(incident_type, sev, lap_idx, d_pct),
                ))
                last_end = j
            i = max(j, i + 1)


# ── Module-level helpers ───────────────────────────────────────────────────────

def _ch(data, name: str) -> Optional[np.ndarray]:
    """Safely fetch a channel array."""
    try:
        ch = data.get_channel(name)
        if ch is not None and len(ch) > 0:
            return np.asarray(ch, float)
    except Exception:
        pass
    return None


def _lap_of(frame_idx: int, boundaries: list) -> int:
    """Return the 1-based lap number for a given frame index."""
    for li in range(len(boundaries) - 1):
        if boundaries[li] <= frame_idx < boundaries[li + 1]:
            return li + 1
    return len(boundaries) - 1


def _describe(incident_type: str, severity: float, lap: int, dist_pct: float) -> str:
    sev_str = "heavy" if severity > 0.7 else "medium" if severity > 0.4 else "light"
    pos_str = f"{dist_pct * 100:.0f}% track"
    labels  = {'lockup': 'Lock-up', 'spin': 'Spin / snap', 'slide': 'Big slide'}
    return f"Lap {lap}  •  {labels.get(incident_type, incident_type)} ({sev_str}) at {pos_str}"
