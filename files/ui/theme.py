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


class _Tooltip:
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
    def __init__(self, parent, figsize=(9, 3), **kw):
        super().__init__(parent, fg_color=PANEL, **kw)
        self.fig = Figure(figsize=figsize, facecolor='#0F0F13')
        self.canvas = FigureCanvasTkAgg(self.fig, master=self)
        self.canvas.get_tk_widget().pack(fill='both', expand=True)
    def clear(self): self.fig.clear()
    def draw(self): self.canvas.draw()
    def destroy(self):
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
