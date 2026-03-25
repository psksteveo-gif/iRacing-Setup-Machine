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
    scale = max(x.max() - x.min(), y.max() - y.min())
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
            hx = (hx - rl.x.mean()) / max(rl.x.max() - rl.x.min(), rl.y.max() - rl.y.min(), 1e-6)
            hy = (hy - rl.y.mean()) / max(rl.x.max() - rl.x.min(), rl.y.max() - rl.y.min(), 1e-6)

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
                    px = (cx_arr.mean() - rl.x.mean()) / max(rl.x.max() - rl.x.min(), rl.y.max() - rl.y.min(), 1e-6)
                    py = (cy_arr.mean() - rl.y.mean()) / max(rl.x.max() - rl.x.min(), rl.y.max() - rl.y.min(), 1e-6)
                    ax.scatter(px, py, s=60, color=col, zorder=6, edgecolors='white', lw=0.5)
                    if txt:
                        ax.annotate(txt, (px, py), textcoords='offset points',
                                    xytext=(5, 4), color=col, fontsize=7,
                                    fontweight='bold', zorder=7)

        # ── 5. Start/finish marker ────────────────────────────────────────
        x0 = (rl.x[0] - rl.x.mean()) / max(rl.x.max() - rl.x.min(), rl.y.max() - rl.y.min(), 1e-6)
        y0 = (rl.y[0] - rl.y.mean()) / max(rl.x.max() - rl.x.min(), rl.y.max() - rl.y.min(), 1e-6)
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


    def gear_overlay(self, data, lap_idx: int = 0, title: str = "Gear Map"):
        """
        Colour the track by gear number for the given lap.
        Low gears = red/orange, high gears = green/blue.
        """
        self.clear()
        from core.racing_line import reconstruct_racing_line
        ax = self.fig.add_subplot(111, facecolor='#0d1b2a')
        ax.set_aspect('equal')
        ax.axis('off')
        self.fig.patch.set_facecolor(PANEL)

        rl = reconstruct_racing_line(data, lap_idx=lap_idx)
        if rl is None or len(rl.x) < 20:
            ax.text(0.5, 0.5, "Insufficient telemetry for gear map",
                    ha='center', va='center', color=DIM, fontsize=11,
                    transform=ax.transAxes)
            self.draw()
            return

        gear_ch = data.get_channel('Gear')
        dist_ch = data.get_channel('LapDistPct')
        if gear_ch is None or dist_ch is None:
            ax.text(0.5, 0.5, "No Gear channel in telemetry",
                    ha='center', va='center', color=DIM, fontsize=11,
                    transform=ax.transAxes)
            self.draw()
            return

        bounds = data.lap_boundaries
        if len(bounds) <= lap_idx + 1:
            self.draw()
            return

        s, e = bounds[lap_idx], bounds[lap_idx + 1]
        gear_lap = np.asarray(gear_ch[s:e], float)
        dist_lap = np.asarray(dist_ch[s:e], float)

        # Draw grey base track
        denom = max(rl.x.max() - rl.x.min(), rl.y.max() - rl.y.min(), 1e-6)
        nx = (rl.x - rl.x.mean()) / denom
        ny = (rl.y - rl.y.mean()) / denom
        ax.plot(nx, ny, color='#2a3a5a', lw=7, solid_capstyle='round', zorder=1)

        # Gear colour map: 1=red, 2=orange, 3=yellow, 4=lime, 5=cyan, 6=blue, 7+=purple
        _gear_colors = {1: '#e74c3c', 2: '#e67e22', 3: '#f1c40f',
                        4: '#2ecc71', 5: '#1abc9c', 6: '#3498db', 7: '#9b59b6'}
        max_gear = max(int(g) for g in gear_lap if g > 0) if any(g > 0 for g in gear_lap) else 7
        plotted_gears: set = set()

        # Walk the track and colour segments
        n = len(rl.dist_pct)
        for frame_i in range(len(dist_lap) - 1):
            g = int(gear_lap[frame_i])
            if g <= 0:
                continue
            d0, d1 = float(dist_lap[frame_i]), float(dist_lap[frame_i + 1])
            # Find the corresponding track positions
            idx = np.searchsorted(rl.dist_pct, d0)
            if idx >= n - 1:
                idx = n - 2
            px = (rl.x[idx] - rl.x.mean()) / denom
            py = (rl.y[idx] - rl.y.mean()) / denom
            px2 = (rl.x[min(idx+1, n-1)] - rl.x.mean()) / denom
            py2 = (rl.y[min(idx+1, n-1)] - rl.y.mean()) / denom
            col = _gear_colors.get(g, '#9b59b6')
            lbl_arg = f"Gear {g}" if g not in plotted_gears else '_nolegend_'
            ax.plot([px, px2], [py, py2], color=col, lw=5,
                    solid_capstyle='round', zorder=2, label=lbl_arg, alpha=0.85)
            plotted_gears.add(g)

        # Start marker
        ax.scatter(nx[0], ny[0], s=80, color='white', zorder=8, marker='D')
        ax.set_title(title, color=TEXT, fontsize=12, pad=6)
        handles, labels = ax.get_legend_handles_labels()
        if handles:
            # Sort by gear number
            pairs = sorted(zip(labels, handles),
                           key=lambda p: int(p[0].split()[-1]) if p[0].startswith('Gear') else 99)
            labels2, handles2 = zip(*pairs) if pairs else ([], [])
            ax.legend(list(handles2), list(labels2), loc='best', fontsize=9,
                      facecolor='#1e2845', edgecolor='#2a3050',
                      labelcolor=TEXT, markerscale=0.9, framealpha=0.85)
        self.fig.tight_layout(pad=0.4)
        self.draw()

    def animate_replay(self, data, lap_idx: int = 0, speed_mult: float = 8.0):
        """
        Animate a dot travelling around the track for the given lap.
        speed_mult controls playback speed (8x = 8× faster than real-time).
        Calls self.draw() on each frame via Tkinter after().
        """
        from core.racing_line import reconstruct_racing_line

        rl = reconstruct_racing_line(data, lap_idx=lap_idx)
        bounds = data.lap_boundaries
        if rl is None or len(rl.x) < 20 or len(bounds) <= lap_idx + 1:
            return

        # Build the normalised track
        denom = max(rl.x.max() - rl.x.min(), rl.y.max() - rl.y.min(), 1e-6)
        nx = (rl.x - rl.x.mean()) / denom
        ny = (rl.y - rl.y.mean()) / denom

        # Speed channel for dot colour
        speed_ch = data.get_channel('Speed')
        dist_ch  = data.get_channel('LapDistPct')
        s, e = bounds[lap_idx], bounds[lap_idx + 1]
        lap_dist = np.asarray(dist_ch[s:e], float) if dist_ch is not None else None
        lap_speed = np.asarray(speed_ch[s:e], float) if speed_ch is not None else None

        tick = float(getattr(data, 'tick_rate', None) or 60)
        # ms per IBT frame at real time, divided by speed_mult
        ms_per_frame = max(1, int(1000.0 / (tick * speed_mult)))

        n_frames = e - s
        self._replay_frame = 0
        self._replay_running = True

        # Draw static base
        self.clear()
        ax = self.fig.add_subplot(111, facecolor='#0d1b2a')
        ax.set_aspect('equal')
        ax.axis('off')
        self.fig.patch.set_facecolor(PANEL)
        ax.plot(nx, ny, color='#2a3a5a', lw=6, solid_capstyle='round', zorder=1)
        ax.plot(nx, ny, color='#1e2845', lw=4, solid_capstyle='round', zorder=2)
        ax.scatter(nx[0], ny[0], s=80, color='white', zorder=8, marker='D')
        # Speed-coloured trail placeholder
        self._replay_dot, = ax.plot([], [], 'o', ms=10, color=ACCENT, zorder=9)
        self._replay_trail_x = []
        self._replay_trail_y = []
        self._replay_trail_line, = ax.plot([], [], '-', color=ACCENT, lw=2, alpha=0.5, zorder=8)
        ax.set_title("Lap Replay — ▶", color=TEXT, fontsize=12, pad=6)
        self._replay_ax = ax
        self._replay_nx = nx
        self._replay_ny = ny
        self._replay_rl = rl
        self._replay_denom = denom
        self._replay_lap_dist = lap_dist
        self._replay_lap_speed = lap_speed
        self._replay_n_frames = n_frames
        self.draw()

        def _step():
            if not self._replay_running:
                return
            fi = self._replay_frame
            if fi >= self._replay_n_frames:
                self._replay_frame = 0
                self._replay_trail_x.clear()
                self._replay_trail_y.clear()
                self.canvas.get_tk_widget().after(500, _step)
                return
            if self._replay_lap_dist is not None and fi < len(self._replay_lap_dist):
                d_pct = float(self._replay_lap_dist[fi])
                idx = int(np.searchsorted(self._replay_rl.dist_pct, d_pct))
                idx = min(idx, len(self._replay_nx) - 1)
                px, py = float(self._replay_nx[idx]), float(self._replay_ny[idx])
                # Colour dot by speed
                col = ACCENT
                if self._replay_lap_speed is not None and fi < len(self._replay_lap_speed):
                    sp = float(self._replay_lap_speed[fi])
                    sp_max = float(self._replay_lap_speed.max()) if self._replay_lap_speed is not None else 200
                    ratio = min(sp / max(sp_max, 1), 1.0)
                    # Green (fast) → red (slow)
                    r = int((1 - ratio) * 220)
                    g = int(ratio * 200)
                    col = f'#{r:02x}{g:02x}50'
                self._replay_dot.set_data([px], [py])
                self._replay_dot.set_color(col)
                self._replay_trail_x.append(px)
                self._replay_trail_y.append(py)
                if len(self._replay_trail_x) > 60:
                    self._replay_trail_x.pop(0)
                    self._replay_trail_y.pop(0)
                self._replay_trail_line.set_data(self._replay_trail_x, self._replay_trail_y)
                try:
                    self.canvas.draw_idle()
                except Exception:
                    pass
            self._replay_frame += 1
            self.canvas.get_tk_widget().after(ms_per_frame, _step)

        self.canvas.get_tk_widget().after(ms_per_frame, _step)

    def stop_replay(self):
        """Stop any running lap replay animation."""
        self._replay_running = False


def _norm_pts(hx, hy, ref_x, ref_y):
    """Normalise a subset of points using the same scale as the full track."""
    denom = max(ref_x.max() - ref_x.min(), ref_y.max() - ref_y.min(), 1e-6)
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
