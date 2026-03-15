"""
Session Highlights — Automatic detection of notable telemetry moments.

Scans lap data and analysis results to identify best performances,
key events, and interesting statistics worth surfacing to the driver.
"""

import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Highlight:
    """A notable moment or achievement within a session."""
    title: str
    description: str
    category: str        # 'best' | 'event' | 'consistency' | 'worst'
    emoji: str
    lap: int             # 1-indexed (0 = whole session)
    track_pct: float     # 0–1 track position (0 if not applicable)
    metric_value: float
    metric_label: str    # formatted value string for display


@dataclass
class SessionHighlights:
    highlights: List[Highlight] = field(default_factory=list)
    session_headline: str = ""  # one-line summary card title


def detect_highlights(
    data,
    report,
    sector_report=None,
    style_report=None,
    consistency=None,
) -> SessionHighlights:
    """
    Scan session telemetry and analysis results to find notable moments.

    Parameters
    ----------
    data          : TelemetryData
    report        : AnalysisReport
    sector_report : SectorAnalysisReport or None
    style_report  : DriverStyleReport or None
    consistency   : ConsistencyBreakdown or None
    """
    if data is None or report is None:
        return SessionHighlights()

    highlights: List[Highlight] = []

    # ── 1. Best lap ──────────────────────────────────────────────────────────
    if data.lap_times and report.best_lap > 0:
        best_idx = int(np.argmin(data.lap_times))
        highlights.append(Highlight(
            title="Best Lap",
            description=f"Fastest lap of the session set on lap {best_idx + 1}.",
            category="best", emoji="🏆",
            lap=best_idx + 1, track_pct=0.0,
            metric_value=report.best_lap,
            metric_label=_fmt(report.best_lap),
        ))

    # ── 2. Most consistent lap ───────────────────────────────────────────────
    if len(data.lap_times) >= 3:
        valid = [(i, t) for i, t in enumerate(data.lap_times) if t > 0]
        if valid:
            best_t = min(t for _, t in valid)
            best_i = int(np.argmin(data.lap_times))
            candidates = [(i, abs(t - best_t)) for i, t in valid if i != best_i]
            if candidates:
                cons_lap, cons_delta = min(candidates, key=lambda x: x[1])
                highlights.append(Highlight(
                    title="Most Consistent Lap",
                    description=f"Lap {cons_lap + 1} was the most consistent — only {cons_delta:.3f}s off the best.",
                    category="consistency", emoji="📏",
                    lap=cons_lap + 1, track_pct=0.0,
                    metric_value=cons_delta,
                    metric_label=f"+{cons_delta:.3f}s from best",
                ))

    # ── 3. Slowest lap (if significantly off) ───────────────────────────────
    if len(data.lap_times) >= 3:
        valid_pairs = [(i, t) for i, t in enumerate(data.lap_times) if t > 0]
        if valid_pairs:
            worst_idx, worst_t = max(valid_pairs, key=lambda x: x[1])
            gap = worst_t - report.best_lap
            if gap > report.best_lap * 0.02:   # > 2% slower than best
                highlights.append(Highlight(
                    title="Slowest Lap",
                    description=f"Lap {worst_idx + 1} was the slowest — {gap:.3f}s off the pace.",
                    category="worst", emoji="⚠️",
                    lap=worst_idx + 1, track_pct=0.0,
                    metric_value=worst_t,
                    metric_label=f"+{gap:.3f}s vs best",
                ))

    # ── 4. Sector highlights ─────────────────────────────────────────────────
    if sector_report and sector_report.sectors:
        times = [s.best_time for s in sector_report.sectors if s.best_time > 0]
        if times:
            best_s_idx = int(np.argmin(times))
            best_s = sector_report.sectors[best_s_idx]
            highlights.append(Highlight(
                title=f"Strongest Sector: S{best_s_idx + 1}",
                description=f"Your S{best_s_idx + 1} ({best_s.start_pct*100:.0f}–{best_s.end_pct*100:.0f}%) is the stand-out sector this session.",
                category="best", emoji="⚡",
                lap=0, track_pct=best_s.start_pct,
                metric_value=best_s.best_time,
                metric_label=_fmt(best_s.best_time),
            ))

        tbl = getattr(sector_report, 'time_left_on_table', 0.0)
        if tbl > 0.05:
            highlights.append(Highlight(
                title="Time Left on Table",
                description=(
                    f"{tbl:.3f}s of improvement available by combining your best sectors "
                    f"(theoretical best: {_fmt(sector_report.theoretical_best)})."
                ),
                category="event", emoji="🎯",
                lap=0, track_pct=0.0,
                metric_value=tbl,
                metric_label=f"{tbl:.3f}s potential",
            ))

    # ── 5. Biggest oversteer moment ──────────────────────────────────────────
    if style_report and style_report.events:
        os_evs = [e for e in style_report.events if e.event_type == 'snap_oversteer']
        if os_evs:
            biggest = max(os_evs, key=lambda e: e.severity)
            highlights.append(Highlight(
                title="Biggest Oversteer Save",
                description=(
                    f"Largest snap-oversteer at {biggest.lap_dist_pct * 100:.1f}% of the lap "
                    f"(severity {biggest.severity:.0%})."
                ),
                category="event", emoji="🔴",
                lap=0, track_pct=biggest.lap_dist_pct,
                metric_value=biggest.severity,
                metric_label=f"{biggest.severity:.0%} severity",
            ))

    # ── 6. Grip utilization ──────────────────────────────────────────────────
    if report.grip_utilization_pct > 0:
        if report.grip_utilization_pct >= 88:
            note = "Outstanding — right on the limit."
        elif report.grip_utilization_pct >= 75:
            note = "Good balance of risk and pace."
        else:
            note = "Room to push harder through the corners."
        highlights.append(Highlight(
            title="Grip Utilization",
            description=f"Using {report.grip_utilization_pct:.0f}% of available grip. {note}",
            category="best" if report.grip_utilization_pct >= 85 else "event",
            emoji="🔥",
            lap=0, track_pct=0.0,
            metric_value=report.grip_utilization_pct,
            metric_label=f"{report.grip_utilization_pct:.0f}%",
        ))

    # ── 7. Braking consistency ───────────────────────────────────────────────
    if style_report and style_report.brake_consistency > 0:
        bc = style_report.brake_consistency
        if bc >= 85:
            highlights.append(Highlight(
                title="Excellent Braking Consistency",
                description=f"Brake consistency score {bc:.0f}/100 — brake points are highly repeatable.",
                category="best", emoji="🛑",
                lap=0, track_pct=0.0,
                metric_value=bc, metric_label=f"{bc:.0f}/100",
            ))
        elif bc < 55:
            highlights.append(Highlight(
                title="Inconsistent Braking",
                description=f"Brake consistency score {bc:.0f}/100 — brake points varied significantly between laps.",
                category="worst", emoji="🛑",
                lap=0, track_pct=0.0,
                metric_value=bc, metric_label=f"{bc:.0f}/100",
            ))

    # ── 8. Lap time trend ────────────────────────────────────────────────────
    if len(data.lap_times) >= 4:
        valid_t = [t for t in data.lap_times if t > 0]
        if len(valid_t) >= 4:
            half = len(valid_t) // 2
            trend = float(np.mean(valid_t[half:]) - np.mean(valid_t[:half]))
            if abs(trend) > 0.1:
                if trend < 0:
                    highlights.append(Highlight(
                        title="Improving Pace",
                        description=f"Lap times improved by {abs(trend):.3f}s on average — good warm-up or learning curve.",
                        category="best", emoji="📈",
                        lap=0, track_pct=0.0,
                        metric_value=abs(trend),
                        metric_label=f"{abs(trend):.3f}s improvement",
                    ))
                else:
                    highlights.append(Highlight(
                        title="Pace Degradation",
                        description=f"Lap times dropped by {trend:.3f}s on average — possible tire wear or fatigue.",
                        category="worst", emoji="📉",
                        lap=0, track_pct=0.0,
                        metric_value=trend,
                        metric_label=f"+{trend:.3f}s degradation",
                    ))

    # ── 9. Consistency grade badge ───────────────────────────────────────────
    if consistency and consistency.overall >= 90:
        highlights.append(Highlight(
            title=f"Consistency Grade: {consistency.grade}",
            description=f"Outstanding score of {consistency.overall:.0f}/100 — race-ready level of consistency.",
            category="best", emoji="⭐",
            lap=0, track_pct=0.0,
            metric_value=consistency.overall,
            metric_label=f"{consistency.overall:.0f}/100",
        ))

    # Sort: best first, then events, then worst
    _ORDER = {'best': 0, 'consistency': 1, 'event': 2, 'worst': 3}
    highlights.sort(key=lambda h: _ORDER.get(h.category, 2))

    headline = _build_headline(data, report, consistency)
    return SessionHighlights(highlights=highlights[:8], session_headline=headline)


def _build_headline(data, report, consistency) -> str:
    parts = [f"{data.car_name.replace('_', ' ').title()} @ {data.track_name}"]
    if report.best_lap > 0:
        parts.append(f"Best {_fmt(report.best_lap)}")
    if consistency and consistency.overall > 0:
        parts.append(f"Consistency {consistency.overall:.0f}/100 {consistency.grade}")
    return "  •  ".join(parts)


def _fmt(s: float) -> str:
    if s <= 0:
        return "—"
    m = int(s // 60)
    sec = s - m * 60
    return f"{m}:{sec:06.3f}" if m > 0 else f"{sec:.3f}s"
