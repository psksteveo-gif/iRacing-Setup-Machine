"""
OBS Overlay — floating, always-on-top telemetry HUD.

Shows in real-time:
  • Current lap time / last lap / best lap
  • Speed + gear
  • Throttle / Brake bars
  • Tire temperature grid (4 corners, colour-coded)
  • Fuel level + estimated laps remaining
  • Live lap-delta sparkline vs. session best (when IBT data is loaded)

Designed to be captured by OBS as a Window or Display source — the window
has a black background with a small footprint (~340 × 280 px) so it can be
chroma-keyed or positioned as a corner widget.

Usage (from main.py)::

    from ui.obs_overlay import OBSOverlay
    overlay = OBSOverlay(root, live_monitor, ref_lap_delta=None)
    overlay.show()   # non-blocking; creates a Toplevel
    overlay.hide()
"""
from __future__ import annotations

import math
import time
from typing import Optional

import customtkinter as ctk

try:
    from ui.theme import DARK, PANEL, CARD, TEXT, DIM, GREEN, YELLOW, RED, ACCENT
except ImportError:
    DARK = "#0c0a12"; PANEL = "#140e1e"; CARD = "#1e1530"
    TEXT = "#e0e0e0"; DIM = "#888"; GREEN = "#2ecc71"
    YELLOW = "#f1c40f"; RED = "#e74c3c"; ACCENT = "#e74c3c"

from core.live_telemetry import LiveSample, FuelTracker

# ── Palette ──────────────────────────────────────────────────────────────────
_BG         = "#0d0d12"       # near-black for chroma-key friendliness
_BORDER     = "#2a2a40"
_HOT        = "#e74c3c"       # tyre temp ≥ 95 °C
_WARM       = "#f1c40f"       # tyre temp 75–95 °C
_COLD       = "#3498db"       # tyre temp < 55 °C
_OPTIMAL    = "#2ecc71"       # tyre temp 55–75 °C
_THROTTLE   = "#2ecc71"
_BRAKE_CLR  = "#e74c3c"

_W = 340     # overlay width
_ROW_H = 22  # row height


def _temp_color(t: float) -> str:
    if t <= 0:      return DIM
    if t < 55:      return _COLD
    if t < 75:      return _OPTIMAL
    if t < 95:      return _WARM
    return _HOT


def _fmt_time(t: float) -> str:
    if t <= 0:
        return "--:--.---"
    m = int(t // 60)
    s = t - m * 60
    return f"{m}:{s:06.3f}"


def _delta_color(d: float) -> str:
    if abs(d) < 0.01:
        return TEXT
    return GREEN if d < 0 else RED


# ═════════════════════════════════════════════════════════════════════════════
class OBSOverlay:
    """
    Floating HUD window. Call show()/hide() to toggle.
    Subscribe to the LiveTelemetryMonitor by passing it at construction.
    """

    def __init__(
        self,
        parent: ctk.CTk,
        live_monitor,                  # LiveTelemetryMonitor | None
        ref_lap_delta: Optional[list] = None,  # list[(dist_pct, delta_s)]
    ):
        self._parent        = parent
        self._monitor       = live_monitor
        self._ref_delta     = ref_lap_delta   # for sparkline
        self._win: ctk.CTkToplevel | None = None
        self._last_sample: LiveSample | None = None
        self._delta_history: list[float] = []  # last 60 delta points
        self._fuel_tracker  = FuelTracker()

    # ── Public API ────────────────────────────────────────────────────────

    def show(self):
        if self._win and self._win.winfo_exists():
            self._win.lift()
            return
        self._build_window()
        if self._monitor:
            self._monitor.add_callback(self._on_sample)

    def hide(self):
        if self._monitor:
            try:
                self._monitor.remove_callback(self._on_sample)
            except Exception:
                pass
        if self._win and self._win.winfo_exists():
            self._win.destroy()
        self._win = None

    def is_visible(self) -> bool:
        return self._win is not None and self._win.winfo_exists()

    def set_ref_delta(self, ref_lap_delta: list):
        """Update the reference lap delta data (called when a new IBT loads)."""
        self._ref_delta = ref_lap_delta

    # ── Window construction ───────────────────────────────────────────────

    def _build_window(self):
        win = ctk.CTkToplevel(self._parent)
        win.title("Live HUD")
        win.geometry(f"{_W}x310+40+40")
        win.resizable(False, False)
        win.configure(fg_color=_BG)
        win.attributes("-topmost", True)
        win.overrideredirect(True)          # frameless
        win.protocol("WM_DELETE_WINDOW", self.hide)
        self._win = win

        # ── Drag handle ──────────────────────────────────────────────
        drag = ctk.CTkFrame(win, fg_color=_BORDER, height=18, corner_radius=0)
        drag.pack(fill="x")
        ctk.CTkLabel(drag, text="⠿  iRacing HUD  — drag to move",
                     font=ctk.CTkFont(size=9), text_color=DIM).pack(side="left", padx=6)
        ctk.CTkButton(drag, text="✕", width=18, height=18,
                      fg_color="transparent", text_color=DIM, hover_color=_HOT,
                      command=self.hide).pack(side="right", padx=2)
        drag.bind("<ButtonPress-1>",   self._drag_start)
        drag.bind("<B1-Motion>",       self._drag_motion)
        for child in drag.winfo_children():
            child.bind("<ButtonPress-1>", self._drag_start)
            child.bind("<B1-Motion>",     self._drag_motion)
        self._drag_x = 0; self._drag_y = 0

        # ── Lap times row ─────────────────────────────────────────────
        lt = ctk.CTkFrame(win, fg_color=PANEL, corner_radius=0, height=_ROW_H * 2)
        lt.pack(fill="x", padx=2, pady=(2, 0))
        lt.pack_propagate(False)

        self._lbl_cur  = self._big_lbl(lt, "--:--.---", 19, bold=True, color=TEXT)
        self._lbl_cur.pack(side="left", padx=(8, 4), pady=2)
        self._lbl_delta = self._big_lbl(lt, "Δ ---.---", 14, color=DIM)
        self._lbl_delta.pack(side="left", padx=2)

        right = ctk.CTkFrame(lt, fg_color="transparent")
        right.pack(side="right", padx=6)
        self._lbl_best = self._small_lbl(right, "Best  --:--.---")
        self._lbl_best.pack(anchor="e")
        self._lbl_last = self._small_lbl(right, "Last  --:--.---")
        self._lbl_last.pack(anchor="e")

        # ── Speed / Gear / RPM ───────────────────────────────────────
        sg = ctk.CTkFrame(win, fg_color=_BG, height=_ROW_H)
        sg.pack(fill="x", padx=4, pady=(3, 0))
        self._lbl_speed = self._big_lbl(sg, "  0 km/h", 15, bold=True)
        self._lbl_speed.pack(side="left", padx=(4, 0))
        self._lbl_gear  = self._big_lbl(sg, "N", 20, bold=True, color=YELLOW)
        self._lbl_gear.pack(side="left", padx=8)
        self._lbl_rpm   = self._small_lbl(sg, "0 rpm")
        self._lbl_rpm.pack(side="left")
        self._lbl_fuel  = self._small_lbl(sg, "⛽ --L", color=GREEN)
        self._lbl_fuel.pack(side="right", padx=6)

        # ── Throttle / Brake bars ────────────────────────────────────
        bars = ctk.CTkFrame(win, fg_color=_BG)
        bars.pack(fill="x", padx=4, pady=(2, 0))
        self._thr_bar = self._make_bar(bars, _THROTTLE, "Thr")
        self._thr_bar.pack(fill="x", pady=1)
        self._brk_bar = self._make_bar(bars, _BRAKE_CLR, "Brk")
        self._brk_bar.pack(fill="x", pady=1)

        # ── Tyre temps grid ──────────────────────────────────────────
        ty = ctk.CTkFrame(win, fg_color=_BG)
        ty.pack(fill="x", padx=4, pady=(4, 0))
        ctk.CTkLabel(ty, text="TYRES", font=ctk.CTkFont(size=9, weight="bold"),
                     text_color=DIM).pack(anchor="w")
        grid = ctk.CTkFrame(ty, fg_color=_BG)
        grid.pack(fill="x")
        self._tyre_lbls: dict[str, ctk.CTkLabel] = {}
        corners = [("FL", 0, 0), ("FR", 0, 1), ("RL", 1, 0), ("RR", 1, 1)]
        for name, row, col in corners:
            f = ctk.CTkFrame(grid, fg_color=CARD, corner_radius=4, width=72, height=36)
            f.grid(row=row, column=col, padx=3, pady=2, sticky="nsew")
            f.grid_propagate(False)
            ctk.CTkLabel(f, text=name, font=ctk.CTkFont(size=9), text_color=DIM).place(x=4, y=2)
            val = ctk.CTkLabel(f, text="--°", font=ctk.CTkFont(size=13, weight="bold"),
                               text_color=DIM)
            val.place(relx=0.5, rely=0.6, anchor="center")
            self._tyre_lbls[name] = val
        grid.columnconfigure(0, weight=1); grid.columnconfigure(1, weight=1)

        # ── Delta sparkline canvas ───────────────────────────────────
        self._spark_canvas = ctk.CTkCanvas(win, width=_W - 8, height=28,
                                            bg=_BG, highlightthickness=0)
        self._spark_canvas.pack(padx=4, pady=(4, 2))
        self._draw_spark()

        # Start the UI refresh loop
        self._refresh()

    # ── Helpers ───────────────────────────────────────────────────────────

    def _big_lbl(self, parent, text, size=14, bold=False, color=TEXT):
        weight = "bold" if bold else "normal"
        return ctk.CTkLabel(parent, text=text,
                            font=ctk.CTkFont(size=size, weight=weight),
                            text_color=color)

    def _small_lbl(self, parent, text, color=DIM):
        return ctk.CTkLabel(parent, text=text,
                            font=ctk.CTkFont(size=10), text_color=color)

    def _make_bar(self, parent, color, label: str):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        ctk.CTkLabel(row, text=label, font=ctk.CTkFont(size=9),
                     text_color=DIM, width=22).pack(side="left")
        inner = ctk.CTkFrame(row, fg_color=_BORDER, height=10, corner_radius=3)
        inner.pack(side="left", fill="x", expand=True)
        inner.pack_propagate(False)
        fill = ctk.CTkFrame(inner, fg_color=color, height=10, corner_radius=3)
        fill.place(relx=0, rely=0, relheight=1, relwidth=0)
        row._fill = fill
        row._color = color
        return row

    def _set_bar(self, bar_row, pct: float):
        bar_row._fill.place(relwidth=max(0.0, min(1.0, pct)))

    # ── Drag support ──────────────────────────────────────────────────────

    def _drag_start(self, event):
        self._drag_x = event.x_root - self._win.winfo_x()
        self._drag_y = event.y_root - self._win.winfo_y()

    def _drag_motion(self, event):
        x = event.x_root - self._drag_x
        y = event.y_root - self._drag_y
        self._win.geometry(f"+{x}+{y}")

    # ── Live sample callback (called from monitor thread) ─────────────────

    def _on_sample(self, sample: LiveSample):
        self._last_sample = sample
        self._fuel_tracker.update(sample)

    # ── UI refresh loop ───────────────────────────────────────────────────

    def _refresh(self):
        if not (self._win and self._win.winfo_exists()):
            return
        s = self._last_sample
        if s and s.is_connected:
            self._apply_sample(s)
        else:
            self._show_disconnected()
        self._win.after(100, self._refresh)   # 10 Hz

    def _apply_sample(self, s: LiveSample):
        # Lap times
        self._lbl_cur.configure(text=_fmt_time(s.lap_time), text_color=TEXT)
        self._lbl_best.configure(text=f"Best  {_fmt_time(s.best_lap)}")
        self._lbl_last.configure(text=f"Last  {_fmt_time(s.last_lap)}")

        # Live delta vs best lap (interpolate from ref data)
        delta = self._compute_delta(s)
        if delta is not None:
            sign = "+" if delta >= 0 else ""
            self._lbl_delta.configure(
                text=f"Δ {sign}{delta:.3f}",
                text_color=_delta_color(delta),
            )
            self._delta_history.append(delta)
            if len(self._delta_history) > 120:
                self._delta_history.pop(0)
            self._draw_spark()
        else:
            self._lbl_delta.configure(text="Δ ---.---", text_color=DIM)

        # Speed / gear / rpm
        from core import units
        spd = s.speed_ms * units.speed_factor()
        unit = units.speed_label()
        self._lbl_speed.configure(text=f"{spd:.0f} {unit}")
        gear_str = "R" if s.gear == -1 else ("N" if s.gear == 0 else str(s.gear))
        self._lbl_gear.configure(text=gear_str)
        self._lbl_rpm.configure(text=f"{s.rpm:.0f} rpm")
        laps_left = self._fuel_tracker.laps_remaining(s.fuel_level)
        if laps_left > 0:
            fuel_txt = f"⛽ {s.fuel_level:.1f}L  ~{laps_left:.1f} laps"
        else:
            fuel_txt = f"⛽ {s.fuel_level:.1f}L"
        self._lbl_fuel.configure(
            text=fuel_txt,
            text_color=GREEN if s.fuel_pct > 0.2 else YELLOW if s.fuel_pct > 0.1 else RED,
        )

        # Bars
        self._set_bar(self._thr_bar, s.throttle)
        self._set_bar(self._brk_bar, s.brake)

        # Tyre temps
        corner_map = {"FL": "lf", "FR": "rf", "RL": "lr", "RR": "rr"}
        for corner, key in corner_map.items():
            temps = s.tire_temps.get(key, {})
            avg = sum(temps.values()) / len(temps) if temps else 0.0
            lbl = self._tyre_lbls[corner]
            if avg > 0:
                lbl.configure(text=f"{avg:.0f}°", text_color=_temp_color(avg))
            else:
                lbl.configure(text="--°", text_color=DIM)

    def _show_disconnected(self):
        self._lbl_cur.configure(text="NOT CONNECTED", text_color=DIM)
        self._lbl_delta.configure(text="", text_color=DIM)
        self._lbl_best.configure(text=""); self._lbl_last.configure(text="")
        self._lbl_speed.configure(text="  0 km/h")
        self._lbl_gear.configure(text="N")
        self._lbl_rpm.configure(text="")
        self._lbl_fuel.configure(text="⛽ --L", text_color=DIM)
        self._set_bar(self._thr_bar, 0); self._set_bar(self._brk_bar, 0)
        for lbl in self._tyre_lbls.values():
            lbl.configure(text="--°", text_color=DIM)

    def _compute_delta(self, s: LiveSample) -> Optional[float]:
        """Interpolate lap delta at current dist_pct from ref_delta data."""
        if not self._ref_delta or s.lap_dist_pct <= 0:
            return None
        try:
            pts = self._ref_delta  # list of (dist_pct, delta_s)
            for i in range(len(pts) - 1):
                d0, v0 = pts[i]
                d1, v1 = pts[i + 1]
                if d0 <= s.lap_dist_pct < d1:
                    frac = (s.lap_dist_pct - d0) / max(1e-6, d1 - d0)
                    return v0 + frac * (v1 - v0)
            return pts[-1][1] if pts else None
        except Exception:
            return None

    def _draw_spark(self):
        c = self._spark_canvas
        if not (self._win and self._win.winfo_exists()):
            return
        c.delete("all")
        w = _W - 8; h = 28
        c.create_rectangle(0, 0, w, h, fill=_BG, outline="")
        # Zero line
        mid = h // 2
        c.create_line(0, mid, w, mid, fill=_BORDER, width=1)
        pts = self._delta_history
        if len(pts) < 2:
            return
        mn = min(pts); mx = max(pts)
        span = max(0.1, mx - mn)
        step = w / (len(pts) - 1)
        coords = []
        for i, v in enumerate(pts):
            x = i * step
            y = h - (v - mn) / span * (h - 4) - 2
            coords += [x, y]
        # Draw coloured segments
        for i in range(len(pts) - 1):
            x0, y0 = coords[i*2], coords[i*2+1]
            x1, y1 = coords[i*2+2], coords[i*2+3]
            col = GREEN if pts[i] < 0 else RED
            c.create_line(x0, y0, x1, y1, fill=col, width=2)
