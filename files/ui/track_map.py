"""
TrackMapWidget — Reconstructed track outline with zone highlighting.

Uses reconstruct_racing_line() to build an approximate track shape from
LatAccel + Speed telemetry, then colours segments by lap-distance-percentage
so any analysis result (corners, sectors, brake zones, issues) can be
overlaid visually.
"""

from __future__ import annotations
import numpy as np
import customtkinter as ctk
from typing import Optional

from ui.theme import PANEL, TEXT, DIM, GREEN, YELLOW, RED, BLUE, ACCENT, PURPLE, EmbedChart
from core.racing_line import reconstruct_racing_line, RacingLine


# ── Category → colour mapping for issue overlays ─────────────────────────────
CATEGORY_COLOR = {
    "Tires":      YELLOW,
    "Brakes":     RED,
    "Suspension": PURPLE,
    "Aero":       BLUE,
    "Driving":    ACCENT,
    "Fuel":       GREEN,
    "General":    DIM,
}


def _normalize(x: np.ndarray, y: np.ndarray):
    """Centre and scale X/Y so the track fits in a unit square."""
    cx, cy = x.mean(), y.mean()
    x, y = x - cx, y - cy
    scale = max(np.ptp(x), np.ptp(y))
    if scale < 1e-6:
        scale = 1.0
    return x / scale, y / scale


def _segment_by_pct(rl: RacingLine, start: float, end: float):
    """Return the X/Y slice of a RacingLine that falls in [start, end] dist_pct."""
    d = rl.dist_pct
    # Handle wrap-around (e.g. start=0.95, end=0.05)
    if start <= end:
        mask = (d >= start) & (d <= end)
    else:
        mask = (d >= start) | (d <= end)
    return rl.x[mask], rl.y[mask]


class TrackMapWidget(EmbedChart):
    """
    Embeddable matplotlib track-map chart.

    Parameters
    ----------
    parent  : CTk parent widget
    figsize : matplotlib figure size (default compact)
    **kw    : passed to EmbedChart / CTkFrame

    Usage
    -----
    map_widget.update(data, highlights=[...], title="...")

    highlights is a list of dicts:
        {
          'start':  float,   # lap-dist-pct 0–1
          'end':    float,   # lap-dist-pct 0–1
          'color':  str,     # matplotlib colour
          'label':  str,     # legend entry ('' to skip)
          'alpha':  float,   # default 0.85
          'lw':     float,   # line width (default 4)
          'zorder': int,     # default 3
        }
    """

    def __init__(self, parent, figsize=(10, 3), **kw):
        super().__init__(parent, figsize=figsize, **kw)
        self._rl: Optional[RacingLine] = None

    # ── Public API ────────────────────────────────────────────────────────────

    def update(self, data, highlights=None, title="Track Map",
               corner_dots=None, sector_splits=None):
        """
        Rebuild the track map.

        Parameters
        ----------
        data        : TelemetryData (may be None → shows placeholder)
        highlights  : list of zone dicts (see class docstring)
        title       : chart title
        corner_dots : list of {'pct': float, 'label': str, 'color': str}
        sector_splits : list of dist_pct floats marking sector boundaries
        """
        self.clear()
        ax = self.fig.add_subplot(111, facecolor='#0d1b2a')
        ax.set_aspect('equal')
        ax.axis('off')
        self.fig.patch.set_facecolor(PANEL)

        if data is None:
            ax.text(0.5, 0.5, "No telemetry loaded", ha='center', va='center',
                    color=DIM, fontsize=11, transform=ax.transAxes)
            self.draw()
            return

        # Reconstruct or re-use cached line
        rl = reconstruct_racing_line(data, lap_idx=0)
        if rl is None or len(rl.x) < 20:
            ax.text(0.5, 0.5, "Insufficient telemetry to draw track map\n"
                    "(need LatAccel + Speed channels)",
                    ha='center', va='center', color=DIM, fontsize=11,
                    transform=ax.transAxes, linespacing=1.8)
            self.draw()
            return

        self._rl = rl
        x, y = _normalize(rl.x.copy(), rl.y.copy())

        # ── 1. Grey track outline ─────────────────────────────────────────
        ax.plot(x, y, color='#3a4a6a', lw=6, solid_capstyle='round',
                solid_joinstyle='round', zorder=1)
        ax.plot(x, y, color='#1e2845', lw=4, solid_capstyle='round',
                solid_joinstyle='round', zorder=2)

        # ── 2. Sector dividers ────────────────────────────────────────────
        if sector_splits:
            for sp in sector_splits:
                sx, sy = _segment_by_pct(rl, max(0, sp - 0.005), min(1, sp + 0.005))
                sx, sy = _norm_pts(sx, sy, rl.x, rl.y)
                if len(sx):
                    ax.plot(sx, sy, color='white', lw=2, zorder=4, alpha=0.6)

        # ── 3. Highlighted zones ──────────────────────────────────────────
        seen_labels: set[str] = set()
        for h in (highlights or []):
            s_pct = h.get('start', 0.0)
            e_pct = h.get('end', 1.0)
            col   = h.get('color', ACCENT)
            label = h.get('label', '')
            alpha = h.get('alpha', 0.85)
            lw    = h.get('lw', 5)
            zo    = h.get('zorder', 3)

            hx, hy = _segment_by_pct(rl, s_pct, e_pct)
            if len(hx) < 2:
                continue
            # Normalize using the same origin/scale as full track
            hx = (hx - rl.x.mean()) / max(np.ptp(rl.x), np.ptp(rl.y), 1e-6)
            hy = (hy - rl.y.mean()) / max(np.ptp(rl.x), np.ptp(rl.y), 1e-6)

            lbl_arg = label if label and label not in seen_labels else '_nolegend_'
            ax.plot(hx, hy, color=col, lw=lw, alpha=alpha,
                    solid_capstyle='round', zorder=zo, label=lbl_arg)
            if label:
                seen_labels.add(label)

        # ── 4. Corner dots ────────────────────────────────────────────────
        if corner_dots:
            for cd in corner_dots:
                pct = cd.get('pct', 0.0)
                col = cd.get('color', TEXT)
                txt = cd.get('label', '')
                cx_arr, cy_arr = _segment_by_pct(rl, max(0, pct - 0.002),
                                                  min(1, pct + 0.002))
                if len(cx_arr):
                    # normalize
                    px = (cx_arr.mean() - rl.x.mean()) / max(np.ptp(rl.x), np.ptp(rl.y), 1e-6)
                    py = (cy_arr.mean() - rl.y.mean()) / max(np.ptp(rl.x), np.ptp(rl.y), 1e-6)
                    ax.scatter(px, py, s=60, color=col, zorder=6, edgecolors='white', lw=0.5)
                    if txt:
                        ax.annotate(txt, (px, py), textcoords='offset points',
                                    xytext=(5, 4), color=col, fontsize=7,
                                    fontweight='bold', zorder=7)

        # ── 5. Start/finish marker ────────────────────────────────────────
        x0 = (rl.x[0] - rl.x.mean()) / max(np.ptp(rl.x), np.ptp(rl.y), 1e-6)
        y0 = (rl.y[0] - rl.y.mean()) / max(np.ptp(rl.x), np.ptp(rl.y), 1e-6)
        ax.scatter(x0, y0, s=80, color='white', zorder=8, marker='D')

        # ── 6. Title & legend ─────────────────────────────────────────────
        ax.set_title(title, color=TEXT, fontsize=12, pad=6)
        handles, labels = ax.get_legend_handles_labels()
        if handles:
            ax.legend(handles, labels, loc='best', fontsize=9,
                      facecolor='#1e2845', edgecolor='#2a3050',
                      labelcolor=TEXT, markerscale=0.9,
                      framealpha=0.85)

        self.fig.tight_layout(pad=0.4)
        self.draw()


def _norm_pts(hx, hy, ref_x, ref_y):
    """Normalise a subset of points using the same scale as the full track."""
    denom = max(np.ptp(ref_x), np.ptp(ref_y), 1e-6)
    return (hx - ref_x.mean()) / denom, (hy - ref_y.mean()) / denom


# ── Convenience builders ──────────────────────────────────────────────────────

def highlights_from_issues(issues, data=None):
    """
    Build a highlight list from an AnalysisReport's issues list.

    Maps issue categories to track zones using named corners when available.
    If corner data is not available, returns broad zone hints.
    """
    from data.track_corners import get_named_corners

    track_name = data.track_name if data else None
    named = []
    if track_name:
        try:
            named = get_named_corners(track_name) or []
        except Exception:
            named = []

    hl = []
    seen_categories: set[str] = set()
    for iss in issues:
        cat = iss.category.value          # e.g. "Brakes", "Tires"
        color = CATEGORY_COLOR.get(cat, DIM)
        if not named:
            # No corner map — just return a generic full-track indicator
            if cat not in seen_categories:
                hl.append({'start': 0.0, 'end': 1.0,
                           'color': color, 'label': cat, 'alpha': 0.25, 'lw': 4})
                seen_categories.add(cat)
            continue

        label = cat if cat not in seen_categories else ''
        seen_categories.add(cat)

        for corner in named:
            s = corner.get('start_pct', corner.get('apex_pct', 0.0) - 0.02)
            e = corner.get('end_pct',   corner.get('apex_pct', 0.0) + 0.02)
            if cat in ('Brakes',):
                # Only braking zone (entry → apex)
                e = corner.get('apex_pct', e)
            hl.append({'start': max(0, s), 'end': min(1, e),
                       'color': color, 'label': label, 'alpha': 0.80, 'lw': 5})
            label = ''  # only label the first zone per category

    return hl


def highlights_from_corners(corner_report):
    """Build highlights from a CornerAnalysisReport, coloured by time delta."""
    if not corner_report or not corner_report.corners:
        return []
    max_delta = max((c.time_delta for c in corner_report.corners), default=1.0) or 1.0
    hl = []
    for cd in corner_report.corners:
        ratio = min(cd.time_delta / max_delta, 1.0)
        # Green → yellow → red as delta increases
        if ratio < 0.4:
            col = GREEN
        elif ratio < 0.7:
            col = YELLOW
        else:
            col = RED
        worst = (cd.corner_num - 1 == corner_report.worst_corner)
        hl.append({
            'start': cd.brake_pct,
            'end':   cd.exit_pct,
            'color': col,
            'label': f"T{cd.corner_num}" if worst else '',
            'alpha': 0.90 if worst else 0.70,
            'lw':    6 if worst else 4,
            'zorder': 5 if worst else 3,
        })
    return hl


def highlights_from_sectors(sector_report):
    """Build highlights from a SectorAnalysisReport, coloured by sector performance."""
    if not sector_report or not sector_report.sectors:
        return []
    sector_colors = [BLUE, GREEN, YELLOW, PURPLE, ACCENT, RED]
    hl = []
    for i, s in enumerate(sector_report.sectors):
        col = RED if i == sector_report.worst_sector else sector_colors[i % len(sector_colors)]
        hl.append({
            'start': s.start_pct,
            'end':   s.end_pct,
            'color': col,
            'label': f"S{i+1}{'  ← worst' if i == sector_report.worst_sector else ''}",
            'alpha': 0.85,
            'lw':    5,
        })
    return hl


def highlights_from_brakes(brake_report):
    """Build highlights from a BrakeAnalysisReport."""
    if not brake_report or not brake_report.profiles:
        return []
    hl = []
    for i, p in enumerate(brake_report.profiles):
        is_worst = p.corner_num == brake_report.weakest_corner
        col = RED if is_worst else ACCENT
        label = f"C{p.corner_num}" if is_worst else ''
        hl.append({
            'start': max(0.0, p.brake_start_pct - 0.005),
            'end':   min(1.0, p.apex_pct + 0.005),
            'color': col,
            'label': label,
            'alpha': 0.90 if is_worst else 0.65,
            'lw':    6 if is_worst else 4,
            'zorder': 5 if is_worst else 3,
        })
    return hl
