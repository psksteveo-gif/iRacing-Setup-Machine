"""
Corner-by-Corner Analysis & Reference Lap Delta
Detects braking zones to identify corners, computes per-corner metrics,
generates coaching notes, and builds cumulative time-delta traces.
"""

import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from core.ibt_parser import TelemetryData  # type: ignore[import-unresolved]

# ── Detection thresholds ──────────────────────────────────────────────────
BRAKE_ON_THRESHOLD = 0.15       # brake > this marks start of braking zone
BRAKE_OFF_GAP = 0.02            # min LapDistPct gap between corners
MIN_CORNER_DURATION = 0.005     # min segment length in LapDistPct
SPEED_DIP_FACTOR = 0.85         # speed must drop below entry_speed * this


@dataclass
class CornerData:
    """Analysis results for a single detected corner."""
    corner_num: int
    brake_pct: float            # LapDistPct where braking begins
    apex_pct: float             # LapDistPct of minimum speed
    exit_pct: float             # LapDistPct where throttle resumes
    entry_speed_ms: float = 0.0
    min_speed_ms: float = 0.0
    exit_speed_ms: float = 0.0
    brake_pressure_avg: float = 0.0  # average brake input 0-1
    throttle_exit_avg: float = 0.0   # average throttle on exit
    lat_g_peak: float = 0.0
    time_in_corner_s: float = 0.0
    # Per-lap data (for consistency)
    lap_times_s: List[float] = field(default_factory=list)
    lap_entry_speeds: List[float] = field(default_factory=list)
    lap_min_speeds: List[float] = field(default_factory=list)
    lap_exit_speeds: List[float] = field(default_factory=list)
    lap_brake_points: List[float] = field(default_factory=list)
    coaching_note: str = ""

    @property
    def best_time(self) -> float:
        return min(self.lap_times_s) if self.lap_times_s else 0.0

    @property
    def avg_time(self) -> float:
        return float(np.mean(self.lap_times_s)) if self.lap_times_s else 0.0

    @property
    def time_delta(self) -> float:
        return self.avg_time - self.best_time if self.lap_times_s else 0.0

    @property
    def consistency_pct(self) -> float:
        if len(self.lap_times_s) < 2:
            return 100.0
        return float(100 - np.std(self.lap_times_s) / max(np.mean(self.lap_times_s), 0.001) * 100)

    @property
    def brake_point_consistency(self) -> float:
        if len(self.lap_brake_points) < 2:
            return 100.0
        return float(100 - np.std(self.lap_brake_points) * 1000)  # scaled


@dataclass
class CornerAnalysisReport:
    corners: List[CornerData] = field(default_factory=list)
    worst_corner: int = 0       # index of corner losing most time
    total_time_lost: float = 0.0


@dataclass
class LapDelta:
    """Cumulative time delta between two laps."""
    dist_pct: np.ndarray = field(default_factory=lambda: np.array([]))
    delta_s: np.ndarray = field(default_factory=lambda: np.array([]))
    ref_lap: int = 0
    cmp_lap: int = 0
    segments: List[dict] = field(default_factory=list)  # {start_pct, end_pct, delta, note}


class CornerDetector:
    """Detect corners from telemetry using braking zones and speed dips."""

    def detect(self, data: TelemetryData, lap_idx: int = 0) -> List[Tuple[float, float, float]]:
        """Return list of (brake_pct, apex_pct, exit_pct) for detected corners."""
        if lap_idx >= data.num_laps or len(data.lap_boundaries) < lap_idx + 2:
            return []

        s, e = data.lap_boundaries[lap_idx], data.lap_boundaries[lap_idx + 1]
        if e - s < 120:
            return []

        lap_dist = data.get_channel('LapDistPct')
        speed = data.get_channel('Speed')
        brake = data.get_channel('Brake')
        throttle = data.get_channel('Throttle')
        if lap_dist is None or speed is None or brake is None:
            return []

        ld = lap_dist[s:e]
        spd = speed[s:e]
        brk = brake[s:e]

        # Find braking zone starts: brake crosses threshold upward
        braking = brk > BRAKE_ON_THRESHOLD
        corners = []
        in_zone = False
        zone_start = 0

        for i in range(1, len(braking)):
            if braking[i] and not in_zone:
                in_zone = True
                zone_start = i
            elif not braking[i] and in_zone:
                in_zone = False
                zone_end = i

                # Find apex (min speed) within and just after braking zone
                search_end = min(zone_end + int(0.03 * len(ld)), len(spd))
                if search_end <= zone_start:
                    continue  # empty slice — skip degenerate brake zone
                apex_i = zone_start + int(np.argmin(spd[zone_start:search_end]))

                # Find exit: where throttle goes above 0.5 after apex
                exit_i = apex_i
                if throttle is not None:
                    thr = throttle[s:e]
                    for j in range(apex_i, min(apex_i + int(0.05 * len(ld)), len(thr))):
                        if thr[j] > 0.5:
                            exit_i = j
                            break
                    else:
                        exit_i = min(apex_i + int(0.02 * len(ld)), len(ld) - 1)
                else:
                    exit_i = min(apex_i + int(0.02 * len(ld)), len(ld) - 1)

                brake_pct = float(ld[zone_start])
                apex_pct = float(ld[apex_i])
                exit_pct = float(ld[exit_i])

                # Filter: must be a real corner (speed actually dips)
                entry_speed = float(spd[zone_start])
                apex_speed = float(spd[apex_i])

                if apex_speed < entry_speed * SPEED_DIP_FACTOR and (exit_pct - brake_pct) > MIN_CORNER_DURATION:
                    # Merge with previous if too close
                    if corners and brake_pct - corners[-1][2] < BRAKE_OFF_GAP:
                        prev = corners[-1]
                        corners[-1] = (prev[0], apex_pct if apex_speed < spd[int((prev[1] - ld[0]) / (ld[-1] - ld[0]) * len(ld))] else prev[1], exit_pct)
                    else:
                        corners.append((brake_pct, apex_pct, exit_pct))

        return corners


class CornerAnalyzer:
    """Full corner-by-corner analysis with coaching notes."""

    def __init__(self):
        self._detector = CornerDetector()

    def analyze(self, data: TelemetryData) -> CornerAnalysisReport:
        report = CornerAnalysisReport()

        if data.num_laps < 1:
            return report

        # Detect corners using the best lap
        best_lap = int(np.argmin(data.lap_times)) if data.lap_times else 0
        corner_zones = self._detector.detect(data, best_lap)

        if not corner_zones:
            return report

        # Build CornerData for each detected corner
        corners = []
        for i, (brake_pct, apex_pct, exit_pct) in enumerate(corner_zones):
            cd = CornerData(
                corner_num=i + 1,
                brake_pct=brake_pct,
                apex_pct=apex_pct,
                exit_pct=exit_pct,
            )
            corners.append(cd)

        # Analyze each corner across all laps
        lap_dist = data.get_channel('LapDistPct')
        speed = data.get_channel('Speed')
        brake = data.get_channel('Brake')
        throttle = data.get_channel('Throttle')
        lat_accel = data.get_channel('LatAccel')
        session_time = data.get_channel('SessionTime')

        for lap_idx in range(data.num_laps):
            if lap_idx + 1 >= len(data.lap_boundaries):
                break
            s, e = data.lap_boundaries[lap_idx], data.lap_boundaries[lap_idx + 1]
            if e - s < 120:
                continue

            ld = lap_dist[s:e]
            spd = speed[s:e] if speed is not None else None
            brk = brake[s:e] if brake is not None else None
            thr = throttle[s:e] if throttle is not None else None
            lat = lat_accel[s:e] if lat_accel is not None else None
            st = session_time[s:e] if session_time is not None else None

            for cd in corners:
                mask = (ld >= cd.brake_pct) & (ld <= cd.exit_pct)
                if not np.any(mask):
                    continue
                indices = np.where(mask)[0]

                # Timing
                if st is not None and len(indices) >= 2:
                    t = float(st[indices[-1]] - st[indices[0]])
                    if t > 0:
                        cd.lap_times_s.append(t)

                if spd is not None and len(indices) >= 2:
                    seg_spd = spd[indices]
                    cd.lap_entry_speeds.append(float(seg_spd[0]) * 3.6)
                    cd.lap_min_speeds.append(float(np.min(seg_spd)) * 3.6)
                    cd.lap_exit_speeds.append(float(seg_spd[-1]) * 3.6)

                # Brake point: where brake first exceeds threshold
                if brk is not None:
                    brake_seg = brk[indices]
                    bp_candidates = np.where(brake_seg > BRAKE_ON_THRESHOLD)[0]
                    if len(bp_candidates) > 0:
                        cd.lap_brake_points.append(float(ld[indices[bp_candidates[0]]]))

        # Compute averages for display from best lap
        for cd in corners:
            if cd.lap_entry_speeds:
                cd.entry_speed_ms = float(np.mean(cd.lap_entry_speeds)) / 3.6
            if cd.lap_min_speeds:
                cd.min_speed_ms = float(np.mean(cd.lap_min_speeds)) / 3.6
            if cd.lap_exit_speeds:
                cd.exit_speed_ms = float(np.mean(cd.lap_exit_speeds)) / 3.6

            # Avg brake pressure & throttle exit from best lap data
            if best_lap < data.num_laps:
                bs, be = data.lap_boundaries[best_lap], data.lap_boundaries[best_lap + 1]
                bld = lap_dist[bs:be]
                bmask = (bld >= cd.brake_pct) & (bld <= cd.apex_pct)
                emask = (bld >= cd.apex_pct) & (bld <= cd.exit_pct)
                if brake is not None and np.any(bmask):
                    cd.brake_pressure_avg = float(np.mean(brake[bs:be][bmask]))
                if throttle is not None and np.any(emask):
                    cd.throttle_exit_avg = float(np.mean(throttle[bs:be][emask]))
                if lat_accel is not None:
                    full_mask = (bld >= cd.brake_pct) & (bld <= cd.exit_pct)
                    if np.any(full_mask):
                        cd.lat_g_peak = float(np.max(np.abs(lat_accel[bs:be][full_mask])))
                if session_time is not None:
                    full_mask = (bld >= cd.brake_pct) & (bld <= cd.exit_pct)
                    idxs = np.where(full_mask)[0]
                    if len(idxs) >= 2:
                        cd.time_in_corner_s = float(session_time[bs:be][idxs[-1]] - session_time[bs:be][idxs[0]])

        # Generate coaching notes
        for cd in corners:
            cd.coaching_note = self._generate_coaching_note(cd)

        report.corners = corners

        # Find worst corner (most time lost)
        if corners:
            deltas = [cd.time_delta for cd in corners]
            if any(d > 0 for d in deltas):
                report.worst_corner = int(np.argmax(deltas))
            report.total_time_lost = sum(deltas)

        return report

    def _generate_coaching_note(self, cd: CornerData) -> str:
        """Generate a human-readable coaching note for a corner."""
        notes = []

        # Brake point consistency
        if cd.brake_point_consistency < 70:
            notes.append("Inconsistent braking point — pick a fixed reference marker and brake at the same spot every lap.")
        elif cd.brake_point_consistency > 95:
            notes.append("Excellent brake marker consistency.")

        # Entry speed analysis
        if cd.lap_entry_speeds and len(cd.lap_entry_speeds) >= 2:
            entry_std = float(np.std(cd.lap_entry_speeds))
            if entry_std > 5:
                notes.append(f"Entry speed varies by ±{entry_std:.0f} km/h — work on carrying consistent speed into the braking zone.")

        # Braking pressure
        if cd.brake_pressure_avg > 0.85:
            notes.append("Very heavy initial braking. Try slightly less peak brake to avoid locking and carry more entry speed.")
        elif cd.brake_pressure_avg < 0.4 and cd.brake_pressure_avg > 0:
            notes.append("Light braking — you may be able to brake later and carry more speed.")

        # Apex/min speed analysis
        if cd.lap_min_speeds and cd.lap_entry_speeds:
            avg_entry = float(np.mean(cd.lap_entry_speeds))
            avg_min = float(np.mean(cd.lap_min_speeds))
            speed_loss = avg_entry - avg_min
            if speed_loss > 80:
                notes.append(f"Losing {speed_loss:.0f} km/h through this corner — check if you're over-slowing. Trail-brake deeper to maintain speed.")
            elif speed_loss < 20 and cd.brake_pressure_avg > 0.3:
                notes.append("Minimal speed loss — good corner. Focus on exit speed for time on the straight.")

        # Exit speed analysis
        if cd.lap_exit_speeds and cd.lap_min_speeds:
            avg_exit = float(np.mean(cd.lap_exit_speeds))
            avg_min = float(np.mean(cd.lap_min_speeds))
            recovery = avg_exit - avg_min
            if recovery < 15 and cd.throttle_exit_avg < 0.6:
                notes.append("Slow exit — apply throttle earlier and more progressively. Poor exit costs time down the entire following straight.")
            elif cd.throttle_exit_avg > 0.85:
                notes.append("Strong throttle application on exit — good acceleration out of the corner.")

        # Lateral G
        if cd.lat_g_peak > 2.5:
            notes.append(f"High peak lateral G ({cd.lat_g_peak:.1f}G) — you're pushing the grip limit here.")
        elif cd.lat_g_peak < 1.0 and cd.lat_g_peak > 0:
            notes.append("Low lateral G — this may be a slow-speed corner, or you have room to carry more speed.")

        # Time consistency
        if cd.time_delta > 0.3:
            notes.append(f"Losing +{cd.time_delta:.3f}s vs your best here. This is your biggest opportunity.")
        elif cd.time_delta > 0.1:
            notes.append(f"Losing +{cd.time_delta:.3f}s vs your best — room to improve with cleaner execution.")
        elif cd.time_delta < 0.05 and cd.lap_times_s:
            notes.append("Very consistent through here — well driven.")

        if not notes:
            notes.append("No specific issues detected.")

        return " ".join(notes)


class LapDeltaAnalyzer:
    """Compute cumulative time delta between a reference lap and comparison lap."""

    def analyze(self, data: TelemetryData, ref_lap: int, cmp_lap: int,
                num_points: int = 500) -> Optional[LapDelta]:
        """Build a delta trace: positive = cmp is slower, negative = cmp is faster."""
        if (ref_lap >= data.num_laps or cmp_lap >= data.num_laps
                or ref_lap + 1 >= len(data.lap_boundaries)
                or cmp_lap + 1 >= len(data.lap_boundaries)):
            return None

        lap_dist = data.get_channel('LapDistPct')
        session_time = data.get_channel('SessionTime')
        speed = data.get_channel('Speed')
        if lap_dist is None or session_time is None or speed is None:
            return None

        # Extract each lap
        rs, re = data.lap_boundaries[ref_lap], data.lap_boundaries[ref_lap + 1]
        cs, ce = data.lap_boundaries[cmp_lap], data.lap_boundaries[cmp_lap + 1]
        if re - rs < 60 or ce - cs < 60:
            return None

        ref_dist = lap_dist[rs:re]
        ref_time = session_time[rs:re] - session_time[rs]
        cmp_dist = lap_dist[cs:ce]
        cmp_time = session_time[cs:ce] - session_time[cs]

        # Interpolate both to a common distance axis
        common_dist = np.linspace(0.001, 0.999, num_points)
        ref_time_interp = np.interp(common_dist, ref_dist, ref_time)
        cmp_time_interp = np.interp(common_dist, cmp_dist, cmp_time)

        # Delta: positive = cmp is slower than ref
        delta = cmp_time_interp - ref_time_interp

        # Generate coaching segments
        segments = self._generate_delta_segments(
            data, ref_lap, cmp_lap, common_dist, delta)

        return LapDelta(
            dist_pct=common_dist,
            delta_s=delta,
            ref_lap=ref_lap,
            cmp_lap=cmp_lap,
            segments=segments,
        )

    def _generate_delta_segments(self, data: TelemetryData,
                                  ref_lap: int, cmp_lap: int,
                                  dist: np.ndarray, delta: np.ndarray) -> List[dict]:
        """Identify where time is gained/lost and explain why."""
        segments = []
        speed = data.get_channel('Speed')
        brake = data.get_channel('Brake')
        throttle = data.get_channel('Throttle')
        lap_dist = data.get_channel('LapDistPct')

        # Split into 10 segments for analysis
        num_segs = 10
        seg_size = len(dist) // num_segs

        for i in range(num_segs):
            si = i * seg_size
            ei = (i + 1) * seg_size if i < num_segs - 1 else len(dist)
            seg_start = float(dist[si])
            seg_end = float(dist[ei - 1])
            seg_delta = float(delta[ei - 1] - delta[si])

            if abs(seg_delta) < 0.010:
                continue

            note = self._explain_delta_segment(
                data, ref_lap, cmp_lap, seg_start, seg_end, seg_delta,
                speed, brake, throttle, lap_dist)

            segments.append({
                'start_pct': seg_start,
                'end_pct': seg_end,
                'delta': seg_delta,
                'note': note,
            })

        return segments

    def _explain_delta_segment(self, data, ref_lap, cmp_lap,
                                start_pct, end_pct, seg_delta,
                                speed, brake, throttle, lap_dist) -> str:
        """Explain why time was gained or lost in a segment."""
        gaining = seg_delta < 0  # cmp is faster in this segment
        verb = "gaining" if gaining else "losing"
        amount = abs(seg_delta)

        parts = [f"{'✅' if gaining else '⚠️'} {verb.title()} {amount:.3f}s ({start_pct*100:.0f}–{end_pct*100:.0f}% track)."]

        # Compare speeds in this segment
        if speed is not None and lap_dist is not None:
            ref_avg_spd = self._segment_avg(speed, lap_dist, data, ref_lap, start_pct, end_pct)
            cmp_avg_spd = self._segment_avg(speed, lap_dist, data, cmp_lap, start_pct, end_pct)
            if ref_avg_spd > 0 and cmp_avg_spd > 0:
                spd_diff = (cmp_avg_spd - ref_avg_spd) * 3.6
                if abs(spd_diff) > 2:
                    faster_label = "faster" if spd_diff > 0 else "slower"
                    parts.append(f"Comparison lap is {abs(spd_diff):.0f} km/h {faster_label} here.")

        # Check braking
        if brake is not None and lap_dist is not None:
            ref_brk = self._segment_avg(brake, lap_dist, data, ref_lap, start_pct, end_pct)
            cmp_brk = self._segment_avg(brake, lap_dist, data, cmp_lap, start_pct, end_pct)
            if ref_brk > 0.1 or cmp_brk > 0.1:
                if cmp_brk > ref_brk + 0.1:
                    parts.append("More braking in comparison lap — possibly braking too hard or too early.")
                elif ref_brk > cmp_brk + 0.1:
                    parts.append("Less braking in comparison lap — carrying more speed or braking later.")

        # Check throttle
        if throttle is not None and lap_dist is not None:
            ref_thr = self._segment_avg(throttle, lap_dist, data, ref_lap, start_pct, end_pct)
            cmp_thr = self._segment_avg(throttle, lap_dist, data, cmp_lap, start_pct, end_pct)
            if abs(cmp_thr - ref_thr) > 0.1:
                if cmp_thr > ref_thr:
                    parts.append("More throttle application — better acceleration or earlier power-on.")
                else:
                    parts.append("Less throttle — possible hesitation or later power application.")

        return " ".join(parts)

    def _segment_avg(self, channel, lap_dist, data, lap_idx, start_pct, end_pct) -> float:
        """Get average of a channel within a track segment for a specific lap."""
        if lap_idx + 1 >= len(data.lap_boundaries):
            return 0.0
        s, e = data.lap_boundaries[lap_idx], data.lap_boundaries[lap_idx + 1]
        ld = lap_dist[s:e]
        mask = (ld >= start_pct) & (ld <= end_pct)
        if not np.any(mask):
            return 0.0
        return float(np.mean(channel[s:e][mask]))


def format_corner_summary(report: CornerAnalysisReport) -> str:
    """Build a text summary of corner analysis for AI prompt inclusion."""
    if not report or not report.corners:
        return ""
    lines = ["\nCorner-by-Corner Analysis:"]
    for cd in report.corners:
        entry = f"{np.mean(cd.lap_entry_speeds):.0f}" if cd.lap_entry_speeds else "??"
        apex = f"{np.mean(cd.lap_min_speeds):.0f}" if cd.lap_min_speeds else "??"
        exit_s = f"{np.mean(cd.lap_exit_speeds):.0f}" if cd.lap_exit_speeds else "??"
        lines.append(
            f"  T{cd.corner_num} ({cd.brake_pct*100:.0f}-{cd.exit_pct*100:.0f}%): "
            f"entry={entry}km/h, apex={apex}km/h, exit={exit_s}km/h, "
            f"time={cd.time_in_corner_s:.3f}s, delta=+{cd.time_delta:.3f}s, "
            f"peak_lat_G={cd.lat_g_peak:.1f}, consistency={cd.consistency_pct:.0f}%"
        )
        # Include detected issues for AI context
        issues = []
        if cd.brake_pressure_avg > 0.85:
            issues.append("heavy braking")
        elif cd.brake_pressure_avg < 0.4 and cd.brake_pressure_avg > 0:
            issues.append("light braking")
        if cd.lap_min_speeds and cd.lap_entry_speeds:
            speed_loss = float(np.mean(cd.lap_entry_speeds) - np.mean(cd.lap_min_speeds))
            if speed_loss > 80:
                issues.append(f"over-slowing ({speed_loss:.0f}km/h loss)")
        if cd.lap_exit_speeds and cd.lap_min_speeds:
            recovery = float(np.mean(cd.lap_exit_speeds) - np.mean(cd.lap_min_speeds))
            if recovery < 15 and cd.throttle_exit_avg < 0.6:
                issues.append("slow exit/late throttle")
        if cd.time_delta > 0.3:
            issues.append(f"major time loss (+{cd.time_delta:.3f}s)")
        if cd.brake_point_consistency < 70:
            issues.append("inconsistent brake point")
        if issues:
            lines.append(f"    Issues: {', '.join(issues)}")
    worst = report.corners[report.worst_corner]
    lines.append(f"  Worst corner: T{worst.corner_num} (+{worst.time_delta:.3f}s)")
    lines.append(f"  Total time lost in corners: +{report.total_time_lost:.3f}s")
    return "\n".join(lines) + "\n"
