"""Stint & Tires + Lap Times tab mixin."""

import numpy as np
import customtkinter as ctk
from tkinter import messagebox

from ui.theme import (DARK, PANEL, CARD, ACCENT, BLUE, TEXT, DIM, GREEN, YELLOW,
                      RED, PURPLE, lbl, card_frame, stat_blk, sec_lbl, EmbedChart)
from core.analysis_engine import format_laptime
from core.advanced_analysis import FuelStrategyAnalyzer
from core.tire_wear_prediction import predict_tire_wear


class StintTabMixin:
    """Mixin providing Stint & Tires and Lap Times tab methods for App."""

    def _t_stint(self):
        tab = self.tv.tab("Stint & Tires"); tab.configure(fg_color=DARK)
        self._ph_stint = lbl(tab, "Load a session to see stint & tire analysis.", 14, color=DIM)
        self._ph_stint.pack(pady=40)
        self._stsc = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        self._stsc.pack(fill='both', expand=True, padx=10, pady=8)
        self._stpc  = EmbedChart(self._stsc, figsize=(10, 2.8)); self._stpc.pack(fill='x', pady=(0, 4))
        self._stdc  = EmbedChart(self._stsc, figsize=(10, 2.8)); self._stdc.pack(fill='x', pady=(0, 4))
        self._stwc  = EmbedChart(self._stsc, figsize=(10, 3.0)); self._stwc.pack(fill='x', pady=(0, 4))
        self._stwear = EmbedChart(self._stsc, figsize=(10, 2.5)); self._stwear.pack(fill='x', pady=(0, 4))
        self._stshock = EmbedChart(self._stsc, figsize=(10, 2.5)); self._stshock.pack(fill='x', pady=(0, 4))
        self._strh    = EmbedChart(self._stsc, figsize=(10, 2.5)); self._strh.pack(fill='x', pady=(0, 4))
        self._steng   = EmbedChart(self._stsc, figsize=(10, 2.5)); self._steng.pack(fill='x', pady=(0, 4))
        self._stdf  = ctk.CTkFrame(self._stsc, fg_color="transparent"); self._stdf.pack(fill='x')

    def _u_stint(self):
        r = self.cur_stint
        if not r: return
        try: self._ph_stint.pack_forget()
        except Exception: pass
        # Pressure chart
        c = self._stpc; c.clear(); ax = c.std_ax("Tire Pressures — Recommended Cold vs Actual Hot (PSI)", xlabel="Corner")
        corners = ['LF', 'RF', 'LR', 'RR']
        cold = [r.pressure_cold_targets.get(co, 0) for co in corners]
        hot = [r.pressure_hot_actuals.get(co, 0) for co in corners]
        x = np.arange(4)
        ax.bar(x - 0.2, cold, 0.35, label='Rec. Cold', color=BLUE, alpha=0.85)
        ax.bar(x + 0.2, hot, 0.35, label='Actual Hot', color=RED, alpha=0.85)
        ax.set_xticks(x); ax.set_xticklabels(corners, color=DIM)
        ax.set_ylabel("PSI", color=DIM, fontsize=8)
        ax.legend(fontsize=8, facecolor='#1e2845', edgecolor='#2a3050', labelcolor=TEXT)
        c.fig.tight_layout(pad=0.8); c.draw()
        # Temp progression
        c2 = self._stdc; c2.clear(); ax2 = c2.std_ax("Tire Temp Progression by Lap", xlabel="Lap")
        lps = None
        for corner, col in [('LF', BLUE), ('RF', RED), ('LR', GREEN), ('RR', YELLOW)]:
            vals = r.tire_temp_progression.get(corner, [])
            if vals:
                lps = lps or list(range(1, len(vals) + 1))
                ax2.plot(lps, vals, marker='o', color=col, label=corner, lw=1.5)
        if r.lap_times and len(r.lap_times) >= 3:
            ax2b = ax2.twinx()
            ax2b.plot(range(1, len(r.lap_times) + 1), r.lap_times, '--', color='white', alpha=0.4, lw=1, label='Lap time')
            ax2b.set_ylabel("Lap time (s)", color=DIM, fontsize=8); ax2b.tick_params(colors=DIM)
        ax2.legend(fontsize=8, facecolor='#1e2845', edgecolor='#2a3050', labelcolor=TEXT, loc='upper left')
        c2.fig.tight_layout(pad=0.8); c2.draw()
        # Detail
        for w in self._stdf.winfo_children(): w.destroy()
        sec_lbl(self._stdf, "🌡 Cold Pressure Recommendations (to hit hot target)")
        pt = ctk.CTkFrame(self._stdf, fg_color=PANEL, corner_radius=8); pt.pack(fill='x', pady=4)
        cr = ctk.CTkFrame(pt, fg_color="transparent"); cr.pack(fill='x', padx=12, pady=10)
        for corner in ['LF', 'RF', 'LR', 'RR']:
            cf = card_frame(cr); cf.pack(side='left', fill='both', expand=True, padx=4)
            lbl(cf, corner, 14, bold=True, color=BLUE).pack(pady=(8, 2))
            lbl(cf, f"Cold: {r.pressure_cold_targets.get(corner, 0):.1f} PSI", 12, bold=True, color=GREEN).pack()
            lbl(cf, f"Hot:  {r.pressure_hot_actuals.get(corner, 0):.1f} PSI", 11).pack(pady=(0, 8))
        # YAML tire data: last hot pressures + tread remaining from CarSetup
        d = self.cur_data
        if d:
            car_setup = d.session_info.get('car_setup', {})
            tires_yaml = car_setup.get('Tires', {}) if isinstance(car_setup, dict) else {}
            yaml_tire_map = {
                'LeftFront': 'LF', 'RightFront': 'RF',
                'LeftRear':  'LR', 'RightRear':  'RR',
            }
            yaml_data = {}
            for yaml_key, corner in yaml_tire_map.items():
                tire = tires_yaml.get(yaml_key, {})
                if isinstance(tire, dict) and tire:
                    yaml_data[corner] = tire
            if yaml_data:
                sec_lbl(self._stdf, "📋 End-of-Session Tire Data (from IBT YAML)")
                yt = ctk.CTkFrame(self._stdf, fg_color=PANEL, corner_radius=8); yt.pack(fill='x', pady=4)
                yr = ctk.CTkFrame(yt, fg_color="transparent"); yr.pack(fill='x', padx=12, pady=10)
                for corner in ['LF', 'RF', 'LR', 'RR']:
                    tire = yaml_data.get(corner, {})
                    if not tire: continue
                    cf = card_frame(yr); cf.pack(side='left', fill='both', expand=True, padx=4)
                    lbl(cf, corner, 14, bold=True, color=BLUE).pack(pady=(8, 2))
                    if 'LastHotPressure' in tire:
                        lbl(cf, f"Hot: {tire['LastHotPressure']}", 11, color=RED).pack()
                    if 'StartingPressure' in tire:
                        lbl(cf, f"Cold: {tire['StartingPressure']}", 11, color=GREEN).pack()
                    if 'TreadRemaining' in tire:
                        lbl(cf, f"Wear: {tire['TreadRemaining']}", 11, color=YELLOW).pack()
                    if 'LastTempsOM' in tire:
                        lbl(cf, f"Temps: {tire['LastTempsOM']}", 10, color=DIM).pack(pady=(0, 8))
        if r.findings:
            sec_lbl(self._stdf, "📋 Pressure Findings")
            for fn in r.findings:
                ff = ctk.CTkFrame(self._stdf, fg_color="#1e2845", corner_radius=6); ff.pack(fill='x', pady=2)
                lbl(ff, f"•  {fn}", 11, color=TEXT, wraplength=820, justify='left', anchor='w').pack(padx=12, pady=6)
        if r.deg_rate > 0:
            sec_lbl(self._stdf, "📉 Degradation")
            dg = ctk.CTkFrame(self._stdf, fg_color=PANEL, corner_radius=8); dg.pack(fill='x', pady=4)
            dr = ctk.CTkFrame(dg, fg_color="transparent"); dr.pack(fill='x', padx=12, pady=10)
            stat_blk(dr, "Deg Rate", f"+{r.deg_rate:.3f}s/lap", YELLOW)
            stat_blk(dr, "Optimal Stint", f"{r.optimal_stint_length} laps", GREEN)
            stat_blk(dr, "Cliff Lap", str(r.cliff_lap), RED)
        self._draw_tire_wear_projection(r)
        self._draw_tire_surface_wear()
        self._draw_suspension()
        self._draw_engine_health()
        self._draw_stint_comparison(self._stdf)

    def _draw_tire_wear_projection(self, stint_report):
        pred = predict_tire_wear(stint_report)
        c = self._stwc; c.clear()
        if not pred.actual_times or pred.fit_type == "none":
            ax = c.std_ax("Tire Wear Projection", xlabel="Lap")
            ax.text(0.5, 0.5, "Not enough data for projection",
                    transform=ax.transAxes, ha='center', va='center', color=DIM, fontsize=11)
            c.fig.tight_layout(pad=0.8); c.draw(); return
        ax = c.std_ax("🔮 Tire Wear Projection", xlabel="Lap")
        ax.plot(pred.actual_laps, pred.actual_times, 'o-', color=BLUE,
                lw=1.8, markersize=4, label='Actual', zorder=5)
        if pred.projected_laps:
            ax.plot(pred.projected_laps, pred.projected_times, 's--', color=YELLOW,
                    lw=1.5, markersize=3, label='Projected', alpha=0.9, zorder=4)
            ax.fill_between(pred.projected_laps, pred.confidence_lower,
                            pred.confidence_upper, color=YELLOW, alpha=0.12, label='Confidence band')
        if pred.pit_window_open > 0 and pred.pit_window_close > pred.pit_window_open:
            ax.axvspan(pred.pit_window_open, pred.pit_window_close, color=GREEN, alpha=0.12, label='Pit window')
            ax.axvline(pred.pit_window_open, color=GREEN, ls=':', lw=1, alpha=0.6)
            ax.axvline(pred.pit_window_close, color=GREEN, ls=':', lw=1, alpha=0.6)
        if pred.grip_cliff_lap > 0:
            ax.axvline(pred.grip_cliff_lap, color=RED, ls='--', lw=1.2,
                       alpha=0.7, label=f'Cliff (lap {pred.grip_cliff_lap})')
        ax.set_ylabel("Lap time (s)", color=DIM, fontsize=8)
        ax.legend(fontsize=7, facecolor='#1e2845', edgecolor='#2a3050', labelcolor=TEXT, loc='upper left')
        c.fig.tight_layout(pad=0.8); c.draw()
        # Wear stats
        sec_lbl(self._stdf, "🔮 Tire Wear Prediction")
        wp = ctk.CTkFrame(self._stdf, fg_color=PANEL, corner_radius=8); wp.pack(fill='x', pady=4)
        wr = ctk.CTkFrame(wp, fg_color="transparent"); wr.pack(fill='x', padx=12, pady=10)
        life_col = GREEN if pred.tire_life_pct > 60 else YELLOW if pred.tire_life_pct > 30 else RED
        stat_blk(wr, "Tire Life", f"{pred.tire_life_pct:.0f}%", life_col)
        stat_blk(wr, "Pit Window", f"Laps {pred.pit_window_open}–{pred.pit_window_close}", GREEN)
        stat_blk(wr, "Grip Cliff", f"Lap {pred.grip_cliff_lap}", RED)
        if pred.peak_wear_corner:
            stat_blk(wr, "Hottest Corner", pred.peak_wear_corner, YELLOW)
        stat_blk(wr, "Model", f"{pred.fit_type} (R²={pred.r_squared:.2f})", DIM)
        if pred.findings:
            for fn in pred.findings:
                ff = ctk.CTkFrame(self._stdf, fg_color="#1e2845", corner_radius=6); ff.pack(fill='x', pady=2)
                lbl(ff, f"•  {fn}", 11, color=TEXT, wraplength=820,
                    justify='left', anchor='w').pack(padx=12, pady=6)

    def _draw_tire_surface_wear(self):
        """Bar chart: inner/mid/outer tread wear per tire from LFwearL/M/R channels."""
        d = self.cur_data
        c = self._stwear; c.clear()
        if d is None:
            return
        corners = ['LF', 'RF', 'LR', 'RR']
        zones   = ['L', 'M', 'R']
        zone_labels = ['Inner', 'Mid', 'Outer']
        corner_colors = [BLUE, RED, GREEN, YELLOW]

        # Collect last-lap average wear per corner per zone
        # iRacing wear channels: 0 = new tyre, 1 = fully worn (fraction of wear used)
        data_found = False
        wear_data = {}
        for corner in corners:
            wear_data[corner] = {}
            for zone in zones:
                ch = d.get_channel(f'{corner}wear{zone}')
                if ch is not None and len(ch) > 0:
                    # Use end-of-session average (last 10% of data) for wear state
                    tail = ch[int(len(ch) * 0.9):]
                    wear_data[corner][zone] = float(np.mean(tail)) * 100  # → percent worn
                    data_found = True
                else:
                    wear_data[corner][zone] = None

        if not data_found:
            ax = c.std_ax("Tire Surface Wear (Inner / Mid / Outer)", xlabel="Zone")
            ax.text(0.5, 0.5, "No tire wear channels in this IBT\n(LFwearL/M/R etc.)",
                    transform=ax.transAxes, ha='center', va='center', color=DIM, fontsize=11)
            c.fig.tight_layout(pad=0.8); c.draw(); return

        ax = c.std_ax("Tire Surface Wear — Inner / Mid / Outer per Corner", xlabel="Tire")
        n_corners = len(corners)
        x = np.arange(n_corners)
        width = 0.22
        offsets = [-1, 0, 1]
        for zi, (zone, zlbl, offset) in enumerate(zip(zones, zone_labels, offsets)):
            vals = [wear_data[corner].get(zone) or 0 for corner in corners]
            cols = [corner_colors[ci] for ci in range(n_corners)]
            bars = ax.bar(x + offset * width, vals, width,
                          label=zlbl, alpha=0.75 + zi * 0.08,
                          color=[corner_colors[ci] for ci in range(n_corners)],
                          edgecolor='white', linewidth=0.4)
            # Add hatching to distinguish zones
            hatches = ['', '///', 'xxx']
            for bar in bars:
                bar.set_hatch(hatches[zi])

        ax.set_xticks(x); ax.set_xticklabels(corners, color=DIM, fontsize=10)
        ax.set_ylabel("Wear %", color=DIM, fontsize=9)
        ax.set_ylim(0, max(1, ax.get_ylim()[1]) * 1.05)
        # Custom legend: zones, not corners
        from matplotlib.patches import Patch
        legend_elements = [Patch(facecolor='grey', hatch=h, label=z, alpha=0.8)
                           for z, h in zip(zone_labels, ['', '///', 'xxx'])]
        ax.legend(handles=legend_elements, fontsize=9,
                  facecolor='#1e2845', edgecolor='#2a3050', labelcolor=TEXT)
        c.fig.tight_layout(pad=0.8); c.draw()

    def _draw_suspension(self):
        """Two charts: shock velocity (rebound/compression) and ride height per corner."""
        d = self.cur_data
        if d is None:
            for chart in (self._stshock, self._strh):
                chart.clear()
                ax = chart.std_ax("No data")
                ax.text(0.5, 0.5, "No telemetry", transform=ax.transAxes,
                        ha='center', va='center', color=DIM, fontsize=10)
                chart.fig.tight_layout(pad=0.8); chart.draw()
            return

        corners = ['LF', 'RF', 'LR', 'RR']
        corner_colors = [BLUE, RED, GREEN, YELLOW]

        # ── Shock velocity chart ─────────────────────────────────────────────
        c = self._stshock; c.clear()
        shock_found = False
        shock_means: dict[str, list[float]] = {corner: [] for corner in corners}

        for corner in corners:
            ch = d.get_channel(f'{corner}shockVel')
            if ch is None:
                continue
            shock_found = True
            # Per-lap average absolute shock velocity (m/s → mm/s display)
            for li in range(d.num_laps):
                s = d.lap_boundaries[li]; e = d.lap_boundaries[li + 1]
                lap_vel = ch[s:e]
                shock_means[corner].append(float(np.mean(np.abs(lap_vel))) * 1000)  # mm/s

        if not shock_found:
            ax = c.std_ax("Shock Velocity — Avg per Lap (mm/s)")
            ax.text(0.5, 0.5, "No shock velocity channels in this IBT",
                    transform=ax.transAxes, ha='center', va='center', color=DIM, fontsize=11)
            c.fig.tight_layout(pad=0.8); c.draw()
        else:
            ax = c.std_ax("Shock Velocity — Avg |vel| per Lap", xlabel="Lap")
            for corner, col in zip(corners, corner_colors):
                vals = shock_means[corner]
                if vals:
                    ax.plot(range(1, len(vals) + 1), vals, 'o-', color=col,
                            lw=1.5, label=corner, alpha=0.9)
            ax.set_ylabel("mm/s", color=DIM, fontsize=9)
            ax.legend(fontsize=9, facecolor='#1e2845', edgecolor='#2a3050', labelcolor=TEXT)
            c.fig.tight_layout(pad=0.8); c.draw()

        # ── Ride height chart ────────────────────────────────────────────────
        c2 = self._strh; c2.clear()
        rh_found = False
        rh_means: dict[str, list[float]] = {corner: [] for corner in corners}

        for corner in corners:
            ch = d.get_channel(f'{corner}rideHeight')
            if ch is None:
                continue
            rh_found = True
            for li in range(d.num_laps):
                s = d.lap_boundaries[li]; e = d.lap_boundaries[li + 1]
                lap_rh = ch[s:e]
                rh_means[corner].append(float(np.mean(lap_rh)) * 1000)  # m → mm

        if not rh_found:
            ax2 = c2.std_ax("Ride Height — Avg per Lap (mm)")
            ax2.text(0.5, 0.5, "No ride height channels in this IBT",
                     transform=ax2.transAxes, ha='center', va='center', color=DIM, fontsize=11)
            c2.fig.tight_layout(pad=0.8); c2.draw()
        else:
            ax2 = c2.std_ax("Ride Height — Avg per Lap", xlabel="Lap")
            for corner, col in zip(corners, corner_colors):
                vals = rh_means[corner]
                if vals:
                    ax2.plot(range(1, len(vals) + 1), vals, 's-', color=col,
                             lw=1.5, label=corner, alpha=0.9)
            ax2.set_ylabel("mm", color=DIM, fontsize=9)
            ax2.legend(fontsize=9, facecolor='#1e2845', edgecolor='#2a3050', labelcolor=TEXT)
            c2.fig.tight_layout(pad=0.8); c2.draw()

    def _draw_engine_health(self):
        """Engine temps + fuel use rate per lap."""
        d = self.cur_data
        c = self._steng; c.clear()
        if d is None:
            return

        channels = [
            ('OilTemp',      'Oil Temp',   RED,    '°C'),
            ('WaterTemp',    'Water Temp', BLUE,   '°C'),
        ]
        ax = c.std_ax("Engine Temperatures per Lap", xlabel="Lap")
        ax2 = None
        found = False

        for ch_name, label, col, unit in channels:
            ch = d.get_channel(ch_name)
            if ch is None:
                continue
            found = True
            lap_vals = []
            for li in range(d.num_laps):
                s = d.lap_boundaries[li]; e = d.lap_boundaries[li + 1]
                lap_vals.append(float(np.mean(ch[s:e])))
            ax.plot(range(1, len(lap_vals) + 1), lap_vals, 'o-', color=col,
                    lw=1.5, label=label, alpha=0.9)

        # Fuel use per hour on secondary axis
        fph = d.get_channel('FuelUsePerHour')
        if fph is not None:
            fph_vals = []
            for li in range(d.num_laps):
                s = d.lap_boundaries[li]; e = d.lap_boundaries[li + 1]
                fph_vals.append(float(np.mean(fph[s:e])))
            ax2 = ax.twinx()
            ax2.plot(range(1, len(fph_vals) + 1), fph_vals, 's--', color=GREEN,
                     lw=1.2, alpha=0.7, label='Fuel/hr (L)')
            ax2.set_ylabel("L/hr", color=DIM, fontsize=9)
            ax2.tick_params(colors=DIM)
            found = True

        if not found:
            ax.text(0.5, 0.5, "No engine temp channels in this IBT\n(OilTemp, WaterTemp)",
                    transform=ax.transAxes, ha='center', va='center', color=DIM, fontsize=11)
        else:
            ax.set_ylabel("°C", color=DIM, fontsize=9)
            # Combine legends
            h1, l1 = ax.get_legend_handles_labels()
            if ax2:
                h2, l2 = ax2.get_legend_handles_labels()
                ax.legend(h1 + h2, l1 + l2, fontsize=9,
                          facecolor='#1e2845', edgecolor='#2a3050', labelcolor=TEXT)
            else:
                ax.legend(fontsize=9, facecolor='#1e2845', edgecolor='#2a3050', labelcolor=TEXT)
        c.fig.tight_layout(pad=0.8); c.draw()

    def _draw_stint_comparison(self, parent):
        d = self.cur_data
        b = self.cur_best
        if not d or not b or not b.lap_times or len(b.lap_times) < 4: return
        lts = b.lap_times
        med = np.median(lts)
        stints: list[list[tuple[int, float]]] = []
        cur_stint: list[tuple[int, float]] = []
        for i, lt in enumerate(lts):
            if lt > med * 2.0 and cur_stint:
                stints.append(cur_stint); cur_stint = []
            else:
                cur_stint.append((i, lt))
        if cur_stint: stints.append(cur_stint)
        if len(stints) < 2: return
        sec_lbl(parent, f"🔄 Multi-Stint Comparison ({len(stints)} stints)")
        row = ctk.CTkFrame(parent, fg_color="transparent"); row.pack(fill='x', pady=4)
        for si, stint in enumerate(stints):
            times = [t for _, t in stint]
            sf = card_frame(row); sf.pack(side='left', fill='both', expand=True, padx=4, pady=4)
            lbl(sf, f"Stint {si + 1}", 13, bold=True, color=BLUE).pack(pady=(8, 3))
            lbl(sf, f"Laps: {stint[0][0] + 1}–{stint[-1][0] + 1} ({len(stint)})", 10, color=DIM).pack()
            lbl(sf, f"Best: {format_laptime(min(times))}", 11, color=GREEN).pack()
            lbl(sf, f"Avg:  {format_laptime(np.mean(times))}", 11).pack()
            if len(times) >= 3:
                trend = np.polyfit(range(len(times)), times, 1)[0]
                tc = GREEN if trend < -0.02 else RED if trend > 0.02 else TEXT
                lbl(sf, f"Trend: {trend:+.3f}s/lap", 11, color=tc).pack()
            lbl(sf, f"Std: {np.std(times):.3f}s", 10, color=DIM).pack(pady=(0, 8))
        ch = EmbedChart(parent, figsize=(10, 2.5)); ch.pack(fill='x', pady=4)
        ax = ch.std_ax("Stint-by-Stint Lap Times", xlabel="Lap in Stint")
        colors = [BLUE, RED, GREEN, YELLOW, '#ff69b4', '#00ced1']
        for si, stint in enumerate(stints):
            times = [t for _, t in stint]
            col = colors[si % len(colors)]
            ax.plot(range(1, len(times) + 1), times, 'o-', color=col, lw=1.5,
                    label=f"Stint {si + 1}", alpha=0.85)
        ax.set_ylabel("seconds", color=DIM, fontsize=8)
        ax.legend(fontsize=8, facecolor='#1e2845', edgecolor='#2a3050', labelcolor=TEXT)
        ch.fig.tight_layout(pad=0.8); ch.draw()

    def _u_fuel(self):
        fr = self.cur_fuel
        if not fr or fr.fuel_per_lap_l <= 0: return
        f = self._stdf
        sec_lbl(f, "⛽ Fuel Strategy")
        ff = ctk.CTkFrame(f, fg_color=PANEL, corner_radius=8); ff.pack(fill='x', pady=4)
        sr = ctk.CTkFrame(ff, fg_color="transparent"); sr.pack(fill='x', padx=12, pady=10)
        stat_blk(sr, "Fuel/Lap", f"{fr.fuel_per_lap_l:.2f} L", BLUE)
        stat_blk(sr, "Remaining", f"{fr.fuel_remaining_l:.1f} L", GREEN)
        stat_blk(sr, "Laps Left", str(fr.laps_remaining), YELLOW)
        stat_blk(sr, "Tank", f"{fr.fuel_capacity_l:.0f} L", DIM)
        sec_lbl(f, "🏁 Race Planner")
        pf = ctk.CTkFrame(f, fg_color=PANEL, corner_radius=8); pf.pack(fill='x', pady=4)
        row = ctk.CTkFrame(pf, fg_color="transparent"); row.pack(fill='x', padx=12, pady=8)
        lbl(row, "Race Length (laps):", color=DIM).pack(side='left')
        self._fuel_laps_var = ctk.StringVar(value="30")
        ctk.CTkEntry(row, textvariable=self._fuel_laps_var, width=70, fg_color=CARD).pack(side='left', padx=8)
        ctk.CTkButton(row, text="Calculate Strategy", height=28, fg_color=ACCENT,
            hover_color="#c0392b", command=self._calc_fuel_strategy).pack(side='left', padx=8)
        self._fuel_result = ctk.CTkFrame(pf, fg_color="transparent")
        self._fuel_result.pack(fill='x', padx=12, pady=(0, 8))

    def _calc_fuel_strategy(self):
        if not self.cur_data: return
        try:
            race_laps = int(self._fuel_laps_var.get())
        except ValueError:
            messagebox.showwarning("Invalid Input", "Enter a whole number of laps."); return
        if race_laps < 1 or race_laps > 1000:
            messagebox.showwarning("Invalid Input", "Race length must be 1–1000 laps."); return
        fr = FuelStrategyAnalyzer().analyze(self.cur_data, race_laps=race_laps)
        for w in self._fuel_result.winfo_children(): w.destroy()
        if fr.num_stops == 0 and fr.race_laps > 0:
            lbl(self._fuel_result, "✅ No pit stop needed!", 12, bold=True, color=GREEN).pack(anchor='w', pady=4)
        elif fr.num_stops > 0:
            sr = ctk.CTkFrame(self._fuel_result, fg_color="transparent"); sr.pack(fill='x', pady=4)
            stat_blk(sr, "Stops", str(fr.num_stops), ACCENT)
            stat_blk(sr, "Total Fuel", f"{fr.total_fuel_needed_l:.1f} L", BLUE)
            stat_blk(sr, "Finish Fuel", f"{fr.finish_fuel_l:.1f} L", GREEN)
            for i, (pl, fl) in enumerate(zip(fr.pit_laps, fr.fuel_per_stop_l)):
                lbl(self._fuel_result, f"  Stop {i + 1}: Pit on lap {pl}, add {fl:.1f} L",
                    11, color=YELLOW).pack(anchor='w', padx=4)
        for fn in fr.findings:
            lbl(self._fuel_result, f"• {fn}", 10, color=DIM, wraplength=780,
                justify='left', anchor='w').pack(anchor='w', padx=4)

    # ══════════════════════════════════════════════════════════════════════════
    # LAP TIMES
    # ══════════════════════════════════════════════════════════════════════════
    def _t_laptimes(self):
        tab = self.tv.tab("Lap Times"); tab.configure(fg_color=DARK)
        self._ph_laptimes = lbl(tab, "Load a session to see lap time analysis.", 14, color=DIM)
        self._ph_laptimes.pack(pady=40)
        self._ltsc = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        self._ltsc.pack(fill='both', expand=True, padx=10, pady=8)
        self._ltc = EmbedChart(self._ltsc, figsize=(10, 3.5)); self._ltc.pack(fill='x', pady=(0, 8))
        self._ltd = ctk.CTkFrame(self._ltsc, fg_color="transparent"); self._ltd.pack(fill='x')

    def _u_laptimes(self):
        r = self.cur_best
        if not r or not r.lap_times: return
        try: self._ph_laptimes.pack_forget()
        except Exception: pass
        c = self._ltc; c.clear(); ax = c.std_ax("Lap Times — Raw vs Fuel Corrected", xlabel="Lap")
        lps = list(range(1, len(r.lap_times) + 1))
        ax.plot(lps, r.lap_times, 'o-', color=BLUE, label='Raw', lw=1.5)
        if r.fuel_corrected and len(r.fuel_corrected) == len(lps):
            ax.plot(lps, r.fuel_corrected, 's--', color=GREEN, label='Fuel Corrected', lw=1.5, alpha=0.85)
        ax.axhline(r.actual_best, color=RED, lw=1, ls=':', alpha=0.7, label=f'Best {format_laptime(r.actual_best)}')
        ax.set_ylabel("seconds", color=DIM, fontsize=8)
        ax.legend(fontsize=8, facecolor='#1e2845', edgecolor='#2a3050', labelcolor=TEXT)
        c.fig.tight_layout(pad=0.8); c.draw()
        for w in self._ltd.winfo_children(): w.destroy()
        sr = ctk.CTkFrame(self._ltd, fg_color=PANEL, corner_radius=8); sr.pack(fill='x', pady=4)
        sr2 = ctk.CTkFrame(sr, fg_color="transparent"); sr2.pack(fill='x', padx=12, pady=10)
        stat_blk(sr2, "Best (Raw)", format_laptime(r.actual_best), GREEN)
        stat_blk(sr2, "Best (FC)", format_laptime(r.fuel_corrected_best), BLUE)
        stat_blk(sr2, "Fuel/Lap", f"{r.fuel_per_lap_kg:.2f} kg" if r.fuel_per_lap_kg else "—")
        tc = GREEN if r.improvement_trend < -0.05 else RED if r.improvement_trend > 0.05 else TEXT
        stat_blk(sr2, "Trend", f"{r.improvement_trend:+.3f}s/lap", tc)
        stat_blk(sr2, "Improving?", "Yes ↓" if r.laps_improving else "No", GREEN if r.laps_improving else DIM)
        sec_lbl(self._ltd, "📋 Lap-by-Lap")
        fc = r.fuel_corrected or r.lap_times
        rpt_mask = self.cur_rpt.valid_lap_mask if self.cur_rpt and self.cur_rpt.valid_lap_mask else [True] * len(r.lap_times)
        for i, (raw, fcc) in enumerate(zip(r.lap_times, fc)):
            is_outlier = i < len(rpt_mask) and not rpt_mask[i]
            bg = "#3a2020" if is_outlier else ("#1e2845" if i % 2 == 0 else PANEL)
            rw = ctk.CTkFrame(self._ltd, fg_color=bg, corner_radius=4); rw.pack(fill='x', pady=1)
            delta = raw - r.actual_best
            lbl(rw, f"Lap {i + 1}", 11, color=DIM).pack(side='left', padx=12, pady=4)
            lbl(rw, format_laptime(raw), 11, bold=True,
                color=GREEN if raw == r.actual_best else (DIM if is_outlier else TEXT)).pack(side='left', padx=8)
            lbl(rw, f"+{delta:.3f}s" if delta > 0 else "BEST", 10,
                color=YELLOW if delta > 0 else GREEN).pack(side='left', padx=8)
            lbl(rw, f"FC: {format_laptime(fcc)}", 10, color=BLUE).pack(side='left', padx=8)
            if is_outlier: lbl(rw, "⚠ outlier", 9, color=YELLOW).pack(side='left', padx=8)
