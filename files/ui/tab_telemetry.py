"""Telemetry tab mixin — charts, overlays, track maps, replay."""

import time
import numpy as np
import customtkinter as ctk
import matplotlib.cm as cm
from matplotlib.colors import Normalize
from matplotlib.lines import Line2D

from ui.theme import (DARK, PANEL, CARD, ACCENT, BLUE, TEXT, DIM, GREEN, YELLOW,
                      RED, PURPLE, lbl, EmbedChart)
from core.analysis_engine import DOWNSAMPLE_CHART, DOWNSAMPLE_LAP, format_laptime
from core.lap_overlay import extract_lap_trace, compare_laps
from core.corner_analysis import LapDeltaAnalyzer
from core.racing_line import reconstruct_racing_line, speed_colormap
from core import units
from core.gg_diagram import analyze_gg_per_corner
from core.track_zones import classify_zones
from core.reference_lap import compute_reference_delta


class TelemetryTabMixin:
    """Mixin providing all Telemetry tab methods for App."""

    CDEFS = {
        "Speed + Throttle + Brake": (['Speed', 'Throttle', 'Brake'], ['Speed m/s', 'Throttle', 'Brake'], [BLUE, GREEN, RED]),
        "Tire Temps (Front)": (['LFtempCL', 'LFtempCM', 'LFtempCR', 'RFtempCL', 'RFtempCM', 'RFtempCR'],
                               ['LF-In', 'LF-Mid', 'LF-Out', 'RF-In', 'RF-Mid', 'RF-Out'],
                               ['#3498db', '#2980b9', '#1a5276', '#e74c3c', '#c0392b', '#922b21']),
        "Tire Temps (Rear)": (['LRtempCL', 'LRtempCM', 'LRtempCR', 'RRtempCL', 'RRtempCM', 'RRtempCR'],
                              ['LR-In', 'LR-Mid', 'LR-Out', 'RR-In', 'RR-Mid', 'RR-Out'],
                              ['#1abc9c', '#16a085', '#0e6655', '#f39c12', '#d68910', '#9a7d0a']),
        "Suspension Travel": (['LFshockDefl', 'RFshockDefl', 'LRshockDefl', 'RRshockDefl'], ['LF', 'RF', 'LR', 'RR'], [BLUE, RED, GREEN, YELLOW]),
        "Shock Velocity": (['LFshockVel', 'RFshockVel', 'LRshockVel', 'RRshockVel'], ['LF', 'RF', 'LR', 'RR'], [BLUE, RED, GREEN, YELLOW]),
        "Ride Height": (['LFrideHeight', 'RFrideHeight', 'LRrideHeight', 'RRrideHeight'], ['LF', 'RF', 'LR', 'RR'], [BLUE, RED, GREEN, YELLOW]),
        "G-Forces": (['LatAccel', 'LongAccel'], ['Lateral G', 'Long G'], [ACCENT, BLUE]),
        "Chassis Dynamics (Pitch/Roll)": (['Pitch', 'Roll', 'VertAccel'], ['Pitch (rad)', 'Roll (rad)', 'Vert G'], [BLUE, RED, YELLOW]),
        "Chassis Rates (Pitch/Roll Rate)": (['PitchRate', 'RollRate', 'YawRate'], ['Pitch Rate', 'Roll Rate', 'Yaw Rate'], [BLUE, RED, PURPLE]),
        "G-G Diagram (Friction Circle)": None,
        "Tire Pressures": (['LFpress', 'RFpress', 'LRpress', 'RRpress'], ['LF', 'RF', 'LR', 'RR'], [BLUE, RED, GREEN, YELLOW]),
        "Brake Line Pressure": (['LFbrakeLinePress', 'RFbrakeLinePress', 'LRbrakeLinePress', 'RRbrakeLinePress'], ['LF', 'RF', 'LR', 'RR'], [BLUE, RED, GREEN, YELLOW]),
        "RPM + Gear": (['RPM', 'Gear'], ['RPM', 'Gear'], [BLUE, YELLOW]),
        "Engine Temps": (['OilTemp', 'WaterTemp'], ['Oil °C', 'Water °C'], [RED, BLUE]),
        "Lap Delta to Best": (['LapDeltaToBestLap'], ['Delta (s)'], [ACCENT]),
        "Lap Delta to Optimal": (['LapDeltaToOptimalLap'], ['Delta (s)'], [GREEN]),
        "Wheel Slip (Speed diff)": (['LFspeed', 'RFspeed', 'LRspeed', 'RRspeed'], ['LF', 'RF', 'LR', 'RR'], [BLUE, RED, GREEN, YELLOW]),
        "Shift Optimization": (['ShiftIndicatorPct', 'ShiftPowerPct', 'RPM'], ['Shift Ind %', 'Power %', 'RPM'], [YELLOW, GREEN, BLUE]),
        "Raw vs Processed Inputs": (['ThrottleRaw', 'Throttle', 'BrakeRaw', 'Brake'], ['Throttle Raw', 'Throttle', 'Brake Raw', 'Brake'], [GREEN, '#1e8a3a', RED, '#8a1e1e']),
        "Fuel Use Rate": (['FuelUsePerHour', 'FuelLevelPct'], ['L/hr', 'Fuel %'], [BLUE, GREEN]),
        "Lap Overlay — Speed": None,
        "Lap Overlay — Throttle/Brake": None,
        "Multi-Lap Overlay — Speed + Pedals": None,
        "Track Map — Speed": None,
        "Track Map — Braking": None,
        "Track Map — Throttle/Brake Zones": None,
        "Reference Lap Delta": None,
        "Reference Lap — External Delta": None,
        "Track Map — Events Heatmap": None,
        "Racing Line — Speed": None,
        "G-G Per Corner": None,
    }
    _OVERLAY_CHANNELS = {
        "Lap Overlay — Speed": ('Speed', 'Speed (m/s)'),
        "Lap Overlay — Throttle/Brake": (None, ''),
    }

    def _t_telemetry(self):
        tab = self.tv.tab("Telemetry"); tab.configure(fg_color=DARK)
        self._ph_telem = lbl(tab, "Load a session to view telemetry charts.", 14, color=DIM)
        self._ph_telem.pack(pady=40)
        ctrl = ctk.CTkFrame(tab, fg_color=PANEL, height=46, corner_radius=8)
        ctrl.pack(fill='x', padx=10, pady=(8, 4)); ctrl.pack_propagate(False)
        lbl(ctrl, "Chart:", color=DIM).pack(side='left', padx=10)
        _default_chart = getattr(self, 'cfg', {}).get('default_chart', 'Speed + Throttle + Brake')
        self._tv = ctk.StringVar(value=_default_chart)
        ctk.CTkOptionMenu(ctrl, values=list(self.CDEFS.keys()), variable=self._tv,
            fg_color=CARD, button_color=ACCENT, command=self._redraw_telem).pack(side='left', padx=8)
        ctk.CTkButton(ctrl, text="Load Ref…", width=80, height=28, fg_color=CARD,
            hover_color="#1a5a8a", command=self._load_ref_ibt).pack(side='left', padx=(8, 2))
        ctk.CTkButton(ctrl, text="💾 Save Chart", width=95, height=28, fg_color=CARD,
            hover_color="#1a5a8a", command=self._save_chart).pack(side='left', padx=(4, 2))
        self._ref_lbl = lbl(ctrl, "No reference loaded", 9, color=DIM)
        self._ref_lbl.pack(side='left', padx=(2, 10))
        lbl(ctrl, "Laps:", color=DIM).pack(side='left', padx=(16, 4))
        self._lap_checks: list[ctk.CTkCheckBox] = []
        self._lap_frame = ctk.CTkFrame(ctrl, fg_color="transparent")
        self._lap_frame.pack(side='left', padx=4)
        replay = ctk.CTkFrame(tab, fg_color=PANEL, height=36, corner_radius=8)
        replay.pack(fill='x', padx=10, pady=(0, 2)); replay.pack_propagate(False)
        self._rp_btn = ctk.CTkButton(replay, text="▶ Play", width=70, height=26, fg_color=CARD,
            hover_color="#1a5a8a", command=self._toggle_replay)
        self._rp_btn.pack(side='left', padx=8)
        self._rp_spd = ctk.StringVar(value="1×")
        ctk.CTkOptionMenu(replay, values=["0.5×", "1×", "2×", "4×"], variable=self._rp_spd,
            fg_color=CARD, button_color=ACCENT, width=60).pack(side='left', padx=4)
        self._rp_slider = ctk.CTkSlider(replay, from_=0, to=100, number_of_steps=500,
            fg_color=CARD, progress_color=ACCENT, button_color=BLUE,
            command=self._seek_replay)
        self._rp_slider.pack(side='left', fill='x', expand=True, padx=8)
        self._rp_slider.set(0)
        self._rp_lbl = lbl(replay, "", 10, color=DIM)
        self._rp_lbl.pack(side='right', padx=8)
        self._rp_playing = False
        self._rp_pos = 0
        self._rp_line = None
        self._rp_last_tick = 0.0
        # Cursor info bar
        cbar = ctk.CTkFrame(tab, fg_color='#0d1420', height=22, corner_radius=0)
        cbar.pack(fill='x', padx=10); cbar.pack_propagate(False)
        self._cursor_lbl = lbl(cbar,
            "Hover chart to inspect values — click to lock  •  ←/→ to step when locked",
            9, color=DIM)
        self._cursor_lbl.pack(side='left', padx=10)
        # Cursor state
        self._cursor_cids: list = []
        self._cursor_vlines: list = []
        self._cursor_locked = False
        self._cursor_x_arr: np.ndarray | None = None
        self._cursor_ch_arrs: list | None = None
        self._cursor_sample_idx: int = 0
        # Arrow-key stepping (active when Telemetry tab is open and cursor locked)
        self.bind_all('<Left>',  lambda e: self._cursor_step(-1)
                      if self.tv.get() == "Telemetry" and self._cursor_locked else None)
        self.bind_all('<Right>', lambda e: self._cursor_step(1)
                      if self.tv.get() == "Telemetry" and self._cursor_locked else None)
        self.bind_all('<Shift-Left>',  lambda e: self._cursor_step(-10)
                      if self.tv.get() == "Telemetry" and self._cursor_locked else None)
        self.bind_all('<Shift-Right>', lambda e: self._cursor_step(10)
                      if self.tv.get() == "Telemetry" and self._cursor_locked else None)
        self._tc = EmbedChart(tab, figsize=(10, 4)); self._tc.pack(fill='both', expand=True, padx=10, pady=(4, 8))

    def _rebuild_lap_checks(self):
        for w in self._lap_frame.winfo_children(): w.destroy()
        self._lap_checks = []
        if not self.cur_data:
            return
        num = min(self.cur_data.num_laps, 20)
        for i in range(num):
            var = ctk.BooleanVar(value=(i == 0))
            cb = ctk.CTkCheckBox(self._lap_frame, text=str(i + 1), variable=var,
                width=46, height=24, checkbox_width=18, checkbox_height=18,
                font=ctk.CTkFont(size=11), command=self._redraw_telem)
            cb.pack(side='left', padx=1)
            cb._var = var
            self._lap_checks.append(cb)

    def _get_selected_laps(self) -> list[int]:
        return [i for i, cb in enumerate(self._lap_checks) if cb._var.get()]

    def _save_chart(self):
        """Save the current chart to a PNG file."""
        from tkinter import filedialog
        from datetime import datetime
        if not self._tc.fig.axes:
            return
        track = getattr(self.cur_data, 'track_name', '') if self.cur_data else ''
        default = f"chart_{track.replace(' ', '_')}_{datetime.now():%Y%m%d_%H%M}.png"
        path = filedialog.asksaveasfilename(
            title="Save Chart", defaultextension=".png",
            filetypes=[("PNG image", "*.png"), ("All files", "*.*")],
            initialfile=default)
        if not path:
            return
        self._tc.fig.savefig(path, dpi=150, bbox_inches='tight',
                             facecolor=self._tc.fig.get_facecolor())

    def _redraw_telem(self, sel=None):
        sel = sel or self._tv.get()
        if not self.cur_data: return
        self._detach_cursor()
        try: self._ph_telem.pack_forget()
        except Exception: pass
        if sel == "G-G Diagram (Friction Circle)":
            self._draw_gg_diagram(); return
        if sel in self._OVERLAY_CHANNELS:
            self._draw_lap_overlay(sel); return
        if sel.startswith("Track Map"):
            self._draw_track_map(sel); return
        if sel == "Reference Lap Delta":
            self._draw_lap_delta(); return
        if sel == "Reference Lap — External Delta":
            self._draw_ref_lap_external_delta(); return
        if sel == "Track Map — Events Heatmap":
            self._draw_track_map(sel); return
        if sel == "Racing Line — Speed":
            self._draw_racing_line(); return
        if sel == "G-G Per Corner":
            self._draw_gg_per_corner(); return
        if sel == "Multi-Lap Overlay — Speed + Pedals":
            self._draw_multi_lap_overlay(); return
        if sel == "Speed + Throttle + Brake":
            self._draw_stb_chart(); return
        chs, labs, cols = self.CDEFS[sel]
        c = self._tc; c.clear(); ax = c.std_ax(sel)
        d = self.cur_data
        ld = d.get_channel('LapDistPct')

        # Determine which laps to show — selected checkboxes, or best lap
        selected = self._get_selected_laps()
        if selected:
            laps_to_plot = [li for li in selected if li + 1 < len(d.lap_boundaries)]
        elif d.lap_times and len(d.lap_boundaries) > 1:
            laps_to_plot = [int(np.argmin(d.lap_times))]
        else:
            laps_to_plot = [0] if len(d.lap_boundaries) > 1 else []

        multi = len(laps_to_plot) > 1
        for lap_idx in laps_to_plot:
            s, e = d.lap_boundaries[lap_idx], d.lap_boundaries[lap_idx + 1]
            x = ld[s:e] * 100 if ld is not None else np.linspace(0, 100, e - s)
            step = max(1, (e - s) // DOWNSAMPLE_CHART)
            lap_suffix = f" L{lap_idx + 1}" if multi else ""
            for ch, lab, col in zip(chs, labs, cols):
                arr = d.get_channel(ch)
                if arr is None or len(arr) < e: continue
                ax.plot(x[::step], arr[s:e][::step],
                        label=f"{lab}{lap_suffix}", color=col,
                        lw=1.2, alpha=0.6 if multi else 0.9)

        self._pad_yaxis(ax, pct=0.10)
        self._draw_corner_markers([ax], d.track_name)
        ax.legend(loc='upper right', fontsize=8, facecolor='#1e2845', edgecolor='#2a3050', labelcolor=TEXT)
        c.fig.tight_layout(pad=1.0)
        # Attach interactive cursor + mini inset on the best lap
        if ld is not None and d.lap_times and len(d.lap_boundaries) > 1:
            best_li = int(np.argmin(d.lap_times))
            if best_li + 1 < len(d.lap_boundaries):
                s_c, e_c = d.lap_boundaries[best_li], d.lap_boundaries[best_li + 1]
                seg_ld = ld[s_c:e_c] * 100
                ch_arrs = [(lab, arr[s_c:e_c])
                           for ch, lab in zip(chs, labs)
                           for arr in [d.get_channel(ch)]
                           if arr is not None and len(arr) >= e_c]
                inset = self._add_track_inset(d, best_li)
                c.draw()
                self._attach_cursor(ax, seg_ld, ch_arrs, inset=inset)
        else:
            c.draw()

    def _draw_lap_overlay(self, sel: str):
        d = self.cur_data
        if not d or d.num_laps < 1: return
        rpt = self.cur_rpt
        valid_mask = rpt.valid_lap_mask if rpt else [True] * d.num_laps
        # Default: all valid laps; use checkbox selection only when ≥2 are ticked
        selected = self._get_selected_laps()
        valid_laps = [i for i, v in enumerate(valid_mask)
                      if v and i + 1 < len(d.lap_boundaries)]
        laps = (selected if len(selected) >= 2 else valid_laps) or list(range(min(d.num_laps, 10)))
        laps = [li for li in laps if li + 1 < len(d.lap_boundaries)]
        if not laps: return

        # Delta-based color: best lap = green, slowest = red
        best_time = min(d.lap_times[li] for li in laps)
        deltas = [d.lap_times[li] - best_time for li in laps]
        max_delta = max(deltas) if max(deltas) > 0 else 0.5
        norm = Normalize(vmin=0, vmax=max_delta)
        cmap_fn = cm.RdYlGn_r

        c = self._tc; c.clear()
        lap_dist = d.get_channel('LapDistPct')

        if sel == "Lap Overlay — Throttle/Brake":
            ax = c.std_ax("Lap Overlay — Throttle & Brake")
            thr = d.get_channel('Throttle')
            brk = d.get_channel('Brake')
            for li, delta in zip(laps, deltas):
                s, e = d.lap_boundaries[li], d.lap_boundaries[li + 1]
                x = lap_dist[s:e] * 100 if lap_dist is not None else np.linspace(0, 100, e - s)
                col = cmap_fn(norm(delta))
                step = max(1, (e - s) // DOWNSAMPLE_LAP)
                dstr = f"+{delta:.3f}" if delta > 0.001 else "BEST"
                label = f"L{li+1}  {format_laptime(d.lap_times[li])}  ({dstr})"
                if thr is not None:
                    ax.plot(x[::step], thr[s:e][::step], color=col, lw=1.2, alpha=0.85, label=label)
                if brk is not None:
                    ax.plot(x[::step], -brk[s:e][::step], color=col, lw=0.8, alpha=0.5, ls='--')
            ax.set_ylabel("Throttle / −Brake", color=DIM, fontsize=9)
            ax.legend(fontsize=7, facecolor='#1e2845', edgecolor='#2a3050', labelcolor=TEXT,
                      ncol=min(len(laps), 5), loc='upper right')
            self._draw_corner_markers([ax], d.track_name)
            c.fig.tight_layout(pad=1.0)
            if lap_dist is not None and laps:
                best_li = laps[int(np.argmin([d.lap_times[li] for li in laps]))]
                s_c, e_c = d.lap_boundaries[best_li], d.lap_boundaries[best_li + 1]
                seg_ld = lap_dist[s_c:e_c] * 100
                thr_arr = d.get_channel('Throttle')
                brk_arr = d.get_channel('Brake')
                ch_arrs = []
                if thr_arr is not None and len(thr_arr) >= e_c:
                    ch_arrs.append(('Throttle', thr_arr[s_c:e_c]))
                if brk_arr is not None and len(brk_arr) >= e_c:
                    ch_arrs.append(('Brake', brk_arr[s_c:e_c]))
                inset = self._add_track_inset(d, best_li)
                c.draw()
                self._attach_cursor(ax, seg_ld, ch_arrs, inset=inset)
            else:
                c.draw()
        else:
            ch_name, ylabel = self._OVERLAY_CHANNELS[sel]
            ax = c.std_ax(sel)
            arr = d.get_channel(ch_name)
            if arr is None:
                c.draw(); return
            for li, delta in zip(laps, deltas):
                s, e = d.lap_boundaries[li], d.lap_boundaries[li + 1]
                x = lap_dist[s:e] * 100 if lap_dist is not None else np.linspace(0, 100, e - s)
                col = cmap_fn(norm(delta))
                step = max(1, (e - s) // DOWNSAMPLE_LAP)
                dstr = f"+{delta:.3f}" if delta > 0.001 else "BEST"
                label = f"Lap {li+1}  {format_laptime(d.lap_times[li])}  ({dstr})"
                ax.plot(x[::step], arr[s:e][::step], color=col, lw=1.3, alpha=0.85, label=label)
            ax.set_ylabel(ylabel, color=DIM, fontsize=9)
            ax.legend(fontsize=7, facecolor='#1e2845', edgecolor='#2a3050', labelcolor=TEXT,
                      ncol=min(len(laps), 5), loc='upper right')
            self._draw_corner_markers([ax], d.track_name)
            c.fig.tight_layout(pad=1.0)
            # Attach cursor + inset on the best lap
            if lap_dist is not None and laps:
                best_li = laps[int(np.argmin([d.lap_times[li] for li in laps]))]
                s_c, e_c = d.lap_boundaries[best_li], d.lap_boundaries[best_li + 1]
                seg_ld = lap_dist[s_c:e_c] * 100
                inset = self._add_track_inset(d, best_li)
                c.draw()
                self._attach_cursor(ax, seg_ld,
                                    [(f"L{best_li+1}(best)", arr[s_c:e_c])],
                                    inset=inset)
            else:
                c.draw()

    def _draw_lap_delta(self):
        d = self.cur_data
        if not d or d.num_laps < 2: return
        laps = self._get_selected_laps()
        best_lap = int(np.argmin(d.lap_times)) if d.lap_times else 0
        if not laps or laps == [best_lap]:
            laps = [i for i in range(d.num_laps) if i != best_lap][:5]
        c = self._tc; c.clear()
        ax = c.std_ax("Reference Lap Delta (vs Best Lap)", xlabel="Track %")
        ax.set_ylabel("Time Delta (s)", color=DIM, fontsize=9)
        ax.axhline(0, color=GREEN, lw=0.8, alpha=0.6, ls='--')
        palette = ['#e94560', '#00b4d8', '#f39c12', '#9b59b6',
                   '#e74c3c', '#1abc9c', '#3498db', '#d35400', '#8e44ad']
        analyzer = LapDeltaAnalyzer()
        for idx, li in enumerate(laps):
            if li == best_lap: continue
            result = analyzer.analyze(d, best_lap, li)
            if result is None: continue
            col = palette[idx % len(palette)]
            ax.plot(result.dist_pct * 100, result.delta_s, color=col,
                    lw=1.5, alpha=0.85, label=f'Lap {li + 1}')
            ax.fill_between(result.dist_pct * 100, result.delta_s, 0,
                            where=result.delta_s < 0, alpha=0.15, color=GREEN)
            ax.fill_between(result.dist_pct * 100, result.delta_s, 0,
                            where=result.delta_s > 0, alpha=0.15, color=RED)
        ax.legend(fontsize=7, facecolor='#1e2845', edgecolor='#2a3050',
                  labelcolor=TEXT, loc='upper right')
        self._draw_corner_markers([ax], d.track_name)
        c.fig.tight_layout(pad=1.0)
        # Cursor + inset
        all_results = [(li, analyzer.analyze(d, best_lap, li))
                       for li in laps if li != best_lap]
        all_results = [(li, r) for li, r in all_results if r is not None]
        if all_results:
            x_arr = all_results[0][1].dist_pct * 100.0
            ch_arrs = [(f"Lap {li+1} Δ", r.delta_s) for li, r in all_results]
            inset = self._add_track_inset(d, best_lap)
            c.draw()
            self._attach_cursor(ax, x_arr, ch_arrs, inset=inset)
        else:
            c.draw()

    def _draw_gg_diagram(self):
        d = self.cur_data
        lat = d.get_channel('LatAccel'); lon = d.get_channel('LongAccel')
        speed = d.get_channel('Speed')
        if lat is None or lon is None: return
        c = self._tc; c.clear()
        ax = c.fig.add_subplot(111, facecolor='#0d1b2a', aspect='equal')
        ax.set_title("G-G Diagram (Friction Circle)", color=TEXT, fontsize=11, pad=6)
        ax.tick_params(colors=DIM, labelsize=8)
        for sp in ax.spines.values(): sp.set_color('#2a3050')
        ax.grid(True, alpha=0.15, color='#3a4a6a')
        step = max(1, len(lat) // 4000)
        lx = lat[::step]; ly = lon[::step]
        if speed is not None:
            sv = speed[::step] * units.speed_factor()
            sc = ax.scatter(lx, ly, c=sv, cmap='plasma', s=1.5, alpha=0.6, rasterized=True)
            cb = c.fig.colorbar(sc, ax=ax, pad=0.02, shrink=0.8)
            cb.set_label(f'Speed ({units.speed_label()})', color=DIM, fontsize=8)
            cb.ax.tick_params(colors=DIM, labelsize=7)
        else:
            ax.scatter(lx, ly, color=BLUE, s=1.5, alpha=0.5, rasterized=True)
        max_g = float(np.percentile(np.sqrt(lx**2 + ly**2), 99))
        if max_g > 0.1:
            theta = np.linspace(0, 2 * np.pi, 100)
            ax.plot(max_g * np.cos(theta), max_g * np.sin(theta), '--', color=RED, lw=1, alpha=0.6, label=f'Max {max_g:.1f} G')
            ax.legend(fontsize=8, facecolor='#1e2845', edgecolor='#2a3050', labelcolor=TEXT)
        ax.set_xlabel("Lateral G", color=DIM, fontsize=9)
        ax.set_ylabel("Longitudinal G", color=DIM, fontsize=9)
        ax.axhline(0, color='#3a4a6a', lw=0.5); ax.axvline(0, color='#3a4a6a', lw=0.5)
        c.fig.tight_layout(pad=1.0); c.draw()

    def _draw_racing_line(self):
        d = self.cur_data
        if not d or d.num_laps < 1: return
        laps = self._get_selected_laps()
        lap_idx = laps[0] if laps else (int(np.argmin(d.lap_times)) if d.lap_times else 0)
        line = reconstruct_racing_line(d, lap_idx)
        if line is None: return
        c = self._tc; c.clear()
        ax = c.fig.add_subplot(111, facecolor='#0d1b2a', aspect='equal')
        ax.set_title(f"Racing Line — Lap {lap_idx + 1} (Speed)", color=TEXT, fontsize=11, pad=6)
        ax.tick_params(colors=DIM, labelsize=8)
        for sp in ax.spines.values(): sp.set_color('#2a3050')
        colors = speed_colormap(line.speed)
        step = max(1, len(line.x) // 3000)
        sc = ax.scatter(line.x[::step], line.y[::step], c=line.speed[::step] * units.speed_factor(),
                        cmap='RdYlGn', s=2, alpha=0.8, rasterized=True)
        cb = c.fig.colorbar(sc, ax=ax, pad=0.02, shrink=0.8)
        cb.set_label(f'Speed ({units.speed_label()})', color=DIM, fontsize=8)
        cb.ax.tick_params(colors=DIM, labelsize=7)
        ax.set_xlabel("X (m)", color=DIM, fontsize=9)
        ax.set_ylabel("Y (m)", color=DIM, fontsize=9)
        c.fig.tight_layout(pad=1.0); c.draw()

    def _draw_gg_per_corner(self):
        d = self.cur_data
        if not d or d.num_laps < 1: return
        report = analyze_gg_per_corner(d)
        if not report or not report.corners: return
        c = self._tc; c.clear()
        n = min(len(report.corners), 6)
        cols = min(n, 3)
        rows = (n + cols - 1) // cols
        for i in range(n):
            cg = report.corners[i]
            ax = c.fig.add_subplot(rows, cols, i + 1, facecolor='#0d1b2a', aspect='equal')
            ax.set_title(f"Corner {cg.corner_num}", color=TEXT, fontsize=9, pad=3)
            ax.tick_params(colors=DIM, labelsize=6)
            for sp in ax.spines.values(): sp.set_color('#2a3050')
            step = max(1, len(cg.lat_g) // 500)
            ax.scatter(cg.lat_g[::step], cg.long_g[::step], c=cg.speed[::step] * units.speed_factor(),
                       cmap='plasma', s=2, alpha=0.6, rasterized=True)
            max_g = cg.max_combined_g
            if max_g > 0.1:
                theta = np.linspace(0, 2 * np.pi, 60)
                ax.plot(max_g * np.cos(theta), max_g * np.sin(theta), '--', color=RED, lw=0.8, alpha=0.5)
            ax.axhline(0, color='#3a4a6a', lw=0.3); ax.axvline(0, color='#3a4a6a', lw=0.3)
            ax.set_xlabel("Lat G", color=DIM, fontsize=7)
            ax.set_ylabel("Long G", color=DIM, fontsize=7)
        c.fig.tight_layout(pad=0.5); c.draw()

    def _draw_track_map(self, sel: str):
        d = self.cur_data
        if not d: return
        lat = d.get_channel('Lat')
        lon = d.get_channel('Lon')
        speed = d.get_channel('Speed')
        brake = d.get_channel('Brake')
        lap_dist = d.get_channel('LapDistPct')
        if d.lap_times and len(d.lap_boundaries) >= 2:
            best_idx = int(np.argmin(d.lap_times))
            if best_idx + 1 < len(d.lap_boundaries):
                s, e = d.lap_boundaries[best_idx], d.lap_boundaries[best_idx + 1]
            else:
                s, e = 0, min(len(lap_dist), 5000) if lap_dist is not None else 5000
        else:
            s, e = 0, min(len(lap_dist), 5000) if lap_dist is not None else 5000
        if lat is not None and lon is not None and len(lat) > e:
            x = lon[s:e]; y = lat[s:e]
            if np.std(x) < 1e-6 or np.std(y) < 1e-6:
                x = y = None
        else:
            x = y = None
        track_estimated = False
        if x is None:
            track_estimated = True
            spd = speed[s:e] if speed is not None else None
            la = d.get_channel('LatAccel')
            if spd is not None and la is not None and len(la) > e:
                la_seg = la[s:e]
                dt = 1.0 / max(d.tick_rate, 1)
                heading = np.cumsum(np.where(spd > 1.0, la_seg / np.maximum(spd, 1.0), 0.0) * dt)
                x = np.cumsum(spd * np.cos(heading) * dt)
                y = np.cumsum(spd * np.sin(heading) * dt)
            elif lap_dist is not None:
                pct = lap_dist[s:e]
                x = np.cos(pct * 2 * np.pi)
                y = np.sin(pct * 2 * np.pi)
        if x is None or y is None: return
        c = self._tc; c.clear()
        ax = c.fig.add_subplot(111, facecolor='#0d1b2a', aspect='equal')
        ax.set_title(sel, color=TEXT, fontsize=11, pad=6)
        ax.tick_params(colors=DIM, labelsize=7)
        for sp in ax.spines.values(): sp.set_color('#2a3050')
        ax.set_xticks([]); ax.set_yticks([])
        if track_estimated:
            ax.text(0.5, 0.02, "\u26a0 Estimated track shape (no GPS data)",
                    transform=ax.transAxes, ha='center', fontsize=8, color=YELLOW, alpha=0.8)
        step = max(1, len(x) // DOWNSAMPLE_CHART)
        xs, ys = x[::step], y[::step]
        if "Zones" in sel:
            self._draw_track_map_zones(sel, ax, c, xs, ys, s, e, step, track_estimated); return
        if "Events" in sel:
            self._draw_track_map_events(ax, c, xs, ys, x, y, s, e, step, track_estimated); return
        if "Braking" in sel and brake is not None and len(brake) > e:
            cv = brake[s:e][::step]; cmap_name = 'Reds'; clabel = 'Brake Pressure'
        elif speed is not None and len(speed) > e:
            cv = speed[s:e][::step] * units.speed_factor(); cmap_name = 'plasma'; clabel = f'Speed ({units.speed_label()})'
        else:
            ax.plot(xs, ys, color=BLUE, lw=1.5, alpha=0.9)
            c.fig.tight_layout(pad=0.5); c.draw(); return
        sc = ax.scatter(xs, ys, c=cv, cmap=cmap_name, s=2, alpha=0.85, rasterized=True)
        cb = c.fig.colorbar(sc, ax=ax, pad=0.02, shrink=0.8)
        cb.set_label(clabel, color=DIM, fontsize=8)
        cb.ax.tick_params(colors=DIM, labelsize=7)
        c.fig.tight_layout(pad=0.5); c.draw()

    def _draw_track_map_zones(self, sel: str, ax, c, xs, ys, s, e, step, track_estimated):
        d = self.cur_data
        throttle = d.get_channel('Throttle')
        brake = d.get_channel('Brake')
        if throttle is None or brake is None or len(throttle) <= e or len(brake) <= e:
            ax.plot(xs, ys, color=BLUE, lw=1.5, alpha=0.9)
            c.fig.tight_layout(pad=0.5); c.draw(); return
        thr_seg = throttle[s:e][::step]
        brk_seg = brake[s:e][::step]
        n = min(len(xs), len(thr_seg), len(brk_seg))
        thr_seg, brk_seg = thr_seg[:n], brk_seg[:n]
        xs, ys = xs[:n], ys[:n]
        colors, throttle_pct, braking_pct, coast_pct = classify_zones(thr_seg, brk_seg)
        ax.scatter(xs, ys, c=colors, s=3, rasterized=True, zorder=3)
        legend_text = (f"\u25cf Throttle {throttle_pct:.0f}%   "
                       f"\u25cf Braking {braking_pct:.0f}%   "
                       f"\u25cf Coast {coast_pct:.0f}%")
        ax.text(0.5, -0.02, legend_text, transform=ax.transAxes, ha='center',
                fontsize=9, color=TEXT, alpha=0.9)
        handles = [
            Line2D([0], [0], marker='o', color='w', markerfacecolor='#2ecc71',
                   markersize=8, label=f'Throttle {throttle_pct:.0f}%'),
            Line2D([0], [0], marker='o', color='w', markerfacecolor='#e74c3c',
                   markersize=8, label=f'Braking {braking_pct:.0f}%'),
            Line2D([0], [0], marker='o', color='w', markerfacecolor='#f39c12',
                   markersize=8, label=f'Coast {coast_pct:.0f}%'),
        ]
        ax.legend(handles=handles, fontsize=7, facecolor='#1e2845',
                  edgecolor='#2a3050', labelcolor=TEXT, loc='upper right')
        c.fig.tight_layout(pad=0.5); c.draw()

    def _toggle_replay(self):
        if self._rp_playing:
            self._rp_playing = False
            self._rp_btn.configure(text="▶ Play"); return
        if not self.cur_data: return
        self._rp_playing = True
        self._rp_btn.configure(text="⏸ Pause")
        self._rp_last_tick = time.perf_counter()
        self._redraw_telem()
        self._replay_tick()

    def _replay_tick(self):
        if not self._rp_playing or not self.cur_data: return
        if self.tv.get() != "Telemetry":
            self.after(100, self._replay_tick); return
        now = time.perf_counter()
        dt = now - self._rp_last_tick
        self._rp_last_tick = now
        speed_map = {"0.5×": 0.03, "1×": 0.06, "2×": 0.12, "4×": 0.24}
        rate = speed_map.get(self._rp_spd.get(), 0.06)
        step = rate * dt
        self._rp_pos = min(1.0, self._rp_pos + step)
        self._rp_slider.set(self._rp_pos * 100)
        self._draw_replay_marker(self._rp_pos)
        if self._rp_pos >= 1.0:
            self._rp_playing = False
            self._rp_btn.configure(text="▶ Play")
            self._rp_pos = 0; return
        self.after(33, self._replay_tick)

    def _draw_track_map_events(self, ax, c, xs, ys, x_full, y_full, s, e, step, track_estimated):
        """Overlay driver events (oversteer, understeer, late brake…) as colored halos on the track map."""
        # Draw base track in dim grey
        ax.scatter(xs, ys, c='#2a3a4a', s=2, alpha=0.6, rasterized=True, zorder=1)
        style = getattr(self, 'cur_style', None)
        if style is None or not style.events:
            ax.set_title("Track Map — Events Heatmap (no events detected)", color=TEXT, fontsize=11, pad=6)
            c.fig.tight_layout(pad=0.5); c.draw(); return

        # Colour map: event_type → (colour, label)
        TYPE_COLORS = {
            'snap_oversteer':   ('#e74c3c', 'Oversteer'),
            'understeer':       ('#f39c12', 'Understeer'),
            'late_brake':       ('#3498db', 'Late Brake'),
            'early_throttle':   ('#2ecc71', 'Early Throttle'),
        }
        DEFAULT_COLOR = '#9b59b6'

        # Build a LapDistPct → (x, y) lookup from the downsampled track arrays
        d = self.cur_data
        lap_dist_full = d.get_channel('LapDistPct')
        if lap_dist_full is None:
            c.fig.tight_layout(pad=0.5); c.draw(); return

        dist_seg = lap_dist_full[s:e][::step]
        n_track = min(len(xs), len(ys), len(dist_seg))
        dist_seg = dist_seg[:n_track]
        xs_t, ys_t = xs[:n_track], ys[:n_track]

        # Group events by type for a single legend entry each
        from collections import defaultdict
        groups = defaultdict(list)  # type_key -> list of (event_x, event_y, severity)
        for ev in style.events:
            # Find nearest track XY for this lap dist position
            idx = int(np.argmin(np.abs(dist_seg - ev.lap_dist_pct)))
            col_key = ev.event_type if ev.event_type in TYPE_COLORS else '__other__'
            groups[col_key].append((xs_t[idx], ys_t[idx], ev.severity))

        plotted_labels = set()
        legend_handles = []
        for key, pts in groups.items():
            color, label = TYPE_COLORS.get(key, (DEFAULT_COLOR, 'Other'))
            evx = np.array([p[0] for p in pts])
            evy = np.array([p[1] for p in pts])
            sizes = np.array([40 + 80 * p[2] for p in pts])
            sc = ax.scatter(evx, evy, c=color, s=sizes, alpha=0.75,
                            edgecolors='white', linewidths=0.3, zorder=4,
                            rasterized=True)
            if label not in plotted_labels:
                from matplotlib.lines import Line2D
                legend_handles.append(
                    Line2D([0], [0], marker='o', color='w', markerfacecolor=color,
                           markersize=8, label=f'{label} ({len(pts)})'))
                plotted_labels.add(label)

        if legend_handles:
            ax.legend(handles=legend_handles, fontsize=7, facecolor='#1e2845',
                      edgecolor='#2a3050', labelcolor=TEXT, loc='upper right')

        total = sum(len(v) for v in groups.values())
        ax.set_title(f"Track Map — Events Heatmap  ({total} events)", color=TEXT, fontsize=11, pad=6)
        c.fig.tight_layout(pad=0.5); c.draw()

    def _draw_ref_lap_external_delta(self):
        """Compare the current session best lap against an externally loaded reference IBT."""
        d = self.cur_data
        ref = getattr(self, '_ref_data', None)
        if d is None:
            return
        if ref is None:
            c = self._tc; c.clear()
            ax = c.std_ax("Reference Lap — External Delta")
            ax.text(0.5, 0.5, "No reference lap loaded.\nUse 'Load Ref…' to select a reference IBT file.",
                    transform=ax.transAxes, ha='center', va='center', fontsize=12, color=DIM)
            c.fig.tight_layout(pad=1.0); c.draw(); return

        result = compute_reference_delta(d, ref)
        if result is None:
            c = self._tc; c.clear()
            ax = c.std_ax("Reference Lap — External Delta")
            ax.text(0.5, 0.5, "Could not compute delta.\nCheck both sessions have LapDistPct and SessionTime channels.",
                    transform=ax.transAxes, ha='center', va='center', fontsize=11, color=DIM)
            c.fig.tight_layout(pad=1.0); c.draw(); return

        from core.analysis_engine import format_laptime
        c = self._tc; c.clear()
        title = (f"vs Reference: {result.ref_name[:60]}"
                 f"   Δ total: {result.total_delta:+.3f}s"
                 f"  (Ref: {format_laptime(result.ref_best)}  |  Current: {format_laptime(result.cur_best)})")
        ax = c.std_ax(title, xlabel="Track %")
        ax.set_ylabel("Time Delta (s) — positive = slower than ref", color=DIM, fontsize=9)
        ax.axhline(0, color=GREEN, lw=1.0, alpha=0.7, ls='--')

        dist_pct = result.dist_pct * 100
        delta = result.delta_s
        ax.plot(dist_pct, delta, color=ACCENT, lw=1.8, alpha=0.9, label='Current vs Ref')
        ax.fill_between(dist_pct, delta, 0, where=delta < 0, alpha=0.18, color=GREEN,
                        label='Faster than ref')
        ax.fill_between(dist_pct, delta, 0, where=delta > 0, alpha=0.18, color=RED,
                        label='Slower than ref')
        ax.legend(fontsize=7, facecolor='#1e2845', edgecolor='#2a3050',
                  labelcolor=TEXT, loc='upper right')
        self._draw_corner_markers([ax], d.track_name)
        c.fig.tight_layout(pad=1.0)
        # Cursor + inset on external delta
        if d.lap_times and len(d.lap_boundaries) > 1:
            best_li = int(np.argmin(d.lap_times))
            x_arr = result.dist_pct * 100.0
            inset = self._add_track_inset(d, best_li)
            c.draw()
            self._attach_cursor(ax, x_arr,
                                [('Δ time (s)', result.delta_s)],
                                inset=inset)
        else:
            c.draw()

    # ── Multi-Lap Overlay (all valid laps, 3-panel) ───────────────────────────

    def _draw_multi_lap_overlay(self):
        """Show Speed, Throttle and Brake for all valid laps, delta-colored."""
        d = self.cur_data
        if not d or d.num_laps < 1: return
        rpt = self.cur_rpt
        valid_mask = rpt.valid_lap_mask if rpt else [True] * d.num_laps
        valid_laps = [i for i, v in enumerate(valid_mask)
                      if v and i + 1 < len(d.lap_boundaries)]
        if not valid_laps:
            valid_laps = list(range(min(d.num_laps, 10)))

        best_time = min(d.lap_times[li] for li in valid_laps)
        deltas   = [d.lap_times[li] - best_time for li in valid_laps]
        max_delta = max(deltas) if max(deltas) > 0 else 0.5
        norm_fn   = Normalize(vmin=0, vmax=max_delta)
        cmap_fn   = cm.RdYlGn_r

        lap_dist = d.get_channel('LapDistPct')
        channels = []
        for ch_name, ylabel in [('Speed', 'Speed (m/s)'),
                                 ('Throttle', 'Throttle'),
                                 ('Brake', 'Brake')]:
            arr = d.get_channel(ch_name)
            if arr is not None:
                channels.append((ch_name, arr, ylabel))
        if not channels:
            c = self._tc; c.clear(); c.std_ax("No channel data").text(
                0.5, 0.5, "No data", transform=c.fig.axes[0].transAxes,
                ha='center', color=DIM); c.draw(); return

        c = self._tc; c.clear()
        n = len(channels)
        axes = []
        for pi, (ch_name, arr, ylabel) in enumerate(channels):
            share = axes[0] if pi > 0 else None
            kwargs = dict(facecolor='#0d1b2a', sharex=share) if share else dict(facecolor='#0d1b2a')
            ax = c.fig.add_subplot(n, 1, pi + 1, **kwargs)
            axes.append(ax)
            ax.set_ylabel(ylabel, color=DIM, fontsize=8)
            ax.tick_params(colors=DIM, labelsize=7)
            for sp in ax.spines.values(): sp.set_color('#2a3050')
            ax.grid(True, alpha=0.08, color='#3a4a6a')
            if pi < n - 1:
                import matplotlib.pyplot as _plt
                _plt.setp(ax.get_xticklabels(), visible=False)

            for li, delta in zip(valid_laps, deltas):
                s, e = d.lap_boundaries[li], d.lap_boundaries[li + 1]
                x = lap_dist[s:e] * 100 if lap_dist is not None else np.linspace(0, 100, e - s)
                step = max(1, (e - s) // DOWNSAMPLE_LAP)
                col = cmap_fn(norm_fn(delta))
                dstr = f"+{delta:.3f}" if delta > 0.001 else "BEST"
                lbl_text = (f"L{li+1}  {format_laptime(d.lap_times[li])}  ({dstr})"
                            if pi == 0 else None)
                ax.plot(x[::step], arr[s:e][::step], color=col, lw=1.2, alpha=0.85,
                        label=lbl_text)

            if pi == 0:
                ax.set_title("Multi-Lap Overlay — Speed + Throttle + Brake  "
                             "(green = fast, red = slow)", color=TEXT, fontsize=10, pad=4)
                ax.legend(fontsize=6, facecolor='#1e2845', edgecolor='#2a3050',
                          labelcolor=TEXT, ncol=min(len(valid_laps), 8), loc='upper right')

        axes[-1].set_xlabel("Track %", color=DIM, fontsize=8)
        self._draw_corner_markers(axes, d.track_name)
        c.fig.tight_layout(pad=0.5, h_pad=0.2)

        # Cursor on speed panel (top) + mini inset using best lap
        if lap_dist is not None and valid_laps:
            best_li = valid_laps[int(np.argmin([d.lap_times[li] for li in valid_laps]))]
            s_c, e_c = d.lap_boundaries[best_li], d.lap_boundaries[best_li + 1]
            seg_ld = lap_dist[s_c:e_c] * 100
            ch_arrs = [(ch, arr[s_c:e_c]) for ch, arr, _ in channels
                       if len(arr) > e_c]
            inset = self._add_track_inset(d, best_li)
            c.draw()
            self._attach_cursor(axes[0], seg_ld, ch_arrs, inset=inset)
        else:
            c.draw()

    # ── Corner Markers ────────────────────────────────────────────────────────

    def _draw_corner_markers(self, axes: list, track_name: str):
        """Draw corner apex vlines and sector dividers on all axes."""
        from data.track_corners import get_named_corners, get_sectors, sector_name
        top_ax = axes[0]

        # ── Sector dividers (solid, more prominent) ───────────────────────────
        splits = get_sectors(track_name) if track_name else []
        for idx, split in enumerate(splits):
            x = split * 100.0
            for ax in axes:
                ax.axvline(x, color='#6a7a9a', lw=1.0, ls='-', alpha=0.45, zorder=2)
            sname = sector_name(track_name, idx + 1)
            top_ax.text(x + 0.4, 0.97, sname,
                        transform=top_ax.get_xaxis_transform(),
                        fontsize=6, color='#9aaac0', alpha=0.85,
                        va='top', ha='left', clip_on=True)

        # ── Corner apex markers (dashed, subtle) ──────────────────────────────
        corners = get_named_corners(track_name) if track_name else []
        for corner in corners:
            apex = corner['apex_pct'] * 100.0
            pri  = corner.get('priority', 2)
            lw   = 0.7 if pri == 1 else 0.4
            alph = 0.30 if pri == 1 else 0.12
            for ax in axes:
                ax.axvline(apex, color='#4a5a7a', lw=lw, ls='--', alpha=alph, zorder=1)
            if pri == 1 and getattr(self, 'cfg', {}).get('show_corner_labels', True):
                name  = corner['name']
                label = name if len(name) <= 12 else name[:11] + '…'
                top_ax.text(apex, 0.97, label,
                            transform=top_ax.get_xaxis_transform(),
                            fontsize=5.5, color='#8a9aba', alpha=0.8,
                            rotation=90, va='top', ha='center', clip_on=True)

    # ── Y-axis padding helper (#8) ────────────────────────────────────────────

    @staticmethod
    def _pad_yaxis(ax, pct: float = 0.08, min_span: float = 0.0) -> None:
        """Expand y-axis limits by *pct* of the current span, enforcing *min_span*."""
        lo, hi = ax.get_ylim()
        span = max(hi - lo, min_span)
        mid  = (hi + lo) / 2.0
        half = max(span / 2.0, abs(hi - lo) / 2.0)
        pad  = half * pct * 2
        ax.set_ylim(mid - half - pad, mid + half + pad)

    # ── Mini track-map inset helper ───────────────────────────────────────────

    def _add_track_inset(self, d, best_li: int):
        """
        Draw a speed-coloured mini track map in the top-right corner of the
        current figure.  Returns (iax, dot, RacingLine) or None.
        Must be called AFTER tight_layout so the inset is not disturbed.
        """
        rl = reconstruct_racing_line(d, best_li)
        if rl is None:
            return None
        iax = self._tc.fig.add_axes([0.785, 0.62, 0.20, 0.34])
        iax.set_facecolor('#06101a')
        iax.set_aspect('equal', adjustable='datalim')
        iax.tick_params(left=False, bottom=False,
                        labelleft=False, labelbottom=False)
        for sp in iax.spines.values():
            sp.set_color('#2a3050')
        cols = speed_colormap(rl.speed)
        for j in range(len(rl.x) - 1):
            iax.plot(rl.x[j:j+2], rl.y[j:j+2],
                     color=cols[j], lw=1.0, solid_capstyle='round')
        mid = len(rl.x) // 2
        dot, = iax.plot(rl.x[mid], rl.y[mid], 'o',
                        color='#ffffff', ms=4, zorder=10)
        return (iax, dot, rl)

    # ── Linked Speed / Throttle / Brake panels ────────────────────────────────

    def _draw_stb_chart(self):
        """Stacked Speed, Throttle, Brake panels with shared x-axis and corner markers."""
        import matplotlib.pyplot as _plt
        d = self.cur_data
        if not d:
            return
        ld = d.get_channel('LapDistPct')

        selected = self._get_selected_laps()
        if selected:
            laps = [li for li in selected if li + 1 < len(d.lap_boundaries)]
        elif d.lap_times and len(d.lap_boundaries) > 1:
            laps = [int(np.argmin(d.lap_times))]
        else:
            laps = [0] if len(d.lap_boundaries) > 1 else []
        if not laps:
            return

        panel_defs = [
            ('Speed',    BLUE,  f'Speed ({units.speed_label()})', units.speed_factor()),
            ('Throttle', GREEN, 'Throttle',                        1.0),
            ('Brake',    RED,   'Brake',                           1.0),
        ]
        panels = [(ch, col, yl, sc) for ch, col, yl, sc in panel_defs
                  if d.get_channel(ch) is not None]
        if not panels:
            return

        multi      = len(laps) > 1
        best_li    = laps[int(np.argmin([d.lap_times[li] for li in laps]))] if d.lap_times else laps[0]
        best_time  = d.lap_times[best_li] if d.lap_times else 0.0
        show_delta = multi and len(laps) > 1
        n_rows     = len(panels) + (1 if show_delta else 0)

        # per-lap color palette for delta panel (cycles if > 6 laps)
        _LAP_COLS = [YELLOW, PURPLE, '#1abc9c', '#e67e22', '#3498db', '#ff6b9d']

        c = self._tc; c.clear()
        axes = []
        for i, (ch, col, ylabel, scale) in enumerate(panels):
            share = axes[0] if i > 0 else None
            kw = dict(facecolor='#0d1b2a', sharex=share) if share else dict(facecolor='#0d1b2a')
            ax = c.fig.add_subplot(n_rows, 1, i + 1, **kw)
            axes.append(ax)

            arr = d.get_channel(ch)
            for lap_idx in laps:
                s, e = d.lap_boundaries[lap_idx], d.lap_boundaries[lap_idx + 1]
                if len(arr) < e:
                    continue
                x    = ld[s:e] * 100 if ld is not None else np.linspace(0, 100, e - s)
                step = max(1, (e - s) // DOWNSAMPLE_LAP)
                if multi:
                    dt    = d.lap_times[lap_idx] - best_time
                    dstr  = f"+{dt:.3f}" if dt > 0.001 else "BEST"
                    label = f"L{lap_idx + 1}  {format_laptime(d.lap_times[lap_idx])}  ({dstr})"
                else:
                    label = ch
                ax.plot(x[::step], arr[s:e][::step] * scale, color=col,
                        lw=1.3, alpha=0.6 if multi else 0.9, label=label)

            ax.set_ylabel(ylabel, color=DIM, fontsize=8)
            ax.tick_params(colors=DIM, labelsize=7)
            for sp in ax.spines.values():
                sp.set_color('#2a3050')
            ax.grid(True, alpha=0.08, color='#3a4a6a')
            # only show x ticks on the last row (delta panel or brake panel)
            if i < n_rows - 1:
                _plt.setp(ax.get_xticklabels(), visible=False)
            if multi and i == 0:
                ax.legend(fontsize=6, facecolor='#1e2845', edgecolor='#2a3050',
                          labelcolor=TEXT, ncol=min(len(laps), 6), loc='upper right')
            # y-axis padding (#8)
            _min_span = (20.0 * units.speed_factor()) if ch == 'Speed' else 0.5
            self._pad_yaxis(ax, pct=0.08, min_span=_min_span)

        # ── Brake / throttle overlap shading (best lap) ───────────────────────
        s_o, e_o = d.lap_boundaries[best_li], d.lap_boundaries[best_li + 1]
        thr_ch = d.get_channel('Throttle')
        brk_ch = d.get_channel('Brake')
        if thr_ch is not None and brk_ch is not None and len(thr_ch) >= e_o:
            ov_x   = ld[s_o:e_o] * 100 if ld is not None else np.linspace(0, 100, e_o - s_o)
            ov_step = max(1, (e_o - s_o) // DOWNSAMPLE_LAP)
            ov_thr = thr_ch[s_o:e_o][::ov_step]
            ov_brk = brk_ch[s_o:e_o][::ov_step]
            ov_x   = ov_x[::ov_step]
            overlap = (ov_thr > 0.05) & (ov_brk > 0.05)
            for ax in axes:
                ax.fill_between(ov_x, 0, 1, where=overlap,
                                transform=ax.get_xaxis_transform(),
                                color='#f39c12', alpha=0.12, zorder=0,
                                label='Overlap' if ax is axes[-1] else None)
            if overlap.any():
                axes[-1].text(0.01, 0.04, "▪ throttle + brake overlap",
                              transform=axes[-1].transAxes,
                              fontsize=6, color='#f39c12', alpha=0.85)

        # ── Delta time panel (#6) ──────────────────────────────────────────────
        delta_ax = None
        if show_delta:
            delta_ax = c.fig.add_subplot(n_rows, 1, n_rows, sharex=axes[0],
                                         facecolor='#0d1b2a')
            axes.append(delta_ax)
            _la = LapDeltaAnalyzer()
            non_best = [li for li in laps if li != best_li]
            for ci, lap_idx in enumerate(non_best):
                dr = _la.analyze(d, best_li, lap_idx)
                if dr is None:
                    continue
                x_d = dr.dist_pct * 100.0
                y_d = dr.delta_s
                lap_col = _LAP_COLS[ci % len(_LAP_COLS)]
                dt    = d.lap_times[lap_idx] - best_time
                dstr  = f"+{dt:.3f}s" if dt > 0.001 else "±0"
                delta_ax.plot(x_d, y_d, color=lap_col, lw=1.0, alpha=0.85,
                              label=f"L{lap_idx + 1} ({dstr})")
                delta_ax.fill_between(x_d, 0, y_d, where=y_d < 0,
                                      color='#2ecc71', alpha=0.18, zorder=0)
                delta_ax.fill_between(x_d, 0, y_d, where=y_d > 0,
                                      color='#e74c3c', alpha=0.18, zorder=0)
            delta_ax.axhline(0, color='#ffffff', lw=0.7, alpha=0.35)
            delta_ax.set_ylabel('Δ (s)', color=DIM, fontsize=8)
            delta_ax.tick_params(colors=DIM, labelsize=7)
            for sp in delta_ax.spines.values():
                sp.set_color('#2a3050')
            delta_ax.grid(True, alpha=0.08, color='#3a4a6a')
            if non_best:
                delta_ax.legend(fontsize=6, facecolor='#1e2845', edgecolor='#2a3050',
                                labelcolor=TEXT, loc='upper right',
                                ncol=min(len(non_best), 4))
            self._pad_yaxis(delta_ax, pct=0.15, min_span=0.1)

        title = "Speed · Throttle · Brake"
        if multi:
            title += f"  ({len(laps)} laps)"
        axes[0].set_title(title, color=TEXT, fontsize=11, pad=6)
        axes[-1].set_xlabel("Track %", color=DIM, fontsize=9)

        self._draw_corner_markers(axes, d.track_name)
        c.fig.tight_layout(pad=0.4, h_pad=0.15)

        # ── Mini track map inset (#3) ──────────────────────────────────────────
        inset = self._add_track_inset(d, best_li)

        c.draw()

        # ── Multi-panel cursor on best lap ────────────────────────────────────
        if ld is not None and laps:
            s_c, e_c = d.lap_boundaries[best_li], d.lap_boundaries[best_li + 1]
            seg_ld   = ld[s_c:e_c] * 100
            ch_arrs  = [(ch, d.get_channel(ch)[s_c:e_c] * scale)
                        for ch, _, _, scale in panels
                        if len(d.get_channel(ch)) >= e_c]
            self._attach_cursor(axes, seg_ld, ch_arrs, inset=inset)

    # ── Interactive Cursor ────────────────────────────────────────────────────

    def _attach_cursor(self, axes, x_arr: np.ndarray, ch_arrs: list,
                       inset=None):
        """
        Attach a hover crosshair to one or more axes, with zoom/pan support.

        axes   : single Axes or list — a vline is drawn on each.
        x_arr  : 1-D array of x positions (track %, 0–100).
        ch_arrs: list of (label, array) sliced to the reference lap.
        inset  : optional (iax, dot, RacingLine) tuple for mini-map sync (#3).
        """
        if not isinstance(axes, list):
            axes = [axes]
        self._detach_cursor()
        self._cursor_x_arr      = x_arr
        self._cursor_ch_arrs    = ch_arrs
        self._cursor_sample_idx = 0

        vlines = [ax.axvline(x=-999, color='#ffffff', lw=0.9, alpha=0.6, ls=':', zorder=10)
                  for ax in axes]
        self._cursor_vlines = vlines

        # drag-pan state (shared via closure)
        _drag: dict = {'active': False, 'start_x': None,
                       'start_xlim': None, 'moved': False}

        def _update_inset(idx: int) -> None:
            if inset is None:
                return
            iax, dot, rl = inset
            dp_val = float(x_arr[idx]) / 100.0   # 0–1
            # find nearest point on racing line by dist_pct
            i_rl = int(np.argmin(np.abs(rl.dist_pct - dp_val)))
            dot.set_xdata([rl.x[i_rl]])
            dot.set_ydata([rl.y[i_rl]])

        def _label(idx: int) -> str:
            x_pct = float(x_arr[idx]) if len(x_arr) > 0 else 0.0
            parts = [f"📍 {x_pct:.1f}%"]
            for lab, arr in ch_arrs:
                if arr is not None and idx < len(arr):
                    parts.append(f"{lab}: {arr[idx]:.3f}")
            if self._cursor_locked:
                parts.append("🔒 locked  (←/→  •  click to unlock)")
            return "  |  ".join(parts)

        def _move_cursor_to(x_data: float) -> None:
            x = float(np.clip(x_data, float(x_arr[0]), float(x_arr[-1])))
            idx = int(np.argmin(np.abs(x_arr - x)))
            self._cursor_sample_idx = idx
            for vl in vlines:
                vl.set_xdata([x, x])
            _update_inset(idx)
            self._cursor_lbl.configure(text=_label(idx))
            self._tc.canvas.draw_idle()

        # ── zoom (scroll-wheel) ───────────────────────────────────────────────
        def on_scroll(event):
            if event.inaxes not in axes or event.xdata is None:
                return
            x_c  = event.xdata
            x0, x1 = axes[0].get_xlim()
            factor  = 0.80 if event.button == 'up' else 1.25
            new_w   = (x1 - x0) * factor
            frac    = (x_c - x0) / (x1 - x0)
            axes[0].set_xlim(x_c - frac * new_w, x_c - frac * new_w + new_w)
            self._tc.canvas.draw_idle()

        # ── pan (left-drag) ───────────────────────────────────────────────────
        def on_press(event):
            if event.button != 1 or event.inaxes not in axes:
                return
            if getattr(event, 'dblclick', False):
                # double-click: reset zoom
                axes[0].set_xlim(0, 100)
                self._cursor_locked = False
                self._tc.canvas.draw_idle()
                return
            _drag['active']    = True
            _drag['start_x']   = event.xdata
            _drag['start_xlim']= axes[0].get_xlim()
            _drag['moved']     = False

        def on_motion(event):
            if _drag['active'] and event.xdata is not None and event.inaxes in axes:
                dx = event.xdata - _drag['start_x']
                x0, x1 = _drag['start_xlim']
                axes[0].set_xlim(x0 - dx, x1 - dx)
                _drag['moved'] = True
                self._tc.canvas.draw_idle()
            elif (not _drag['active'] and not self._cursor_locked
                  and event.xdata is not None and event.inaxes in axes):
                _move_cursor_to(event.xdata)

        def on_release(event):
            if event.button != 1:
                return
            was_drag = _drag['moved']
            _drag['active'] = False
            _drag['moved']  = False
            if not was_drag and event.xdata is not None and event.inaxes in axes:
                # simple click → toggle lock
                self._cursor_locked = not self._cursor_locked
                _move_cursor_to(event.xdata)

        canvas = self._tc.canvas
        self._cursor_cids = [
            canvas.mpl_connect('scroll_event',         on_scroll),
            canvas.mpl_connect('button_press_event',   on_press),
            canvas.mpl_connect('motion_notify_event',  on_motion),
            canvas.mpl_connect('button_release_event', on_release),
        ]

    def _detach_cursor(self):
        """Disconnect cursor event handlers and reset state."""
        for cid in getattr(self, '_cursor_cids', []):
            try:
                self._tc.canvas.mpl_disconnect(cid)
            except Exception:
                pass
        self._cursor_cids       = []
        self._cursor_vlines     = []
        self._cursor_locked     = False
        self._cursor_x_arr      = None
        self._cursor_ch_arrs    = None
        self._cursor_sample_idx = 0
        try:
            self._cursor_lbl.configure(
                text="Hover chart to inspect values — click to lock  •  ←/→ to step when locked")
        except Exception:
            pass

    def _cursor_step(self, direction: int):
        """Move the locked cursor by `direction` samples (±1 or ±10)."""
        x_arr = self._cursor_x_arr
        if x_arr is None or not self._cursor_locked:
            return
        n = len(x_arr)
        new_idx = int(np.clip(self._cursor_sample_idx + direction, 0, n - 1))
        self._cursor_sample_idx = new_idx
        x = float(x_arr[new_idx])
        for vl in self._cursor_vlines:
            vl.set_xdata([x, x])
        parts = [f"📍 {x:.1f}% 🔒 locked  (←/→ to step,  click to unlock)"]
        if self._cursor_ch_arrs:
            for lab, arr in self._cursor_ch_arrs:
                if arr is not None and new_idx < len(arr):
                    parts.append(f"{lab}: {arr[new_idx]:.3f}")
        self._cursor_lbl.configure(text="  |  ".join(parts))
        self._tc.canvas.draw_idle()

    def _seek_replay(self, val):
        self._rp_pos = float(val) / 100.0
        if not self._rp_playing:
            self._draw_replay_marker(self._rp_pos)

    def _draw_replay_marker(self, pct):
        d = self.cur_data
        if not d: return
        c = self._tc
        if not c.fig.axes: return
        ax = c.fig.axes[0]
        if self._rp_line and self._rp_line in ax.lines:
            self._rp_line.remove()
            self._rp_line = None
        xpos = pct * 100.0
        ylim = ax.get_ylim()
        self._rp_line, = ax.plot([xpos, xpos], ylim, color=YELLOW, lw=1.5, alpha=0.8, ls='--')
        speed = d.get_channel('Speed')
        throttle = d.get_channel('Throttle')
        brake = d.get_channel('Brake')
        lap_dist = d.get_channel('LapDistPct')
        info_parts = [f"Pos: {pct * 100:.1f}%"]
        if lap_dist is not None:
            s = e = None
            if d.lap_times and len(d.lap_boundaries) > 1:
                best_li = int(np.argmin(d.lap_times))
                if best_li < len(d.lap_boundaries) - 1:
                    s = d.lap_boundaries[best_li]
                    e = d.lap_boundaries[best_li + 1]
            if s is not None and e is not None:
                seg = lap_dist[s:e]
                idx = s + int(np.argmin(np.abs(seg - pct)))
            else:
                idx = int(np.argmin(np.abs(lap_dist - pct)))
            if speed is not None and idx < len(speed):
                info_parts.append(units.fmt_speed(speed[idx]))
            if throttle is not None and idx < len(throttle):
                info_parts.append(f"Thr: {throttle[idx] * 100:.0f}%")
            if brake is not None and idx < len(brake):
                info_parts.append(f"Brk: {brake[idx] * 100:.0f}%")
        self._rp_lbl.configure(text="  |  ".join(info_parts))
        c.canvas.draw_idle()
