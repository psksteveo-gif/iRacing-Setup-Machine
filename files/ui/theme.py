"""Shared theme constants, helper functions, and reusable widgets."""

import customtkinter as ctk
import matplotlib
matplotlib.use('TkAgg')
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt

from core.analysis_engine import Severity

# ── Theme Constants ───────────────────────────────────────────────────────────
DARK   = "#08080A"   # deep black background
PANEL  = "#0F0F13"   # very dark purple-black panels
CARD   = "#14141A"   # dark purple-black cards
ACCENT = "#E8611A"   # burnt orange — primary buttons, key numbers, alerts
BLUE   = "#4A9EE8"   # vibrant medium purple — headers, borders, icons
TEXT   = "#F0EEE8"   # pale lavender off-white — main readable text
DIM    = "#8A8890"   # muted purple — secondary / hint text
GREEN  = "#2ECC8E"
YELLOW = "#F0A830"
RED    = "#E84040"
PURPLE = "#9B6EE8"
CARD_BORDER = "#252530"   # vibrant purple for card borders / drop-shadow effect
SEV_COLOR = {Severity.CRITICAL: RED, Severity.WARNING: YELLOW, Severity.INFO: BLUE}

# ── Helper Functions ──────────────────────────────────────────────────────────

def lbl(parent, text, size=11, bold=False, color=TEXT, **kw):
    return ctk.CTkLabel(parent, text=text,
        font=ctk.CTkFont(size=size, weight="bold" if bold else "normal"),
        text_color=color, **kw)

def card_frame(parent, **kw):
    return ctk.CTkFrame(parent, fg_color=CARD, corner_radius=8,
                        border_width=1, border_color=CARD_BORDER, **kw)


def bordered_card(parent, **kw):
    """Card with a prominent purple border — use for highlighted sections."""
    return ctk.CTkFrame(parent, fg_color=CARD, corner_radius=8,
                        border_width=1, border_color=BLUE, **kw)

def sec_lbl(parent, text):
    lbl(parent, text, 14, bold=True, color=PURPLE).pack(anchor='w', pady=(10, 2))

def stat_blk(parent, label_text, val, color=TEXT, tooltip=None):
    f = ctk.CTkFrame(parent, fg_color="transparent"); f.pack(side='left', padx=10)
    l = lbl(f, label_text, 11, color=DIM); l.pack()
    v = lbl(f, val, 15, bold=True, color=color); v.pack()
    if tooltip:
        _Tooltip(f, tooltip)
    return f


# ── Neon glow for charts (native, no external dependency) ───────────────────────
# mplcyberpunk is incompatible with matplotlib ≥3.11 (it calls the removed
# matplotlib.style.core API), so these reproduce its look. Names mirror it:
# add_glow / add_underglow / add_glow_effects. All default to the current axes and
# skip dashed guides.

_GLOW_GID = '_os_glow_copy'  # marks halo copies so they aren't glowed/filled again


def _iter_solid_lines(ax, max_points):
    for line in list(ax.get_lines()):
        if line.get_gid() == _GLOW_GID:
            continue
        if line.get_linestyle() not in ('-', 'solid'):
            continue
        x, y = line.get_data()
        try:
            n = len(x)
        except TypeError:
            continue
        if n == 0 or n > max_points:
            continue
        yield line, x, y


def add_glow(ax=None, n_glow=6, alpha=0.12, lw_step=1.3, max_points=6000):
    """Neon glow halo behind every solid line on `ax` (mplcyberpunk make_lines_glow).
    Glow copies are unlabelled (legends unaffected) and skip dashed guides."""
    if ax is None:
        ax = plt.gca()
    for line, x, y in _iter_solid_lines(ax, max_points):
        color = line.get_color()
        base_lw = line.get_linewidth()
        base_z = line.get_zorder()
        for i in range(1, n_glow + 1):
            ax.plot(x, y, color=color,
                    linewidth=base_lw + lw_step * i,
                    alpha=alpha * (1.0 - i / (n_glow + 1)),
                    solid_capstyle='round',
                    zorder=base_z - 0.1 * i, gid=_GLOW_GID)


def add_underglow(ax=None, alpha=0.55, max_points=6000):
    """Vertical gradient fill beneath every solid line (color → transparent),
    clipped to the area under the line. Preserves the axis limits."""
    if ax is None:
        ax = plt.gca()
    import numpy as np
    import matplotlib.colors as mcolors
    from matplotlib.patches import Polygon
    xlim, ylim = ax.get_xlim(), ax.get_ylim()
    for line, x, y in _iter_solid_lines(ax, max_points):
        x = np.asarray(x, dtype=float); y = np.asarray(y, dtype=float)
        rgb = mcolors.to_rgb(line.get_color())
        z = np.empty((256, 1, 4), dtype=float)
        z[:, :, :3] = rgb
        z[:, :, -1] = np.linspace(0.0, alpha, 256)[:, None]
        xmin, xmax = float(np.min(x)), float(np.max(x))
        ymin, ymax = float(np.min(y)), float(np.max(y))
        if xmax <= xmin or ymax <= ymin:
            continue
        im = ax.imshow(z, aspect='auto', origin='lower',
                       extent=[xmin, xmax, ymin, ymax],
                       zorder=line.get_zorder() - 0.05, alpha=1.0)
        verts = np.column_stack([x, y])
        verts = np.vstack([[xmin, ymin], verts, [xmax, ymin], [xmin, ymin]])
        clip = Polygon(verts, closed=True, facecolor='none', edgecolor='none')
        ax.add_patch(clip)
        im.set_clip_path(clip)
    ax.set_xlim(xlim); ax.set_ylim(ylim)


def add_glow_effects(ax=None, max_points=6000):
    """Full look: line glow + underglow gradient fill (mplcyberpunk add_glow_effects)."""
    if ax is None:
        ax = plt.gca()
    add_glow(ax, max_points=max_points)
    add_underglow(ax, max_points=max_points)


class _Tooltip:
    """Themed hover tooltip. Uses CTkToolTip when available (rounded, animated,
    cursor-following) and falls back to the lightweight legacy tooltip otherwise.
    Public API unchanged: _Tooltip(widget, text)."""
    def __init__(self, widget, text):
        try:
            from CTkToolTip import CTkToolTip
            # extra kwargs (text_color/wraplength/justify) are forwarded to the
            # internal CTkLabel via **message_kwargs.
            self._impl = CTkToolTip(
                widget, message=text, delay=0.45, follow=True,
                bg_color="#14141A", corner_radius=8,
                border_width=1, border_color=CARD_BORDER, alpha=0.96,
                text_color=TEXT, wraplength=320, justify="left")
        except Exception:
            self._impl = _LegacyTooltip(widget, text)


class _LegacyTooltip:
    """Hover tooltip — appears after a short delay, disappears on mouse-out."""
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tw = None
        self._job = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide,     add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, event=None):
        self._cancel_job()
        self._job = self.widget.after(450, self._show)

    def _cancel_job(self):
        if self._job:
            try: self.widget.after_cancel(self._job)
            except Exception: pass
            self._job = None

    def _show(self, event=None):
        if self.tw:
            return
        import tkinter as _tk
        x = self.widget.winfo_rootx() + 16
        tw = _tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_attributes("-topmost", True)
        tw.configure(bg="#14141A")
        _tk.Label(tw, text=self.text, font=("Segoe UI", 9),
                  fg=TEXT, bg="#14141A", padx=8, pady=5,
                  wraplength=320, justify="left").pack()
        tw.update_idletasks()
        tw_w = tw.winfo_reqwidth()
        tw_h = tw.winfo_reqheight()
        sw = tw.winfo_screenwidth()
        # Prefer showing above the widget; fall back to below
        y_above = self.widget.winfo_rooty() - tw_h - 4
        y_below = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        y = y_above if y_above > 0 else y_below
        if x + tw_w > sw:
            x = sw - tw_w - 8
        tw.wm_geometry(f"+{x}+{y}")
        self.tw = tw
        # Destroy if mouse wanders into the tooltip window itself
        tw.bind("<Enter>", self._hide)

    def _hide(self, event=None):
        self._cancel_job()
        if self.tw:
            try: self.tw.destroy()
            except Exception: pass
            self.tw = None


class EmbedChart(ctk.CTkFrame):
    def __init__(self, parent, figsize=(9, 3), responsive=True, **kw):
        super().__init__(parent, fg_color=PANEL, **kw)
        self.fig = Figure(figsize=figsize, facecolor='#0F0F13')
        self.canvas = FigureCanvasTkAgg(self.fig, master=self)
        self._tkc = self.canvas.get_tk_widget()
        self._tkc.pack(fill='both', expand=True)
        # Responsive layout: matplotlib's Tk backend resizes the figure but never
        # re-runs tight_layout, so subplot positions go stale on resize. Reflow once
        # the resize settles. Debounced; add='+' appends to the backend's handler.
        self._resize_job = None
        self._last_wh = (0, 0)
        if responsive:
            self._tkc.bind('<Configure>', self._on_configure, add='+')

    def _on_configure(self, event):
        if abs(event.width - self._last_wh[0]) < 6 and abs(event.height - self._last_wh[1]) < 6:
            return
        self._last_wh = (event.width, event.height)
        if self._resize_job is not None:
            try: self.after_cancel(self._resize_job)
            except Exception: pass
        self._resize_job = self.after(120, self._reflow)

    def _reflow(self):
        self._resize_job = None
        if not self.fig.axes:
            return
        try:
            self.fig.tight_layout()
        except Exception:
            pass
        self.canvas.draw_idle()

    def clear(self): self.fig.clear()
    def draw(self): self.canvas.draw()
    def destroy(self):
        if self._resize_job is not None:
            try: self.after_cancel(self._resize_job)
            except Exception: pass
        plt.close(self.fig)
        super().destroy()
    def std_ax(self, title="", xlabel="Track %"):
        ax = self.fig.add_subplot(111, facecolor='#0F0F13')
        ax.set_title(title, color=TEXT, fontsize=13, pad=6)
        ax.tick_params(colors=DIM, labelsize=10, which='both')
        for sp in ax.spines.values():
            sp.set_color('#1C1C24')
            sp.set_alpha(0.4)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.set_xlabel(xlabel, color=DIM, fontsize=10)
        ax.yaxis.grid(True, alpha=0.15, color='#1C1C24', linewidth=0.8)
        ax.xaxis.grid(False)
        ax.set_axisbelow(True)
        return ax


class IssueCard(ctk.CTkFrame):
    def __init__(self, parent, issue, **kw):
        super().__init__(parent, fg_color="#14141A", corner_radius=6, **kw)
        c = SEV_COLOR[issue.severity]
        icon = {"critical": "🔴", "warning": "🟡", "info": "🔵"}[issue.severity.value]
        hdr = ctk.CTkFrame(self, fg_color="transparent", cursor="hand2"); hdr.pack(fill='x', padx=8, pady=5)
        lbl(hdr, f"{icon}  {issue.title}", 13, bold=True, color=c, anchor='w').pack(side='left', fill='x', expand=True)
        ctk.CTkLabel(hdr, text=issue.category.value, font=ctk.CTkFont(size=11),
            text_color=DIM, fg_color="#14141A", corner_radius=4).pack(side='right', padx=4)
        self._d = ctk.CTkFrame(self, fg_color="transparent")
        lbl(self._d, issue.description, 12, color=DIM, wraplength=520, justify='left', anchor='w').pack(fill='x', padx=8, pady=(0, 3))
        lbl(self._d, f"💡 {issue.recommendation}", 12, color=BLUE, wraplength=520, justify='left', anchor='w').pack(fill='x', padx=8, pady=(0, 6))
        self._open = False
        for w in [hdr] + list(hdr.winfo_children()): w.bind("<Button-1>", self._toggle)
    def _toggle(self, _=None):
        self._open = not self._open
        (self._d.pack(fill='x') if self._open else self._d.pack_forget())


# ── Design System re-exports ───────────────────────────────────────────────────
from ui.ds_theme import COLORS, FONTS, RADIUS, SPACING, SEVERITY, TABS, AI_SUBTABS
