"""Telemetry tab mixin — charts, overlays, track maps, replay."""

import time
import numpy as np
import customtkinter as ctk
from matplotlib.lines import Line2D

from ui.theme import (DARK, PANEL, CARD, ACCENT, BLUE, TEXT, DIM, GREEN, YELLOW,
                      RED, PURPLE, lbl, EmbedChart)
from core.analysis_engine import DOWNSAMPLE_CHART, DOWNSAMPLE_LAP
from core.lap_overlay import extract_lap_trace, compare_laps
from core.corner_analysis import LapDeltaAnalyzer
from core.racing_line import reconstruct_racing_line, speed_colormap
from core.gg_diagram import analyze_gg_per_corner
from core.track_zones import classify_zones


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
        "G-Forces": (['LatAccel', 'LongAccel'], ['Lateral G', 'Long G'], [ACCENT, BLUE]),
        "G-G Diagram (Friction Circle)": None,
        "Tire Pressures": (['LFpress', 'RFpress', 'LRpress', 'RRpress'], ['LF', 'RF', 'LR', 'RR'], [BLUE, RED, GREEN, YELLOW]),
        "RPM + Gear": (['RPM', 'Gear'], ['RPM', 'Gear'], [BLUE, YELLOW]),
        "Lap Overlay — Speed": None,
        "Lap Overlay — Throttle/Brake": None,
        "Track Map — Speed": None,
        "Track Map — Braking": None,
        "Track Map — Throttle/Brake Zones": None,
        "Reference Lap Delta": None,
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
        self._tv = ctk.StringVar(value="Speed + Throttle + Brake")
        ctk.CTkOptionMenu(ctrl, values=list(self.CDEFS.keys()), variable=self._tv,
            fg_color=CARD, button_color=ACCENT, command=self._redraw_telem).pack(side='left', padx=8)
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
                width=40, height=22, checkbox_width=16, checkbox_height=16,
                font=ctk.CTkFont(size=9), command=self._redraw_telem)
            cb.pack(side='left', padx=1)
            cb._var = var
            self._lap_checks.append(cb)

    def _get_selected_laps(self) -> list[int]:
        return [i for i, cb in enumerate(self._lap_checks) if cb._var.get()]

    def _redraw_telem(self, sel=None):
        sel = sel or self._tv.get()
        if not self.cur_data: return
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
        if sel == "Racing Line — Speed":
            self._draw_racing_line(); return
        if sel == "G-G Per Corner":
            self._draw_gg_per_corner(); return
        chs, labs, cols = self.CDEFS[sel]
        c = self._tc; c.clear(); ax = c.std_ax(sel)
        ld = self.cur_data.get_channel('LapDistPct')
        x = ld * 100 if ld is not None else None
        for ch, lab, col in zip(chs, labs, cols):
            arr = self.cur_data.get_channel(ch)
            if arr is None: continue
            step = max(1, len(arr) // DOWNSAMPLE_CHART)
            xd = x[::step] if x is not None else np.arange(len(arr[::step]))
            ax.plot(xd, arr[::step], label=lab, color=col, lw=1.2, alpha=0.9)
        ax.legend(loc='upper right', fontsize=8, facecolor='#1e2845', edgecolor='#2a3050', labelcolor=TEXT)
        c.fig.tight_layout(pad=1.0); c.draw()

    def _draw_lap_overlay(self, sel: str):
        d = self.cur_data
        if not d or d.num_laps < 1: return
        laps = self._get_selected_laps()
        if not laps:
            laps = list(range(min(d.num_laps, 5)))
        c = self._tc; c.clear()
        palette = ['#e94560', '#00b4d8', '#2ecc71', '#f39c12', '#9b59b6',
                   '#e74c3c', '#1abc9c', '#3498db', '#d35400', '#8e44ad',
                   '#27ae60', '#c0392b', '#16a085', '#2980b9', '#f1c40f',
                   '#e67e22', '#2c3e50', '#7f8c8d', '#1a5276', '#922b21']
        lap_dist = d.get_channel('LapDistPct')
        if sel == "Lap Overlay — Throttle/Brake":
            ax = c.std_ax("Lap Overlay — Throttle & Brake")
            for idx, li in enumerate(laps):
                if li >= d.num_laps: continue
                s, e = d.lap_boundaries[li], d.lap_boundaries[li + 1]
                x = lap_dist[s:e] * 100 if lap_dist is not None else np.linspace(0, 100, e - s)
                col = palette[idx % len(palette)]
                thr = d.get_channel('Throttle')
                brk = d.get_channel('Brake')
                step = max(1, (e - s) // DOWNSAMPLE_LAP)
                if thr is not None:
                    ax.plot(x[::step], thr[s:e][::step], color=col, lw=1.2, alpha=0.8, label=f'L{li + 1} Thr')
                if brk is not None:
                    ax.plot(x[::step], -brk[s:e][::step], color=col, lw=0.8, alpha=0.5, ls='--')
            ax.set_ylabel("Throttle / -Brake", color=DIM, fontsize=9)
            ax.legend(fontsize=7, facecolor='#1e2845', edgecolor='#2a3050', labelcolor=TEXT, ncol=2, loc='upper right')
        else:
            ch_name, ylabel = self._OVERLAY_CHANNELS[sel]
            ax = c.std_ax(sel)
            arr = d.get_channel(ch_name)
            if arr is None:
                c.draw(); return
            for idx, li in enumerate(laps):
                if li >= d.num_laps: continue
                s, e = d.lap_boundaries[li], d.lap_boundaries[li + 1]
                x = lap_dist[s:e] * 100 if lap_dist is not None else np.linspace(0, 100, e - s)
                col = palette[idx % len(palette)]
                step = max(1, (e - s) // DOWNSAMPLE_LAP)
                ax.plot(x[::step], arr[s:e][::step], color=col, lw=1.2, alpha=0.85, label=f'Lap {li + 1}')
            ax.set_ylabel(ylabel, color=DIM, fontsize=9)
            ax.legend(fontsize=7, facecolor='#1e2845', edgecolor='#2a3050', labelcolor=TEXT, ncol=2, loc='upper right')
        c.fig.tight_layout(pad=1.0); c.draw()

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
        c.fig.tight_layout(pad=1.0); c.draw()

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
            sv = speed[::step] * 3.6
            sc = ax.scatter(lx, ly, c=sv, cmap='plasma', s=1.5, alpha=0.6, rasterized=True)
            cb = c.fig.colorbar(sc, ax=ax, pad=0.02, shrink=0.8)
            cb.set_label('Speed (km/h)', color=DIM, fontsize=8)
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
        sc = ax.scatter(line.x[::step], line.y[::step], c=line.speed[::step] * 3.6,
                        cmap='RdYlGn', s=2, alpha=0.8, rasterized=True)
        cb = c.fig.colorbar(sc, ax=ax, pad=0.02, shrink=0.8)
        cb.set_label('Speed (km/h)', color=DIM, fontsize=8)
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
            ax.scatter(cg.lat_g[::step], cg.long_g[::step], c=cg.speed[::step] * 3.6,
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
        if "Braking" in sel and brake is not None and len(brake) > e:
            cv = brake[s:e][::step]; cmap_name = 'Reds'; clabel = 'Brake Pressure'
        elif speed is not None and len(speed) > e:
            cv = speed[s:e][::step] * 3.6; cmap_name = 'plasma'; clabel = 'Speed (km/h)'
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
                info_parts.append(f"Spd: {speed[idx] * 3.6:.0f}km/h")
            if throttle is not None and idx < len(throttle):
                info_parts.append(f"Thr: {throttle[idx] * 100:.0f}%")
            if brake is not None and idx < len(brake):
                info_parts.append(f"Brk: {brake[idx] * 100:.0f}%")
        self._rp_lbl.configure(text="  |  ".join(info_parts))
        c.canvas.draw_idle()
