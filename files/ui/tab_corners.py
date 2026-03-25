"""Corners tab mixin — corner-by-corner analysis & AI suggestions."""

import threading
import numpy as np
import customtkinter as ctk
from tkinter import messagebox

from ui.theme import (DARK, PANEL, CARD, ACCENT, BLUE, TEXT, DIM, GREEN, YELLOW,
                      RED, PURPLE, lbl, card_frame, stat_blk, sec_lbl)
from core.corner_analysis import CornerAnalyzer, CornerAnalysisReport, LapDeltaAnalyzer
from core.ai_advisor import get_ai_recommendations_stream
from core.config import get_api_key, save_cfg
from core import units


class CornersTabMixin:
    """Mixin providing Corners tab methods for App."""

    def _t_corners(self):
        tab = self.tv.tab("Corners"); tab.configure(fg_color=DARK)
        self._ph_corners = lbl(tab, "Load a session to see corner-by-corner analysis.", 14, color=DIM)
        self._ph_corners.pack(expand=True)
        self._cor_sc = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        self._cor_sc.pack(fill='both', expand=True, padx=10, pady=8)
        self._cor_summary = ctk.CTkFrame(self._cor_sc, fg_color=PANEL, corner_radius=8)
        self._cor_summary.pack(fill='x', pady=(0, 8))
        self._cor_cards = ctk.CTkFrame(self._cor_sc, fg_color="transparent")
        self._cor_cards.pack(fill='x')
        self._cor_ai_hdr = ctk.CTkFrame(self._cor_sc, fg_color=PANEL, height=44, corner_radius=8)
        self._cor_ai_hdr.pack(fill='x', pady=(8, 4)); self._cor_ai_hdr.pack_propagate(False)
        lbl(self._cor_ai_hdr, "🤖  AI Corner-Specific Setup Suggestions", 12, bold=True).pack(side='left', padx=12)
        self._cor_ai_status = lbl(self._cor_ai_hdr, "", 10, color=DIM); self._cor_ai_status.pack(side='right', padx=8)
        self._cor_ai_btn = ctk.CTkButton(self._cor_ai_hdr, text="Get Corner Suggestions", width=180, height=28,
            fg_color=ACCENT, hover_color="#a03010", command=self._get_corner_ai)
        self._cor_ai_btn.pack(side='right', padx=8)
        self._cor_ai_text = ctk.CTkTextbox(self._cor_sc, fg_color=PANEL, text_color=TEXT, height=300,
            font=ctk.CTkFont(family="Helvetica", size=14), wrap='word')
        self._cor_ai_text.pack(fill='x', pady=(0, 8))
        self._cor_ai_text.insert('1.0', "Analyze corners first, then click 'Get Corner Suggestions' for AI-powered per-corner setup changes.")
        self._cor_ai_text.configure(state='disabled')
        self.cur_corner_report: CornerAnalysisReport | None = None

    # ── Good / Bad classifier ─────────────────────────────────────────────
    @staticmethod
    def _corner_good_bad(cd) -> tuple:
        """Return (goods: list[str], bads: list[str]) for a corner."""
        goods, bads = [], []

        # Consistency
        if cd.consistency_pct >= 92:
            goods.append(f"Very consistent corner times ({cd.consistency_pct:.0f}%)")
        elif cd.consistency_pct >= 78:
            goods.append(f"Reasonable consistency ({cd.consistency_pct:.0f}%)")
        else:
            bads.append(f"Inconsistent lap times ({cd.consistency_pct:.0f}%) — execution varies lap to lap")

        # Brake point consistency
        if cd.brake_point_consistency >= 92:
            goods.append("Consistent brake marker")
        elif cd.brake_point_consistency < 70:
            bads.append("Brake point moves lap to lap — pick a fixed visual reference")

        # Braking pressure
        if cd.brake_pressure_avg > 0:
            if cd.brake_pressure_avg > 0.88:
                bads.append(f"Over-braking ({cd.brake_pressure_avg * 100:.0f}% avg pressure) — risk of lock-up; trail off earlier")
            elif cd.brake_pressure_avg > 0.72:
                goods.append(f"Strong, committed braking ({cd.brake_pressure_avg * 100:.0f}%)")
            elif cd.brake_pressure_avg < 0.35:
                bads.append(f"Light braking ({cd.brake_pressure_avg * 100:.0f}%) — you may be braking too early; try later, harder")

        # Exit throttle
        if cd.throttle_exit_avg > 0:
            if cd.throttle_exit_avg >= 0.72:
                goods.append(f"Aggressive exit throttle ({cd.throttle_exit_avg * 100:.0f}%) — good for drive out")
            elif cd.throttle_exit_avg >= 0.50:
                goods.append(f"Decent exit throttle ({cd.throttle_exit_avg * 100:.0f}%)")
            else:
                bads.append(f"Timid exit throttle ({cd.throttle_exit_avg * 100:.0f}%) — get on the power earlier at apex")

        # Entry speed variation
        if len(cd.lap_entry_speeds) >= 3:
            entry_std = float(np.std(cd.lap_entry_speeds))
            if entry_std <= 2.5:
                goods.append("Consistent entry speed")
            elif entry_std > 6:
                bads.append(f"Entry speed varies ±{entry_std:.0f} km/h — braking distance inconsistency")

        # Apex speed vs entry
        if cd.lap_entry_speeds and cd.lap_min_speeds:
            avg_entry = float(np.mean(cd.lap_entry_speeds))
            avg_min   = float(np.mean(cd.lap_min_speeds))
            ratio = avg_min / avg_entry if avg_entry > 0 else 0
            if ratio >= 0.72:
                goods.append(f"Good minimum speed through apex ({avg_min:.0f} km/h)")
            elif ratio < 0.55:
                bads.append(f"Heavy speed scrub at apex ({avg_min:.0f} km/h vs {avg_entry:.0f} km/h entry) — rotate earlier or carry more speed")

        # Exit speed
        if cd.lap_exit_speeds and cd.lap_min_speeds:
            avg_exit = float(np.mean(cd.lap_exit_speeds))
            avg_min  = float(np.mean(cd.lap_min_speeds))
            recovery = avg_exit - avg_min
            if recovery >= 20:
                goods.append(f"Strong exit acceleration (+{recovery:.0f} km/h from apex)")
            elif recovery < 8:
                bads.append(f"Slow exit acceleration (+{recovery:.0f} km/h from apex) — trail brake less and open throttle sooner")

        # Peak lateral G
        if cd.lat_g_peak > 0:
            if cd.lat_g_peak >= 2.5:
                goods.append(f"High lateral load through corner ({cd.lat_g_peak:.1f}G) — good use of grip")
            elif cd.lat_g_peak < 1.2:
                bads.append(f"Low lateral load ({cd.lat_g_peak:.1f}G) — running a wide line or scrubbing speed unnecessarily")

        # Time delta rating
        if cd.time_delta <= 0.02:
            goods.append("Near-optimal corner time — minimal time left on track")
        elif cd.time_delta > 0.15:
            bads.append(f"+{cd.time_delta:.3f}s lost vs best lap — high-priority corner to improve")
        elif cd.time_delta > 0.06:
            bads.append(f"+{cd.time_delta:.3f}s lost vs best lap — work in progress")

        return goods, bads

    def _u_corners(self):
        d = self.cur_data
        if not d or d.num_laps < 1: return
        try: self._ph_corners.pack_forget()
        except Exception: pass
        self._cor_sc.pack(fill='both', expand=True, padx=10, pady=8)
        report = CornerAnalyzer().analyze(d)
        self.cur_corner_report = report
        if not report.corners:
            for w in self._cor_summary.winfo_children(): w.destroy()
            lbl(self._cor_summary, "No corners detected — telemetry may lack sufficient braking data.", 12, color=DIM).pack(pady=10)
            return
        # Summary bar
        for w in self._cor_summary.winfo_children(): w.destroy()
        sf = ctk.CTkFrame(self._cor_summary, fg_color="transparent"); sf.pack(fill='x', padx=10, pady=10)
        stat_blk(sf, "Corners Detected", str(len(report.corners)), color=BLUE)
        stat_blk(sf, "Total Time Lost", f"+{report.total_time_lost:.3f}s", color=YELLOW)
        if report.corners:
            worst = report.corners[report.worst_corner]
            stat_blk(sf, "Worst Corner", f"{worst.label} (+{worst.time_delta:.3f}s)", color=RED)
            best_corner = min(report.corners, key=lambda c: c.time_delta)
            stat_blk(sf, "Best Corner", best_corner.label, color=GREEN)

        # ── Per-corner cards with Good / Bad breakdown ────────────────────
        for w in self._cor_cards.winfo_children(): w.destroy()
        for cd in report.corners:
            is_worst = cd.corner_num - 1 == report.worst_corner
            border_col = RED if is_worst else BLUE
            cf = ctk.CTkFrame(self._cor_cards, fg_color="#0E0A18",
                              corner_radius=8, border_width=1, border_color=border_col)
            cf.pack(fill='x', pady=5)

            # ── Header ────────────────────────────────────────────────────
            hdr = ctk.CTkFrame(cf, fg_color="#140E22", corner_radius=0)
            hdr.pack(fill='x', padx=0, pady=0)
            title = cd.corner_name if cd.corner_name else f"Turn {cd.corner_num}"
            badge = f"  WORST  " if is_worst else (f"  +{cd.time_delta:.3f}s  " if cd.time_delta > 0.001 else "  BEST  ")
            badge_col = RED if is_worst else (YELLOW if cd.time_delta > 0.05 else GREEN)
            lbl(hdr, title, 13, bold=True, color=RED if is_worst else TEXT).pack(side='left', padx=14, pady=8)
            ctk.CTkLabel(hdr, text=badge, font=ctk.CTkFont(size=11, weight='bold'),
                         fg_color=badge_col, text_color="#000000",
                         corner_radius=6).pack(side='left', padx=4, pady=8)
            lbl(hdr, f"{cd.brake_pct * 100:.0f}–{cd.exit_pct * 100:.0f}% of lap", 9, color=DIM).pack(side='right', padx=14)

            # ── Metrics row ───────────────────────────────────────────────
            mr = ctk.CTkFrame(cf, fg_color="transparent"); mr.pack(fill='x', padx=8, pady=(6, 2))
            stat_blk(mr, "Entry",       units.fmt_speed_from_kmh(float(np.mean(cd.lap_entry_speeds)), 0) if cd.lap_entry_speeds else "—", color=BLUE)
            stat_blk(mr, "Apex",        units.fmt_speed_from_kmh(float(np.mean(cd.lap_min_speeds)),   0) if cd.lap_min_speeds   else "—", color=YELLOW)
            stat_blk(mr, "Exit",        units.fmt_speed_from_kmh(float(np.mean(cd.lap_exit_speeds)),  0) if cd.lap_exit_speeds  else "—", color=GREEN)
            stat_blk(mr, "Corner time", f"{cd.time_in_corner_s:.2f}s" if cd.time_in_corner_s else "—")
            stat_blk(mr, "Peak G",      f"{cd.lat_g_peak:.1f}G"       if cd.lat_g_peak        else "—", color=PURPLE)
            stat_blk(mr, "Brake press", f"{cd.brake_pressure_avg * 100:.0f}%" if cd.brake_pressure_avg else "—",
                     color=RED if cd.brake_pressure_avg > 0.88 else TEXT)
            stat_blk(mr, "Exit throttle", f"{cd.throttle_exit_avg * 100:.0f}%" if cd.throttle_exit_avg else "—",
                     color=GREEN if cd.throttle_exit_avg >= 0.65 else YELLOW)
            stat_blk(mr, "Consistency", f"{cd.consistency_pct:.0f}%",
                     color=GREEN if cd.consistency_pct > 90 else YELLOW if cd.consistency_pct > 75 else RED)

            # ── Good / Bad breakdown ──────────────────────────────────────
            goods, bads = self._corner_good_bad(cd)
            gb_row = ctk.CTkFrame(cf, fg_color="transparent"); gb_row.pack(fill='x', padx=12, pady=(4, 8))

            # Good column
            good_f = ctk.CTkFrame(gb_row, fg_color="#081A10", corner_radius=6)
            good_f.pack(side='left', fill='both', expand=True, padx=(0, 4))
            lbl(good_f, "✓  What's working", 10, bold=True, color=GREEN).pack(anchor='w', padx=10, pady=(7, 3))
            if goods:
                for g in goods:
                    row = ctk.CTkFrame(good_f, fg_color="transparent"); row.pack(fill='x', padx=8, pady=1)
                    lbl(row, "▸", 10, color=GREEN).pack(side='left', padx=(0, 4))
                    lbl(row, g, 10, color=TEXT, wraplength=360, anchor='w', justify='left').pack(side='left', fill='x', expand=True)
            else:
                lbl(good_f, "No standout positives yet", 10, color=DIM).pack(anchor='w', padx=10, pady=2)
            ctk.CTkFrame(good_f, fg_color="transparent", height=6).pack()

            # Bad column
            bad_f = ctk.CTkFrame(gb_row, fg_color="#1A0A0A", corner_radius=6)
            bad_f.pack(side='left', fill='both', expand=True, padx=(4, 0))
            lbl(bad_f, "✗  Fix next session", 10, bold=True, color=ACCENT).pack(anchor='w', padx=10, pady=(7, 3))
            if bads:
                for b in bads:
                    row = ctk.CTkFrame(bad_f, fg_color="transparent"); row.pack(fill='x', padx=8, pady=1)
                    lbl(row, "▸", 10, color=ACCENT).pack(side='left', padx=(0, 4))
                    lbl(row, b, 10, color=TEXT, wraplength=360, anchor='w', justify='left').pack(side='left', fill='x', expand=True)
            else:
                lbl(bad_f, "Nothing critical to fix here", 10, color=DIM).pack(anchor='w', padx=10, pady=2)
            ctk.CTkFrame(bad_f, fg_color="transparent", height=6).pack()

        # Reference Lap Delta
        if d.num_laps >= 2:
            best_lap = int(np.argmin(d.lap_times))
            sorted_laps = sorted(range(d.num_laps), key=lambda i: d.lap_times[i])
            cmp_lap = sorted_laps[1] if len(sorted_laps) > 1 else 0
            delta = LapDeltaAnalyzer().analyze(d, best_lap, cmp_lap)
            if delta and len(delta.segments) > 0:
                dsf = ctk.CTkFrame(self._cor_cards, fg_color="#1c1228", corner_radius=8)
                dsf.pack(fill='x', pady=(8, 4))
                lbl(dsf, f"📊 Lap Delta — Lap {cmp_lap + 1} vs Best (Lap {best_lap + 1})",
                    12, bold=True, color=BLUE).pack(anchor='w', padx=12, pady=(8, 4))
                for seg in delta.segments:
                    sf = ctk.CTkFrame(dsf, fg_color="#100c18", corner_radius=4)
                    sf.pack(fill='x', padx=12, pady=2)
                    lbl(sf, seg['note'], 10, color=TEXT, wraplength=800, justify='left', anchor='w').pack(
                        fill='x', padx=8, pady=4)

    def _get_corner_ai(self):
        if not self.cur_rpt:
            messagebox.showwarning("No Session", "Load a session first."); return
        if not self.cur_corner_report or not self.cur_corner_report.corners:
            messagebox.showwarning("No Corners", "Switch to the Corners tab to run corner analysis first."); return
        if not self.cfg.get('ai_consent'):
            ok = messagebox.askyesno("AI Data Notice",
                "This will send session telemetry data to the\n"
                "Anthropic Claude API for analysis.\n\n"
                "No personally identifiable information is included.\n\n"
                "Allow data transmission?")
            if not ok: return
            self.cfg['ai_consent'] = True
            save_cfg(self.cfg)
        key = get_api_key().strip()
        if not key:
            messagebox.showwarning("API Key Needed", "Set your key in Settings.")
            self._settings(); return
        self._cor_ai_btn.configure(state='disabled', text="Analyzing…")
        self._cor_ai_status.configure(text="⏳ Streaming from Claude…")
        self._cor_ai_text.configure(state='normal')
        self._cor_ai_text.delete('1.0', 'end')
        self._ai_cancel = threading.Event()
        cancel = self._ai_cancel

        def worker():
            if self.cur_data is None: return
            setup_flat = self.cur_setup.flat if self.cur_setup else None
            try:
                for chunk in get_ai_recommendations_stream(
                        self.cur_rpt, self.cur_data.car_name, self.cur_data.track_name, key,
                        setup_data=setup_flat,
                        sector_report=self.cur_sec,
                        style_report=self.cur_style,
                        stint_report=self.cur_stint,
                        session_info=self.cur_data.session_info,
                        best_report=self.cur_best,
                        corner_report=self.cur_corner_report):
                    if cancel.is_set(): return
                    self.after(0, lambda c=chunk: self._on_cor_ai_chunk(c))
            except Exception as ex:
                import logging
                logging.getLogger(__name__).warning("Corner AI streaming failed: %s", ex)
                if not cancel.is_set():
                    self.after(0, lambda: self._on_cor_ai_chunk(
                        "\n\n⚠ AI request failed. Check your API key and internet.\n"))
            if not cancel.is_set():
                self.after(0, self._on_cor_ai_done)
        t = threading.Thread(target=worker, daemon=True)
        t.start()

        def _timeout():
            if t.is_alive():
                cancel.set()
                self.after(0, lambda: (
                    self._cor_ai_btn.configure(state='normal', text="Get Corner Suggestions"),
                    self._cor_ai_status.configure(text="⚠ Timed out")))
        self.after(90_000, _timeout)

    def _on_cor_ai_chunk(self, chunk):
        self._cor_ai_text.configure(state='normal')
        self._cor_ai_text.insert('end', chunk)
        self._cor_ai_text.see('end')
        self._cor_ai_text.configure(state='disabled')

    def _on_cor_ai_done(self):
        self._cor_ai_btn.configure(state='normal', text="Get Corner Suggestions")
        self._cor_ai_status.configure(text="✅ Done")
