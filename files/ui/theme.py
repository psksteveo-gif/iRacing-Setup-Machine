"""Shared theme constants, helper functions, and reusable widgets."""

import customtkinter as ctk
import matplotlib
matplotlib.use('TkAgg')
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt

from core.analysis_engine import Severity

# ── Theme Constants ───────────────────────────────────────────────────────────
DARK = "#1a1a2e"; PANEL = "#16213e"; CARD = "#0f3460"
ACCENT = "#e94560"; BLUE = "#00b4d8"; TEXT = "#eaeaea"
DIM = "#8a8fa3"; GREEN = "#2ecc71"; YELLOW = "#f39c12"
RED = "#e74c3c"; PURPLE = "#9b59b6"
SEV_COLOR = {Severity.CRITICAL: RED, Severity.WARNING: YELLOW, Severity.INFO: BLUE}

# ── Helper Functions ──────────────────────────────────────────────────────────

def lbl(parent, text, size=11, bold=False, color=TEXT, **kw):
    return ctk.CTkLabel(parent, text=text,
        font=ctk.CTkFont(size=size, weight="bold" if bold else "normal"),
        text_color=color, **kw)

def card_frame(parent, **kw):
    return ctk.CTkFrame(parent, fg_color=CARD, corner_radius=8, **kw)

def sec_lbl(parent, text):
    lbl(parent, text, 12, bold=True, color=BLUE).pack(anchor='w', pady=(10, 2))

def stat_blk(parent, label_text, val, color=TEXT, tooltip=None):
    f = ctk.CTkFrame(parent, fg_color="transparent"); f.pack(side='left', padx=10)
    l = lbl(f, label_text, 9, color=DIM); l.pack()
    v = lbl(f, val, 13, bold=True, color=color); v.pack()
    if tooltip:
        _Tooltip(f, tooltip)
    return f


class _Tooltip:
    """Simple hover tooltip for any widget."""
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tw = None
        widget.bind("<Enter>", self._show)
        widget.bind("<Leave>", self._hide)
    def _show(self, event=None):
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self.tw = tw = ctk.CTkToplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.configure(fg_color="#2a3050")
        lbl(tw, self.text, 9, color=TEXT).pack(padx=8, pady=4)
        tw.update_idletasks()
        sw = tw.winfo_screenwidth()
        sh = tw.winfo_screenheight()
        tw_w = tw.winfo_reqwidth()
        tw_h = tw.winfo_reqheight()
        if x + tw_w > sw:
            x = sw - tw_w - 4
        if y + tw_h > sh:
            y = self.widget.winfo_rooty() - tw_h - 4
        tw.wm_geometry(f"+{x}+{y}")
    def _hide(self, event=None):
        if self.tw:
            self.tw.destroy()
            self.tw = None


class EmbedChart(ctk.CTkFrame):
    def __init__(self, parent, figsize=(9, 3), **kw):
        super().__init__(parent, fg_color=PANEL, **kw)
        self.fig = Figure(figsize=figsize, facecolor=PANEL)
        self.canvas = FigureCanvasTkAgg(self.fig, master=self)
        self.canvas.get_tk_widget().pack(fill='both', expand=True)
    def clear(self): self.fig.clear()
    def draw(self): self.canvas.draw()
    def destroy(self):
        plt.close(self.fig)
        super().destroy()
    def std_ax(self, title="", xlabel="Track %"):
        ax = self.fig.add_subplot(111, facecolor='#0d1b2a')
        ax.set_title(title, color=TEXT, fontsize=11, pad=6)
        ax.tick_params(colors=DIM, labelsize=8)
        for sp in ax.spines.values(): sp.set_color('#2a3050')
        ax.spines['top'].set_visible(False); ax.spines['right'].set_visible(False)
        ax.set_xlabel(xlabel, color=DIM, fontsize=9)
        ax.grid(True, alpha=0.1, color='#3a4a6a')
        return ax


class IssueCard(ctk.CTkFrame):
    def __init__(self, parent, issue, **kw):
        super().__init__(parent, fg_color="#1e2845", corner_radius=6, **kw)
        c = SEV_COLOR[issue.severity]
        icon = {"critical": "🔴", "warning": "🟡", "info": "🔵"}[issue.severity.value]
        hdr = ctk.CTkFrame(self, fg_color="transparent", cursor="hand2"); hdr.pack(fill='x', padx=8, pady=5)
        lbl(hdr, f"{icon}  {issue.title}", 12, bold=True, color=c, anchor='w').pack(side='left', fill='x', expand=True)
        ctk.CTkLabel(hdr, text=issue.category.value, font=ctk.CTkFont(size=9),
            text_color=DIM, fg_color="#2a3050", corner_radius=4).pack(side='right', padx=4)
        self._d = ctk.CTkFrame(self, fg_color="transparent")
        lbl(self._d, issue.description, 11, color=DIM, wraplength=520, justify='left', anchor='w').pack(fill='x', padx=8, pady=(0, 3))
        lbl(self._d, f"💡 {issue.recommendation}", 11, color=BLUE, wraplength=520, justify='left', anchor='w').pack(fill='x', padx=8, pady=(0, 6))
        self._open = False
        for w in [hdr] + list(hdr.winfo_children()): w.bind("<Button-1>", self._toggle)
    def _toggle(self, _=None):
        self._open = not self._open
        (self._d.pack(fill='x') if self._open else self._d.pack_forget())
