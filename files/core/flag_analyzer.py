"""
Flag Analyzer
=============
Parses iRacing's SessionFlags bitfield to detect yellow flag / safety car periods
and produces a per-lap valid mask — laps with significant yellow flag exposure are
excluded from performance analysis.
"""

from __future__ import annotations
import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional
from core.ibt_parser import TelemetryData

# SessionFlags bit masks (iRacing SDK irsdk_Flags enum)
FLAG_CHECKERED       = 0x00000001
FLAG_WHITE           = 0x00000002
FLAG_GREEN           = 0x00000004
FLAG_YELLOW          = 0x00000008
FLAG_RED             = 0x00000010
FLAG_YELLOW_WAVING   = 0x00000100
FLAG_CAUTION         = 0x00004000
FLAG_CAUTION_WAVING  = 0x00008000

# Any of these → caution / neutralised lap
YELLOW_MASK = FLAG_YELLOW | FLAG_YELLOW_WAVING | FLAG_CAUTION | FLAG_CAUTION_WAVING

# Fraction of a lap that must be under yellow to discard it (0.15 = 15%)
YELLOW_LAP_THRESHOLD = 0.15


@dataclass
class FlagEvent:
    lap: int
    start_pct: float   # LapDistPct at onset
    end_pct: float     # LapDistPct at clear (or 1.0 if spans lap boundary)
    flag_type: str     # 'yellow', 'red', 'checkered'
    duration_s: float  # seconds this flag was active


@dataclass
class FlagReport:
    """Results of flag analysis for a session."""
    # Per-lap True/False — True means lap is clean (no significant caution exposure)
    clean_lap_mask: List[bool] = field(default_factory=list)
    yellow_lap_indices: List[int] = field(default_factory=list)  # 0-based
    flag_events: List[FlagEvent] = field(default_factory=list)
    total_yellow_laps: int = 0
    total_laps: int = 0
    has_flag_data: bool = False

    @property
    def clean_lap_count(self) -> int:
        return sum(self.clean_lap_mask)

    def summary(self) -> str:
        if not self.has_flag_data:
            return "No flag data"
        if self.total_yellow_laps == 0:
            return f"All {self.total_laps} laps clean (no cautions)"
        return (f"{self.clean_lap_count}/{self.total_laps} clean laps  "
                f"({self.total_yellow_laps} yellow-flag lap{'s' if self.total_yellow_laps != 1 else ''} excluded)")


class FlagAnalyzer:

    def analyze(self, data: TelemetryData) -> FlagReport:
        report = FlagReport(total_laps=data.num_laps)

        flags_ch = data.get_channel('SessionFlags')
        if flags_ch is None or len(flags_ch) == 0 or data.num_laps < 1:
            # No flag data — mark all laps clean
            report.clean_lap_mask = [True] * data.num_laps
            return report

        report.has_flag_data = True
        flags = flags_ch.astype(np.uint32)
        yellow_active = (flags & YELLOW_MASK) != 0

        session_time = data.get_channel('SessionTime')
        lap_dist    = data.get_channel('LapDistPct')

        boundaries = data.lap_boundaries
        if not boundaries or len(boundaries) < 2:
            report.clean_lap_mask = [True] * data.num_laps
            return report

        # Per-lap analysis
        for lap_idx in range(data.num_laps):
            b_start = boundaries[lap_idx]
            b_end   = boundaries[lap_idx + 1] if lap_idx + 1 < len(boundaries) else len(flags)
            lap_slice = yellow_active[b_start:b_end]
            if len(lap_slice) == 0:
                report.clean_lap_mask.append(True)
                continue
            yellow_fraction = float(np.sum(lap_slice)) / len(lap_slice)
            is_clean = yellow_fraction < YELLOW_LAP_THRESHOLD
            report.clean_lap_mask.append(is_clean)
            if not is_clean:
                report.yellow_lap_indices.append(lap_idx)

            # Build flag events for this lap
            if session_time is not None and lap_dist is not None:
                _extract_flag_events(
                    report, lap_idx, b_start, b_end,
                    yellow_active, flags, session_time, lap_dist
                )

        report.total_yellow_laps = len(report.yellow_lap_indices)
        return report


def _extract_flag_events(
    report: FlagReport,
    lap_idx: int,
    b_start: int,
    b_end: int,
    yellow_active: np.ndarray,
    flags: np.ndarray,
    session_time: np.ndarray,
    lap_dist: np.ndarray,
) -> None:
    """Find contiguous yellow-flag stretches within this lap and record them."""
    in_event = False
    ev_start_idx = 0
    for i in range(b_start, min(b_end, len(yellow_active))):
        if yellow_active[i] and not in_event:
            in_event = True
            ev_start_idx = i
        elif not yellow_active[i] and in_event:
            in_event = False
            dur = float(session_time[i] - session_time[ev_start_idx]) if i < len(session_time) else 0.0
            if dur >= 1.0:  # ignore sub-1s noise
                report.flag_events.append(FlagEvent(
                    lap=lap_idx + 1,
                    start_pct=float(lap_dist[ev_start_idx]) if ev_start_idx < len(lap_dist) else 0.0,
                    end_pct=float(lap_dist[i - 1]) if i - 1 < len(lap_dist) else 1.0,
                    flag_type='yellow',
                    duration_s=round(dur, 2),
                ))
    if in_event:
        i = min(b_end, len(yellow_active)) - 1
        dur = float(session_time[i] - session_time[ev_start_idx]) if i < len(session_time) else 0.0
        if dur >= 1.0:
            report.flag_events.append(FlagEvent(
                lap=lap_idx + 1,
                start_pct=float(lap_dist[ev_start_idx]) if ev_start_idx < len(lap_dist) else 0.0,
                end_pct=1.0,
                flag_type='yellow',
                duration_s=round(dur, 2),
            ))
