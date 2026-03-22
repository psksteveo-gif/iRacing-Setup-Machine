"""Corners tab mixin — corner-by-corner analysis & AI suggestions."""

import threading
import numpy as np
import customtkinter as ctk
from tkinter import messagebox

from ui.theme import (DARK, PANEL, CARD, ACCENT, BLUE, TEXT, DIM, GREEN, YELLOW,
                      RED, PURPLE, lbl, card_frame, stat_blk, sec_lbl, EmbedChart)
from ui.track_map import TrackMapWidget, highlights_from_corners
from core.corner_analysis import CornerAnalyzer, CornerAnalysisReport, LapDeltaAnalyzer
from core.ai_advisor import get_ai_recommendations_stream
from core.config import get_api_key, save_cfg


class CornersTabMixin:
    """Mixin providing Corners tab methods for App."""

    def _t_corners(self):
        tab = self.tv.tab("Corners"); tab.configure(fg_color=DARK)
        self._ph_corners = lbl(tab, "Load a session to see corner-by-corner analysis.", 14, color=DIM)
        self._ph_corners.pack(expand=True)
        self._cor_sc = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        self._cor_sc.pack(fill='both', expand=True, padx=10, pady=8)
        self._cor_summary = ctk.CTkFrame(self._cor_sc, fg_color=PANEL, corner_radius=8)
        self._cor_summary.pack(fill='x', pady=(0, 4))
        self._cor_map = TrackMapWidget(self._cor_sc, figsize=(10, 2.8))
        self._cor_map.pack(fill='x', pady=(0, 4))
        self._cor_delta_chart = EmbedChart(self._cor_sc, figsize=(10, 2.5))
        self._cor_delta_chart.pack(fill='x', pady=(0, 4))
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
        # Track map — corners coloured green→yellow→red by time delta
        hl = highlights_from_corners(report)
        worst = report.corners[report.worst_corner]
        dots = [{'pct': c.apex_pct, 'label': f"T{c.corner_num}",
                 'color': RED if (c.corner_num - 1 == report.worst_corner) else DIM}
                for c in report.corners]
        self._cor_map.update(d, highlights=hl, corner_dots=dots,
                             title="Corner Map — red = worst, green = best")
        # Summary bar
        for w in self._cor_summary.winfo_children(): w.destroy()
        sf = ctk.CTkFrame(self._cor_summary, fg_color="transparent"); sf.pack(fill='x', padx=10, pady=8)
        stat_blk(sf, "Corners Detected", str(len(report.corners)), color=BLUE)
        stat_blk(sf, "Total Time Lost", f"+{report.total_time_lost:.3f}s", color=YELLOW)
        if report.corners:
            worst = report.corners[report.worst_corner]
            stat_blk(sf, "Worst Corner", f"T{worst.corner_num} (+{worst.time_delta:.3f}s)", color=RED)
            best_corner = min(report.corners, key=lambda c: c.time_delta)
            stat_blk(sf, "Best Corner", f"T{best_corner.corner_num}", color=GREEN)
        # Delta chart
        c = self._cor_delta_chart; c.clear()
        ax = c.std_ax("Corner Times — Avg vs Best", xlabel="Corner")
        nums = [f"T{cd.corner_num}" for cd in report.corners]
        x = np.arange(len(report.corners))
        avgs = [cd.avg_time for cd in report.corners]
        bests = [cd.best_time for cd in report.corners]
        w = 0.35
        cols = [RED if i == report.worst_corner else BLUE for i in range(len(report.corners))]
        ax.bar(x - w / 2, avgs, w, label='Avg', color=cols, alpha=0.85)
        ax.bar(x + w / 2, bests, w, label='Best', color=GREEN, alpha=0.85)
        ax.set_xticks(x); ax.set_xticklabels(nums, color=DIM, fontsize=8)
        ax.set_ylabel("seconds", color=DIM, fontsize=8)
        ax.legend(fontsize=8, facecolor='#1c1228', edgecolor='#2a1a38', labelcolor=TEXT)
        c.fig.tight_layout(pad=0.8); c.draw()
        # Corner detail cards
        for w in self._cor_cards.winfo_children(): w.destroy()
        for cd in report.corners:
            is_worst = cd.corner_num - 1 == report.worst_corner
            cf = ctk.CTkFrame(self._cor_cards, fg_color="#1c1228", corner_radius=8)
            cf.pack(fill='x', pady=4)
            hdr = ctk.CTkFrame(cf, fg_color="transparent"); hdr.pack(fill='x', padx=12, pady=(8, 4))
            corner_label = f"🔴 Turn {cd.corner_num}  ← WORST" if is_worst else f"🟢 Turn {cd.corner_num}"
            lbl(hdr, corner_label, 13, bold=True, color=RED if is_worst else TEXT).pack(side='left')
            lbl(hdr, f"{cd.brake_pct * 100:.0f}–{cd.exit_pct * 100:.0f}% track", 10, color=DIM).pack(side='right')
            mr = ctk.CTkFrame(cf, fg_color="transparent"); mr.pack(fill='x', padx=8, pady=4)
            stat_blk(mr, "Entry", f"{np.mean(cd.lap_entry_speeds):.0f} km/h" if cd.lap_entry_speeds else "—", color=BLUE)
            stat_blk(mr, "Apex", f"{np.mean(cd.lap_min_speeds):.0f} km/h" if cd.lap_min_speeds else "—", color=YELLOW)
            stat_blk(mr, "Exit", f"{np.mean(cd.lap_exit_speeds):.0f} km/h" if cd.lap_exit_speeds else "—", color=GREEN)
            stat_blk(mr, "Time", f"{cd.time_in_corner_s:.3f}s" if cd.time_in_corner_s else "—")
            stat_blk(mr, "Delta", f"+{cd.time_delta:.3f}s" if cd.time_delta > 0.001 else "—",
                     color=RED if cd.time_delta > 0.1 else GREEN)
            stat_blk(mr, "Peak G", f"{cd.lat_g_peak:.1f}G" if cd.lat_g_peak else "—", color=PURPLE)
            stat_blk(mr, "Consistency", f"{cd.consistency_pct:.0f}%",
                     color=GREEN if cd.consistency_pct > 90 else YELLOW if cd.consistency_pct > 75 else RED)
            if cd.coaching_note:
                nf = ctk.CTkFrame(cf, fg_color="#100c18", corner_radius=6)
                nf.pack(fill='x', padx=12, pady=(4, 8))
                lbl(nf, "📋 Coach's Notes:", 10, bold=True, color=ACCENT).pack(anchor='w', padx=8, pady=(6, 2))
                lbl(nf, cd.coaching_note, 10, color=TEXT, wraplength=800, justify='left', anchor='w').pack(
                    fill='x', padx=8, pady=(0, 6))
        # Reference Lap Delta
        if d.num_laps >= 2:
            best_lap = int(np.argmin(d.lap_times))
            sorted_laps = sorted(range(d.num_laps), key=lambda i: d.lap_times[i])
            cmp_lap = sorted_laps[1] if len(sorted_laps) > 1 else 0
            delta = LapDeltaAnalyzer().analyze(d, best_lap, cmp_lap)
            if delta and len(delta.segments) > 0:
                dsf = ctk.CTkFrame(self._cor_cards, fg_color="#1c1228", corner_radius=8)
                dsf.pack(fill='x', pady=(8, 4))
                lbl(dsf, f"📊 Lap Delta Notes — Lap {cmp_lap + 1} vs Best (Lap {best_lap + 1})",
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
