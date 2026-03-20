"""
iRacing Data tab mixin.

Shows:
  • Connection status + login form
  • iRating / Safety Rating trend charts
  • Recent race results table (colour-coded iR delta)
  • Personal best laps per car/track
  • IBT correlation panel (API result ↔ local IBT session)
"""
from __future__ import annotations

import threading
from datetime import datetime
from typing import Optional

import customtkinter as ctk

from ui.theme import (
    DARK, PANEL, CARD, ACCENT, BLUE, TEXT, DIM, GREEN, YELLOW, RED,
    lbl, card_frame, stat_blk, EmbedChart,
)
from core.iracing_api import (
    IRacingAPIClient, MemberSummary, RaceResult, BestLap,
    CareerStats, YearlyStat, UpcomingRace, EventLogEntry,
    format_laptime_api, license_level_to_str, get_client,
)


class IRacingTabMixin:
    """Mixin providing the iRacing tab for App.
    Relies on self.cfg, self.sessions, self.after(), and self.tv.
    """

    # ── Tab builder ───────────────────────────────────────────────────────

    def _t_iracing(self):
        tab = self.tv.tab("iRacing")
        tab.configure(fg_color=DARK)

        # ── Connection header ─────────────────────────────────────────
        hdr = ctk.CTkFrame(tab, fg_color=PANEL, height=52, corner_radius=8)
        hdr.pack(fill="x", padx=10, pady=(8, 4))
        hdr.pack_propagate(False)

        self._ir_dot = lbl(hdr, "●", 18, color=RED)
        self._ir_dot.pack(side="left", padx=(12, 4))
        self._ir_status_lbl = lbl(hdr, "Not connected to iRacing", 12, color=DIM)
        self._ir_status_lbl.pack(side="left")

        # Live session badge (shown when SDK is connected)
        self._ir_live_badge = ctk.CTkFrame(hdr, fg_color=CARD, corner_radius=6)
        self._ir_live_badge.pack(side="right", padx=(4, 0))
        self._ir_live_dot = lbl(self._ir_live_badge, "⬤", 10, color=DIM)
        self._ir_live_dot.pack(side="left", padx=(6, 2), pady=4)
        self._ir_live_lbl = lbl(self._ir_live_badge, "SDK: not running", 10, color=DIM)
        self._ir_live_lbl.pack(side="left", padx=(0, 4), pady=4)
        self._ir_sdk_btn = ctk.CTkButton(
            self._ir_live_badge, text="Start", width=52, height=22,
            fg_color=ACCENT, hover_color="#c0392b", font=ctk.CTkFont(size=10),
            command=self._ir_toggle_sdk,
        )
        self._ir_sdk_btn.pack(side="left", padx=(0, 6), pady=4)

        self._ir_refresh_btn = ctk.CTkButton(
            hdr, text="↺  Refresh", width=90, height=30,
            fg_color=CARD, hover_color=ACCENT,
            command=self._ir_refresh,
        )
        self._ir_refresh_btn.pack(side="right", padx=4)

        self._ir_logout_btn = ctk.CTkButton(
            hdr, text="Logout", width=80, height=30,
            fg_color=CARD, hover_color="#8a2222",
            command=self._ir_logout,
        )
        self._ir_logout_btn.pack(side="right", padx=4)

        self._ir_connect_btn = ctk.CTkButton(
            hdr, text="Connect", width=90, height=30,
            fg_color=ACCENT, hover_color="#c0392b",
            command=self._ir_do_login,
        )
        self._ir_connect_btn.pack(side="right", padx=(4, 8))

        # ── Login form ────────────────────────────────────────────────
        self._ir_login_frame = ctk.CTkFrame(tab, fg_color=PANEL, corner_radius=8)
        self._ir_login_frame.pack(fill="x", padx=10, pady=(0, 4))
        lbl(self._ir_login_frame, "iRacing Account", 13, bold=True).pack(
            anchor="w", padx=12, pady=(10, 4))

        er = ctk.CTkFrame(self._ir_login_frame, fg_color="transparent")
        er.pack(fill="x", padx=12, pady=2)
        lbl(er, "Email:", 11, color=DIM).pack(side="left", padx=(0, 8))
        self._ir_email_entry = ctk.CTkEntry(
            er, fg_color=CARD, border_color="#2a3050",
            width=280, height=28, placeholder_text="your@email.com",
        )
        self._ir_email_entry.pack(side="left", padx=8)

        pr = ctk.CTkFrame(self._ir_login_frame, fg_color="transparent")
        pr.pack(fill="x", padx=12, pady=2)
        lbl(pr, "Password:", 11, color=DIM).pack(side="left", padx=(0, 8))
        self._ir_pass_entry = ctk.CTkEntry(
            pr, show="●", fg_color=CARD, border_color="#2a3050",
            width=280, height=28,
        )
        self._ir_pass_entry.pack(side="left", padx=8)
        self._ir_pass_entry.bind("<Return>", lambda _: self._ir_do_login())

        save_row = ctk.CTkFrame(self._ir_login_frame, fg_color="transparent")
        save_row.pack(fill="x", padx=12, pady=(4, 10))
        self._ir_save_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            save_row, text="Save credentials securely (OS keyring)",
            variable=self._ir_save_var,
            fg_color=ACCENT, hover_color=BLUE,
            font=ctk.CTkFont(size=11),
        ).pack(side="left")
        self._ir_login_err = lbl(save_row, "", 11, color=RED)
        self._ir_login_err.pack(side="right", padx=8)

        # ── Main scrollable content (hidden until authenticated) ──────
        self._ir_sc = ctk.CTkScrollableFrame(tab, fg_color="transparent")

        # Stats bar
        self._ir_stats_bar = ctk.CTkFrame(self._ir_sc, fg_color=PANEL, corner_radius=8)
        self._ir_stats_bar.pack(fill="x", pady=(0, 6))

        # Career stats
        lbl(self._ir_sc, "Career Statistics", 13, bold=True, color=BLUE).pack(
            anchor="w", pady=(4, 2))
        self._ir_career_frame = ctk.CTkFrame(self._ir_sc, fg_color="transparent")
        self._ir_career_frame.pack(fill="x", pady=(0, 6))

        # Upcoming races
        lbl(self._ir_sc, "Upcoming Races  (next 50 sessions)", 13,
            bold=True, color=BLUE).pack(anchor="w", pady=(4, 2))
        self._ir_schedule_frame = ctk.CTkScrollableFrame(
            self._ir_sc, fg_color="transparent", height=180)
        self._ir_schedule_frame.pack(fill="x", pady=(0, 6))

        # iRating chart
        lbl(self._ir_sc, "iRating Trend (Road)", 13, bold=True, color=BLUE).pack(
            anchor="w", pady=(4, 2))
        self._ir_irating_chart = EmbedChart(self._ir_sc, figsize=(10, 2.5))
        self._ir_irating_chart.pack(fill="x", pady=(0, 6))

        # SR chart
        lbl(self._ir_sc, "Safety Rating Trend", 13, bold=True, color=BLUE).pack(
            anchor="w", pady=(2, 2))
        self._ir_sr_chart = EmbedChart(self._ir_sc, figsize=(10, 1.8))
        self._ir_sr_chart.pack(fill="x", pady=(0, 6))

        # Yearly stats table
        lbl(self._ir_sc, "Year-by-Year Stats  (Road)", 13, bold=True, color=BLUE).pack(
            anchor="w", pady=(4, 2))
        self._ir_yearly_frame = ctk.CTkFrame(self._ir_sc, fg_color="transparent")
        self._ir_yearly_frame.pack(fill="x", pady=(0, 6))

        # Recent results table
        lbl(self._ir_sc, "Recent Race Results  (click to drill down)", 13,
            bold=True, color=BLUE).pack(anchor="w", pady=(4, 2))
        self._ir_results_frame = ctk.CTkFrame(self._ir_sc, fg_color="transparent")
        self._ir_results_frame.pack(fill="x", pady=(0, 6))

        # Best laps
        lbl(self._ir_sc, "Personal Best Laps", 13, bold=True, color=BLUE).pack(
            anchor="w", pady=(4, 2))
        self._ir_bests_frame = ctk.CTkFrame(self._ir_sc, fg_color="transparent")
        self._ir_bests_frame.pack(fill="x", pady=(0, 6))

        # Personal bests history chart
        lbl(self._ir_sc, "Best Lap Trend (per car+track)", 13,
            bold=True, color=BLUE).pack(anchor="w", pady=(4, 2))
        self._ir_bests_chart = EmbedChart(self._ir_sc, figsize=(10, 2.4))
        self._ir_bests_chart.pack(fill="x", pady=(0, 6))

        # Leaderboard panel
        lb_hdr = ctk.CTkFrame(self._ir_sc, fg_color="transparent")
        lb_hdr.pack(fill="x", pady=(4, 2))
        lbl(lb_hdr, "Community Leaderboard", 13, bold=True, color=BLUE).pack(side="left")
        self._ir_lb_submit_btn = ctk.CTkButton(
            lb_hdr, text="Submit My Best", width=120, height=26,
            fg_color=ACCENT, hover_color="#c0392b",
            command=self._ir_lb_submit,
        )
        self._ir_lb_submit_btn.pack(side="right", padx=4)
        self._ir_lb_frame = ctk.CTkFrame(self._ir_sc, fg_color=PANEL, corner_radius=8)
        self._ir_lb_frame.pack(fill="x", pady=(0, 6))
        lbl(self._ir_lb_frame,
            "Connect and load data to see the leaderboard for your current car+track.",
            11, color=DIM).pack(pady=8)

        # IBT correlation
        lbl(self._ir_sc, "Session Correlation  (API ↔ IBT)", 13,
            bold=True, color=BLUE).pack(anchor="w", pady=(4, 2))
        self._ir_corr_frame = ctk.CTkFrame(self._ir_sc, fg_color=PANEL, corner_radius=8)
        self._ir_corr_frame.pack(fill="x", pady=(0, 10))

        # ── Auto-Load on Session End ──────────────────────────────────
        lbl(self._ir_sc, "Auto-Load on Session End", 13,
            bold=True, color=BLUE).pack(anchor="w", pady=(4, 2))
        al_frame = ctk.CTkFrame(self._ir_sc, fg_color=PANEL, corner_radius=8)
        al_frame.pack(fill="x", pady=(0, 6))
        al_row = ctk.CTkFrame(al_frame, fg_color="transparent")
        al_row.pack(fill="x", padx=12, pady=10)
        self._ir_autoload_var = ctk.BooleanVar(value=False)
        ctk.CTkSwitch(
            al_row,
            text="Watch for new IBT files while iRacing is running",
            variable=self._ir_autoload_var,
            onvalue=True, offvalue=False,
            fg_color=ACCENT, progress_color=GREEN,
            font=ctk.CTkFont(size=12),
            command=self._ir_toggle_autoload,
        ).pack(side="left")
        self._ir_autoload_status = lbl(al_row, "", 11, color=DIM)
        self._ir_autoload_status.pack(side="right", padx=8)

        # ── Partnership Features (roadmap) ───────────────────────────
        lbl(self._ir_sc, "Partnership Features  (roadmap)", 13,
            bold=True, color=BLUE).pack(anchor="w", pady=(8, 2))
        pf_frame = ctk.CTkFrame(self._ir_sc, fg_color=PANEL, corner_radius=8)
        pf_frame.pack(fill="x", pady=(0, 10))

        _PARTNERSHIP_FEATURES = [
            ("✅", GREEN,   "iRacing Data API — session results, iRating, leaderboards"),
            ("✅", GREEN,   "Live SDK telemetry — real-time channel monitoring"),
            ("⏳", YELLOW,  "Setup file write (`.sto`) — pending iRacing partnership"),
            ("⏳", YELLOW,  "Official parameter bounds per car — pending partnership"),
            ("⏳", YELLOW,  "Official parameter step sizes — pending partnership"),
            ("⏳", YELLOW,  "Track characterization data (banking, grip, elevation) — pending"),
            ("⏳", YELLOW,  "Series locked-parameter mapping — pending partnership"),
        ]
        for emoji, color, text in _PARTNERSHIP_FEATURES:
            row = ctk.CTkFrame(pf_frame, fg_color="transparent")
            row.pack(fill="x", padx=12, pady=2)
            lbl(row, emoji, 13).pack(side="left", padx=(0, 6))
            lbl(row, text, 11, color=color).pack(side="left")
        lbl(pf_frame,
            "A partnership inquiry has been submitted to iRacing. "
            "Features marked ⏳ will be activated automatically once the partnership is confirmed.",
            10, color=DIM, wraplength=740).pack(anchor="w", padx=12, pady=(4, 10))

        # ── Pre-fill saved credentials ─────────────────────────────────
        try:
            email, pw = IRacingAPIClient.load_credentials()
            if email:
                self._ir_email_entry.insert(0, email)
            if pw:
                self._ir_pass_entry.insert(0, pw)
        except Exception:
            pass

        lbl(self._ir_sc, "Connect your iRacing account above to load data.", 13,
            color=DIM).pack(expand=True, pady=40)

    # ── Live SDK badge ────────────────────────────────────────────────────

    def _ir_toggle_sdk(self):
        """Start or stop the live iRacing SDK monitor from the iRacing tab."""
        # Delegate to main App's _toggle_live if available
        if hasattr(self, '_toggle_live'):
            self._toggle_live()
            # Update button label based on new state
            self.after(300, self._ir_sync_sdk_btn)

    def _ir_sync_sdk_btn(self):
        """Sync the Start/Stop button label with the monitor state."""
        if not hasattr(self, '_ir_sdk_btn'):
            return
        monitor = getattr(self, '_live_monitor', None)
        if monitor and monitor.is_running:
            self._ir_sdk_btn.configure(text="Stop", fg_color="#666")
        else:
            self._ir_sdk_btn.configure(text="Start", fg_color="#e74c3c")

    def ir_set_live_session(self, car: str, track: str):
        """
        Called from main.py when the live SDK connects/detects a session.
        Updates the badge in the iRacing tab header.
        Pass empty strings to show disconnected state.
        """
        if not hasattr(self, "_ir_live_lbl"):
            return
        if car or track:
            label = f"{car}  @  {track}" if car and track else (car or track)
            self._ir_live_dot.configure(text_color=GREEN)
            self._ir_live_lbl.configure(text=label, text_color=GREEN)
            # Auto-fetch leaderboard for this combo
            if car and track:
                self._ir_fetch_leaderboard(car, track)
        else:
            self._ir_live_dot.configure(text_color=DIM)
            self._ir_live_lbl.configure(text="SDK: not running", text_color=DIM)

    # ── Auto-load toggle ──────────────────────────────────────────────────

    def _ir_toggle_autoload(self):
        """Enable or disable auto-load of new IBT files on session end."""
        enabled = self._ir_autoload_var.get()
        lbl = getattr(self, '_ir_autoload_status', None)
        if not enabled:
            # Stop the file watcher if running
            fw = getattr(self, '_file_watcher', None)
            if fw and fw.is_running:
                fw.stop()
            if lbl:
                lbl.configure(text="Auto-load off", text_color=DIM)
            return

        # Find the iRacing replays/documents folder and watch it
        import os
        candidates = [
            os.path.expanduser("~/Documents/iRacing/telemetry"),
            os.path.expanduser("~/OneDrive/Documents/iRacing/telemetry"),
        ]
        watch_dir = next((d for d in candidates if os.path.isdir(d)), None)
        if not watch_dir:
            if lbl:
                lbl.configure(text="⚠ Could not find iRacing/telemetry folder", text_color=YELLOW)
            self._ir_autoload_var.set(False)
            return

        # Start the file watcher — new .ibt files trigger auto-load
        try:
            from core.file_watcher import FileWatcher

            def _on_new_ibt(path: str):
                """Called by file watcher when a new IBT file appears."""
                self.after(0, lambda p=path: self._ir_on_new_ibt(p))

            fw = getattr(self, '_file_watcher', None)
            if fw and fw.is_running:
                fw.stop()
            self._file_watcher = FileWatcher(watch_dir, pattern="*.ibt",
                                             callback=_on_new_ibt)
            self._file_watcher.start()
            if lbl:
                lbl.configure(
                    text=f"Watching: …/iRacing/telemetry", text_color=GREEN)
        except Exception as exc:
            if lbl:
                lbl.configure(text=f"⚠ {exc}", text_color=YELLOW)
            self._ir_autoload_var.set(False)

    def _ir_on_new_ibt(self, path: str):
        """Triggered when a new IBT file is detected by the file watcher."""
        import os
        from tkinter import messagebox as mb
        fname = os.path.basename(path)
        answer = mb.askyesno(
            "New Session Detected",
            f"A new telemetry file was detected:\n{fname}\n\nLoad it now?",
            parent=self,
        )
        if answer and hasattr(self, '_load_ibt_path'):
            self._load_ibt_path(path)

    # ── Lifecycle ─────────────────────────────────────────────────────────

    def _ir_on_tab_selected(self):
        """Called from _on_tab_change when iRacing tab is selected."""
        self._ir_sync_sdk_btn()
        client = get_client()
        if client.is_authenticated():
            # Silently refresh if last fetch was >5 min ago
            last = getattr(self, "_ir_last_fetch", 0.0)
            import time
            if time.monotonic() - last > 300:
                self._ir_refresh()

    # ── Login / logout ────────────────────────────────────────────────────

    def _ir_do_login(self):
        email = self._ir_email_entry.get().strip()
        password = self._ir_pass_entry.get()
        if not email or not password:
            self._ir_login_err.configure(text="Email and password required")
            return
        self._ir_login_err.configure(text="")
        self._ir_connect_btn.configure(state="disabled", text="Connecting…")
        threading.Thread(
            target=self._ir_auth_bg, args=(email, password), daemon=True
        ).start()

    def _ir_auth_bg(self, email: str, password: str):
        try:
            client = get_client()
            status = client.authenticate(email, password)
            if status.authenticated and self._ir_save_var.get():
                try:
                    IRacingAPIClient.save_credentials(email, password)
                except Exception:
                    pass   # keyring unavailable — non-fatal
        except Exception as exc:
            from core.iracing_api import APIConnectionStatus
            status = APIConnectionStatus(
                authenticated=False,
                error_message=f"Connection error: {exc}",
            )
        self.after(0, lambda: self._ir_on_auth_result(status))

    def _ir_on_auth_result(self, status):
        self._ir_connect_btn.configure(state="normal", text="Connect")
        if status.authenticated:
            self._ir_update_ui_authenticated(status.display_name)
            self._ir_fetch_all(status.cust_id)
        else:
            self._ir_login_err.configure(text=status.error_message or "Authentication failed")

    def _ir_logout(self):
        IRacingAPIClient.clear_credentials()
        get_client()._status.authenticated = False
        self._ir_login_frame.pack(fill="x", padx=10, pady=(0, 4))
        self._ir_sc.pack_forget()
        self._ir_dot.configure(text_color=RED)
        self._ir_status_lbl.configure(text="Not connected to iRacing")

    def _ir_refresh(self):
        client = get_client()
        if not client.is_authenticated():
            return
        threading.Thread(
            target=self._ir_fetch_all,
            args=(client.get_status().cust_id,),
            daemon=True,
        ).start()

    # ── Data fetching ─────────────────────────────────────────────────────

    def _ir_fetch_all(self, cust_id: int):
        import time
        self._ir_last_fetch = time.monotonic()
        client = get_client()

        # Fetch in order; each updates the UI as it arrives
        try:
            summary = client.get_member_summary(cust_id)
            self.after(0, lambda s=summary: self._ir_render_stats(s))
        except Exception as exc:
            self.after(0, lambda: self._ir_status_lbl.configure(
                text=f"Error: {exc}", text_color=RED))
            return

        try:
            career = client.get_career_stats(cust_id)
            self.after(0, lambda c=career: self._ir_render_career(c))
        except Exception:
            pass

        try:
            upcoming = client.get_upcoming_races()
            self.after(0, lambda u=upcoming: self._ir_render_schedule(u))
        except Exception as exc:
            import logging
            logging.getLogger(__name__).debug("Race schedule fetch failed: %s", exc)
            self.after(0, lambda: self._ir_render_schedule([]))

        try:
            ir_hist = client.get_irating_history(cust_id)
            self.after(0, lambda h=ir_hist: self._ir_render_irating(h))
        except Exception:
            pass

        try:
            sr_hist = client.get_sr_history(cust_id)
            self.after(0, lambda h=sr_hist: self._ir_render_sr(h))
        except Exception:
            pass

        try:
            yearly = client.get_yearly_stats(cust_id)
            self.after(0, lambda y=yearly: self._ir_render_yearly(y))
        except Exception:
            pass

        try:
            results = client.get_recent_results(cust_id, limit=30)
            self.after(0, lambda r=results: self._ir_render_results(r))
        except Exception:
            pass

        try:
            bests = client.get_best_laps(cust_id)
            self.after(0, lambda b=bests: (
                self._ir_render_bests(b),
                self._ir_render_bests_chart(b),
            ))
        except Exception:
            pass

        try:
            results_local = getattr(self, "_ir_last_results", [])
            if results_local and hasattr(self, "sessions"):
                corr = client.correlate_with_ibt(results_local, self.sessions)
                self.after(0, lambda c=corr: self._ir_render_correlation(c))
        except Exception:
            pass

    # ── UI update methods (main thread) ───────────────────────────────────

    def _ir_update_ui_authenticated(self, display_name: str):
        self._ir_login_frame.pack_forget()
        self._ir_sc.pack(fill="both", expand=True, padx=10, pady=(4, 8))
        self._ir_dot.configure(text_color=GREEN)
        self._ir_status_lbl.configure(
            text=f"Connected as {display_name}", text_color=GREEN)

    def _ir_render_stats(self, s: MemberSummary):
        for w in self._ir_stats_bar.winfo_children():
            w.destroy()
        sr_row = ctk.CTkFrame(self._ir_stats_bar, fg_color="transparent")
        sr_row.pack(fill="x", padx=12, pady=8)

        cls = license_level_to_str(s.license_level)
        cls_colors = {"R": "#cc0000", "D": "#ff6600", "C": "#ffcc00",
                      "B": "#00cc44", "A": "#0066ff", "P": "#9900cc"}
        cls_col = cls_colors.get(cls, ACCENT)
        ctk.CTkLabel(
            sr_row, text=cls, font=ctk.CTkFont(size=22, weight="bold"),
            fg_color=cls_col, text_color="white", corner_radius=6,
            width=42, height=42,
        ).pack(side="left", padx=(0, 10))

        stat_blk(sr_row, "iRating", str(s.irating), BLUE)
        stat_blk(sr_row, "Safety Rating", f"{s.safety_rating:.2f}", GREEN)
        stat_blk(sr_row, "License", f"{cls} — {s.safety_rating:.2f}", cls_col)
        if s.club_name:
            stat_blk(sr_row, "Club", s.club_name)
        if s.member_since:
            try:
                yr = s.member_since[:4]
                stat_blk(sr_row, "Member since", yr)
            except Exception:
                pass

    def _ir_render_irating(self, history: list[dict]):
        if not history:
            return
        try:
            import matplotlib.pyplot as _plt
            import numpy as np
            from matplotlib.dates import datestr2num

            dates = [h["timestamp"][:10] for h in history]
            values = [h["value"] for h in history]

            ax = self._ir_irating_chart.std_ax()
            xs = range(len(dates))
            ax.plot(xs, values, color=BLUE, linewidth=1.8)
            ax.fill_between(xs, values, min(values), color=BLUE, alpha=0.15)

            # Tick every N sessions
            step = max(1, len(dates) // 6)
            ax.set_xticks(list(range(0, len(dates), step)))
            ax.set_xticklabels([dates[i] for i in range(0, len(dates), step)],
                               rotation=30, ha="right", fontsize=7)
            ax.set_ylabel("iRating", fontsize=8)
            ax.yaxis.set_tick_params(labelsize=7)
            ax.set_xlim(0, max(1, len(dates) - 1))

            # Annotations for min/max
            if values:
                mx_i = int(np.argmax(values))
                ax.annotate(
                    f"Peak\n{values[mx_i]:,}",
                    xy=(mx_i, values[mx_i]),
                    xytext=(mx_i, values[mx_i] + (max(values) - min(values)) * 0.08),
                    fontsize=7, color=GREEN, ha="center",
                )

            self._ir_irating_chart.fig.tight_layout(pad=0.4)
            self._ir_irating_chart.draw()
        except Exception:
            pass

    def _ir_render_sr(self, history: list[dict]):
        if not history:
            return
        try:
            values = [h["value"] for h in history]
            dates  = [h["timestamp"][:10] for h in history]
            ax = self._ir_sr_chart.std_ax()
            xs = range(len(dates))
            ax.plot(xs, values, color=GREEN, linewidth=1.5)
            ax.fill_between(xs, values, 0, color=GREEN, alpha=0.1)
            step = max(1, len(dates) // 6)
            ax.set_xticks(list(range(0, len(dates), step)))
            ax.set_xticklabels([dates[i] for i in range(0, len(dates), step)],
                               rotation=30, ha="right", fontsize=7)
            ax.set_ylabel("Safety Rating", fontsize=8)
            ax.yaxis.set_tick_params(labelsize=7)
            ax.set_xlim(0, max(1, len(dates) - 1))
            ax.set_ylim(0, 5.0)
            self._ir_sr_chart.fig.tight_layout(pad=0.4)
            self._ir_sr_chart.draw()
        except Exception:
            pass

    def _ir_render_results(self, results: list[RaceResult]):
        self._ir_last_results = results
        for w in self._ir_results_frame.winfo_children():
            w.destroy()
        if not results:
            lbl(self._ir_results_frame, "No recent race results.", 11, color=DIM).pack(pady=8)
            return

        # Header row
        cols = ["Date", "Series", "Track", "Car", "Pos", "Inc", "iR Δ", "SR Δ", "Best Lap"]
        widths = [80, 200, 180, 130, 50, 40, 60, 60, 90]
        hdr = ctk.CTkFrame(self._ir_results_frame, fg_color=PANEL, corner_radius=4)
        hdr.pack(fill="x", pady=(0, 2))
        for col, w in zip(cols, widths):
            ctk.CTkLabel(
                hdr, text=col,
                font=ctk.CTkFont(size=10, weight="bold"),
                text_color=DIM, width=w, anchor="w",
            ).pack(side="left", padx=4, pady=4)

        for i, r in enumerate(results):
            row_bg = PANEL if i % 2 == 0 else CARD
            row = ctk.CTkFrame(self._ir_results_frame,
                               fg_color=row_bg, corner_radius=3)
            row.pack(fill="x", pady=1)

            date_str = r.session_start_time[:10] if r.session_start_time else "—"
            ir_col = GREEN if r.irating_change > 0 else RED if r.irating_change < 0 else DIM
            sr_col = GREEN if r.sr_change > 0 else RED if r.sr_change < 0 else DIM
            pos_col = GREEN if r.finish_pos == 1 else (
                YELLOW if r.finish_pos <= 3 else TEXT)

            values = [
                (date_str,  80, TEXT),
                (r.series_name[:28],  200, DIM),
                (r.track_name[:24],   180, TEXT),
                (r.car_name[:18],     130, DIM),
                (f"P{r.finish_pos}",   50, pos_col),
                (str(r.incidents),     40, RED if r.incidents > 4 else TEXT),
                (f"{r.irating_change:+d}", 60, ir_col),
                (f"{r.sr_change:+.2f}",    60, sr_col),
                (format_laptime_api(r.best_lap_time), 90, TEXT),
            ]
            for text, w, color in values:
                ctk.CTkLabel(
                    row, text=text,
                    font=ctk.CTkFont(size=10),
                    text_color=color, width=w, anchor="w",
                ).pack(side="left", padx=4, pady=3)

            # Make entire row clickable if we have a subsession ID
            if r.subsession_id:
                row.configure(cursor="hand2")
                row.bind("<Button-1>",
                         lambda e, result=r: self._ir_open_result_detail(result))
                for child in row.winfo_children():
                    child.configure(cursor="hand2")
                    child.bind("<Button-1>",
                               lambda e, result=r: self._ir_open_result_detail(result))

    def _ir_render_bests(self, bests: list[BestLap]):
        for w in self._ir_bests_frame.winfo_children():
            w.destroy()
        if not bests:
            lbl(self._ir_bests_frame, "No best lap data available.", 11, color=DIM).pack(pady=8)
            return

        # Group by car
        cars: dict[str, list[BestLap]] = {}
        for b in bests:
            cars.setdefault(b.car_name, []).append(b)

        for car_name, car_bests in sorted(cars.items()):
            grp = ctk.CTkFrame(self._ir_bests_frame, fg_color=PANEL, corner_radius=6)
            grp.pack(fill="x", pady=2)
            lbl(grp, car_name, 11, bold=True).pack(anchor="w", padx=10, pady=(6, 2))
            for b in sorted(car_bests, key=lambda x: x.track_name):
                row = ctk.CTkFrame(grp, fg_color="transparent")
                row.pack(fill="x", padx=20, pady=1)
                lbl(row, b.track_name[:40], 10, color=DIM).pack(side="left")
                lbl(row, format_laptime_api(b.best_lap_time), 10,
                    color=GREEN, bold=True).pack(side="right", padx=6)

    def _ir_render_correlation(self,
                                corr: list[tuple[RaceResult, Optional[int]]]):
        for w in self._ir_corr_frame.winfo_children():
            w.destroy()
        lbl(self._ir_corr_frame, "API Result ↔ IBT Session Match",
            11, bold=True).pack(anchor="w", padx=10, pady=(8, 4))

        matched = [(r, i) for r, i in corr if i is not None]
        if not matched:
            lbl(self._ir_corr_frame,
                "No matching IBT sessions loaded. Load IBT files to enable correlation.",
                11, color=DIM).pack(padx=10, pady=(0, 8))
            return

        for r, idx in matched[:10]:
            _, rpt = self.sessions[idx]
            row = ctk.CTkFrame(self._ir_corr_frame, fg_color=CARD, corner_radius=4)
            row.pack(fill="x", padx=10, pady=2)
            lbl(row, r.track_name[:28], 11).pack(side="left", padx=8, pady=4)

            api_t = format_laptime_api(r.best_lap_time)
            ibt_t = format_laptime_api(rpt.best_lap)
            if r.best_lap_time > 0 and rpt.best_lap > 0:
                delta = r.best_lap_time - rpt.best_lap
                delta_str = f"Δ {delta:+.3f}s"
                delta_col = GREEN if abs(delta) < 0.5 else YELLOW
            else:
                delta_str = ""
                delta_col = DIM

            lbl(row, f"API {api_t}", 10, color=BLUE).pack(side="left", padx=6)
            lbl(row, f"IBT {ibt_t}", 10, color=GREEN).pack(side="left", padx=6)
            if delta_str:
                lbl(row, delta_str, 10, color=delta_col).pack(side="left", padx=4)

            ctk.CTkButton(
                row, text="Load IBT →", width=90, height=24,
                fg_color=ACCENT, hover_color="#c0392b",
                command=lambda i=idx: self._sel(*self.sessions[i]),
            ).pack(side="right", padx=8, pady=3)

    # ── Career stats ─────────────────────────────────────────────────────

    def _ir_render_career(self, stats: list[CareerStats]):
        for w in self._ir_career_frame.winfo_children():
            w.destroy()
        if not stats:
            lbl(self._ir_career_frame, "No career data available.", 11, color=DIM).pack(pady=4)
            return

        for s in stats:
            grp = ctk.CTkFrame(self._ir_career_frame, fg_color=PANEL, corner_radius=8)
            grp.pack(fill="x", pady=2)

            hdr_row = ctk.CTkFrame(grp, fg_color="transparent")
            hdr_row.pack(fill="x", padx=12, pady=(8, 4))
            lbl(hdr_row, s.category_name, 12, bold=True).pack(side="left")

            stat_row = ctk.CTkFrame(grp, fg_color="transparent")
            stat_row.pack(fill="x", padx=12, pady=(0, 8))

            def _sb(parent, title, value, color=None):
                f = ctk.CTkFrame(parent, fg_color=CARD, corner_radius=6)
                f.pack(side="left", padx=4)
                lbl(f, value, 15, bold=True, color=color or TEXT).pack(
                    padx=10, pady=(4, 0))
                lbl(f, title, 9, color=DIM).pack(padx=10, pady=(0, 4))

            _sb(stat_row, "Starts", f"{s.starts:,}")
            _sb(stat_row, "Wins", f"{s.wins:,}", GREEN if s.wins > 0 else None)
            _sb(stat_row, "Top 5", f"{s.top5:,}")
            _sb(stat_row, "Poles", f"{s.poles:,}")
            _sb(stat_row, "Win %", f"{s.win_pct:.1f}%",
                GREEN if s.win_pct >= 5 else YELLOW if s.win_pct >= 1 else None)
            _sb(stat_row, "Top-5 %", f"{s.top5_pct:.1f}%")
            _sb(stat_row, "Avg Finish", f"P{s.avg_finish:.1f}")
            _sb(stat_row, "Avg Inc", f"{s.avg_incidents:.2f}",
                GREEN if s.avg_incidents < 2 else YELLOW if s.avg_incidents < 4 else RED)
            _sb(stat_row, "Laps Led", f"{s.laps_led:,}")
            _sb(stat_row, "Total Laps", f"{s.total_laps:,}")

    # ── Upcoming race schedule ─────────────────────────────────────────────

    def _ir_render_schedule(self, races: list[UpcomingRace]):
        for w in self._ir_schedule_frame.winfo_children():
            w.destroy()
        if not races:
            lbl(self._ir_schedule_frame,
                "No upcoming sessions found.", 11, color=DIM).pack(pady=4)
            return

        cols = ["Start (UTC)", "Series", "Track", "Registered", "Lic"]
        widths = [130, 220, 180, 80, 50]
        hdr = ctk.CTkFrame(self._ir_schedule_frame, fg_color=PANEL, corner_radius=4)
        hdr.pack(fill="x", pady=(0, 2))
        for col, w in zip(cols, widths):
            ctk.CTkLabel(hdr, text=col,
                         font=ctk.CTkFont(size=10, weight="bold"),
                         text_color=DIM, width=w, anchor="w",
                         ).pack(side="left", padx=4, pady=4)

        for i, r in enumerate(races):
            row_bg = PANEL if i % 2 == 0 else CARD
            row = ctk.CTkFrame(self._ir_schedule_frame, fg_color=row_bg, corner_radius=3)
            row.pack(fill="x", pady=1)

            # Format UTC time to local-ish display
            try:
                from datetime import datetime, timezone
                dt = datetime.fromisoformat(r.session_start_utc.replace("Z", "+00:00"))
                time_str = dt.strftime("%a %d %b  %H:%M")
            except Exception:
                time_str = r.session_start_utc[:16] if r.session_start_utc else "—"

            track_full = f"{r.track_name}" + (f" — {r.config_name}" if r.config_name else "")
            reg_col = GREEN if r.registered > 20 else YELLOW if r.registered > 5 else DIM

            values = [
                (time_str,          130, TEXT),
                (r.series_name[:32], 220, DIM),
                (track_full[:26],    180, TEXT),
                (str(r.registered),   80, reg_col),
                (r.license_min[:6],   50, DIM),
            ]
            for text, w, color in values:
                ctk.CTkLabel(row, text=text,
                             font=ctk.CTkFont(size=10),
                             text_color=color, width=w, anchor="w",
                             ).pack(side="left", padx=4, pady=3)

    # ── Yearly stats ──────────────────────────────────────────────────────

    def _ir_render_yearly(self, stats: list[YearlyStat]):
        for w in self._ir_yearly_frame.winfo_children():
            w.destroy()
        if not stats:
            lbl(self._ir_yearly_frame, "No yearly data available.", 11, color=DIM).pack(pady=4)
            return

        # Filter to Road category for brevity; show others if no Road data
        road = [s for s in stats if "road" in s.category_name.lower()]
        display = road if road else stats

        cols = ["Year", "Starts", "Wins", "Top 5", "Poles", "Avg Fin", "Avg Inc", "iR Δ", "Laps"]
        widths = [50, 60, 50, 60, 50, 70, 70, 70, 70]
        hdr = ctk.CTkFrame(self._ir_yearly_frame, fg_color=PANEL, corner_radius=4)
        hdr.pack(fill="x", pady=(0, 2))
        for col, w in zip(cols, widths):
            ctk.CTkLabel(hdr, text=col,
                         font=ctk.CTkFont(size=10, weight="bold"),
                         text_color=DIM, width=w, anchor="w",
                         ).pack(side="left", padx=4, pady=4)

        for i, s in enumerate(display):
            row_bg = PANEL if i % 2 == 0 else CARD
            row = ctk.CTkFrame(self._ir_yearly_frame, fg_color=row_bg, corner_radius=3)
            row.pack(fill="x", pady=1)

            ir_col = GREEN if s.irating_change > 0 else RED if s.irating_change < 0 else DIM
            inc_col = GREEN if s.avg_incidents < 2 else YELLOW if s.avg_incidents < 4 else RED

            values = [
                (str(s.year),                  50, TEXT),
                (str(s.starts),                60, TEXT),
                (str(s.wins),                  50, GREEN if s.wins else TEXT),
                (str(s.top5),                  60, TEXT),
                (str(s.poles),                 50, TEXT),
                (f"P{s.avg_finish:.1f}",       70, TEXT),
                (f"{s.avg_incidents:.2f}",     70, inc_col),
                (f"{s.irating_change:+d}",     70, ir_col),
                (f"{s.total_laps:,}",          70, DIM),
            ]
            for text, w, color in values:
                ctk.CTkLabel(row, text=text,
                             font=ctk.CTkFont(size=10),
                             text_color=color, width=w, anchor="w",
                             ).pack(side="left", padx=4, pady=3)

    # ── Personal bests history chart ──────────────────────────────────────

    def _ir_render_bests_chart(self, bests: list[BestLap]):
        """
        Plot each car+track combo's best lap over time as a scatter/line.
        Each car gets a unique colour; x-axis is the BestLap ordering (most
        recent iRacing data first).
        """
        if not hasattr(self, "_ir_bests_chart"):
            return
        ax = self._ir_bests_chart.std_ax()
        if not bests:
            ax.text(0.5, 0.5, "No best lap data", transform=ax.transAxes,
                    ha="center", va="center", color=DIM, fontsize=10)
            self._ir_bests_chart.draw()
            return

        # Group by car
        cars: dict[str, list[BestLap]] = {}
        for b in bests:
            cars.setdefault(b.car_name, []).append(b)

        import matplotlib.cm as cm
        import numpy as np
        colours = cm.tab10(np.linspace(0, 1, max(1, len(cars))))

        for (car_name, car_bests), colour in zip(sorted(cars.items()), colours):
            # Sort by track for a consistent x ordering
            sorted_bests = sorted(car_bests, key=lambda b: b.track_name)
            xs = list(range(len(sorted_bests)))
            ys = [b.best_lap_time for b in sorted_bests]
            labels = [b.track_name[:18] for b in sorted_bests]

            ax.scatter(xs, ys, color=colour, s=40, zorder=3)
            if len(xs) > 1:
                ax.plot(xs, ys, color=colour, linewidth=1, alpha=0.6,
                        label=car_name[:24])
            else:
                ax.plot(xs, ys, "o", color=colour, label=car_name[:24])

            # Label each point with track name
            for x, y, lab in zip(xs, ys, labels):
                ax.annotate(lab, (x, y), textcoords="offset points",
                            xytext=(0, 6), ha="center", fontsize=6,
                            color="#aaaaaa", rotation=45)

        ax.set_ylabel("Best Lap (s)", fontsize=8)
        ax.yaxis.set_tick_params(labelsize=7)
        ax.set_xticks([])
        if len(cars) > 1:
            ax.legend(fontsize=7, loc="upper right")
        self._ir_bests_chart.draw()

    # ── Leaderboard ───────────────────────────────────────────────────────

    def _ir_lb_submit(self):
        """Submit the current session's best lap to the community leaderboard."""
        from tkinter import messagebox, simpledialog
        from core.cloud_sync import submit_leaderboard, CloudSyncError

        if not self.cur_data or not self.cur_rpt:
            messagebox.showwarning("No Session", "Load a session first.", parent=self)
            return

        # Ask for display name
        name = simpledialog.askstring(
            "Leaderboard Name",
            "Enter a display name (leave blank for Anonymous):",
            parent=self,
        )
        if name is None:   # cancelled
            return
        name = name.strip() or None

        def _worker():
            try:
                result = submit_leaderboard(
                    car_name=self.cur_data.car_name or "",
                    track_name=self.cur_data.track_name or "",
                    lap_time_s=self.cur_rpt.best_lap,
                    display_name=name,
                )
                msg = result.get("message", "Submitted!")
                self.after(0, lambda: messagebox.showinfo("Leaderboard", msg, parent=self))
                self.after(0, lambda: self._ir_fetch_leaderboard(
                    self.cur_data.car_name or "",
                    self.cur_data.track_name or "",
                ))
            except CloudSyncError as e:
                self.after(0, lambda: messagebox.showerror("Leaderboard Error", str(e), parent=self))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Error", str(e), parent=self))

        threading.Thread(target=_worker, daemon=True).start()

    def _ir_fetch_leaderboard(self, car_name: str, track_name: str):
        """Fetch leaderboard times for a car+track and render them."""
        from core.cloud_sync import get_leaderboard, get_leaderboard_standing, CloudSyncError

        def _worker():
            try:
                data = get_leaderboard(car_name, track_name, limit=10)
                standing = get_leaderboard_standing(car_name, track_name)
                self.after(0, lambda: self._ir_render_leaderboard(data, standing))
            except CloudSyncError:
                pass   # not logged in or no internet — silently skip
            except Exception:
                pass

        threading.Thread(target=_worker, daemon=True).start()

    # ── Result drill-down window ──────────────────────────────────────────

    def _ir_open_result_detail(self, result: RaceResult):
        """Open a Toplevel window with lap chart + incident log for one subsession."""
        win = ctk.CTkToplevel(self)
        win.title(f"Race Detail — {result.track_name}  {result.session_start_time[:10]}")
        win.geometry("700x560")
        win.configure(fg_color=DARK)
        win.attributes("-topmost", True)
        win.after(100, lambda: win.attributes("-topmost", False))

        # Header
        hdr = ctk.CTkFrame(win, fg_color=PANEL, corner_radius=0)
        hdr.pack(fill="x")
        lbl(hdr, f"{result.series_name}", 13, bold=True).pack(
            side="left", padx=12, pady=8)
        lbl(hdr, f"P{result.finish_pos}  •  {result.car_name}  •  {result.track_name}",
            11, color=DIM).pack(side="left", padx=4)

        stat_row = ctk.CTkFrame(win, fg_color=PANEL, corner_radius=8)
        stat_row.pack(fill="x", padx=10, pady=(6, 4))
        for title, val, col in [
            ("Best Lap", format_laptime_api(result.best_lap_time), GREEN),
            ("iR Δ", f"{result.irating_change:+d}", GREEN if result.irating_change > 0 else RED),
            ("SR Δ", f"{result.sr_change:+.2f}", GREEN if result.sr_change > 0 else RED),
            ("Incidents", str(result.incidents), RED if result.incidents > 4 else TEXT),
            ("Laps", str(result.laps_completed), TEXT),
        ]:
            f = ctk.CTkFrame(stat_row, fg_color=CARD, corner_radius=6)
            f.pack(side="left", padx=4, pady=6)
            lbl(f, val, 15, bold=True, color=col).pack(padx=10, pady=(4, 0))
            lbl(f, title, 9, color=DIM).pack(padx=10, pady=(0, 4))

        # Tabs: lap chart | incident log
        tabs = ctk.CTkTabview(win, fg_color=PANEL)
        tabs.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        tabs.add("Lap Chart")
        tabs.add("Incident Log")

        # Lap chart placeholder
        lc_frame = tabs.tab("Lap Chart")
        lc_frame.configure(fg_color=DARK)
        lc_loading = lbl(lc_frame, "Loading lap chart…", 12, color=DIM)
        lc_loading.pack(expand=True, pady=40)

        # Incident log placeholder
        il_frame = tabs.tab("Incident Log")
        il_frame.configure(fg_color=DARK)
        il_loading = lbl(il_frame, "Loading events…", 12, color=DIM)
        il_loading.pack(expand=True, pady=40)

        # Fetch data in background
        def _fetch():
            client = get_client()
            lap_chart = client.get_lap_chart(result.subsession_id)
            event_log = client.get_event_log(result.subsession_id)
            win.after(0, lambda: self._ir_render_lap_chart(lc_frame, lc_loading, lap_chart))
            win.after(0, lambda: self._ir_render_event_log(il_frame, il_loading, event_log))

        threading.Thread(target=_fetch, daemon=True).start()

    def _ir_render_lap_chart(self, frame, loading_lbl, laps: list[dict]):
        loading_lbl.destroy()
        if not laps:
            lbl(frame, "No lap chart data available.", 11, color=DIM).pack(pady=20)
            return
        try:
            import matplotlib
            matplotlib.use("TkAgg")
            import matplotlib.pyplot as plt
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
            from ui.theme import DARK as _BG

            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(7, 4.5),
                                            facecolor="#1a1a2e", sharex=True)
            fig.subplots_adjust(hspace=0.08, left=0.07, right=0.97, top=0.95, bottom=0.12)

            lap_nums = [l["lap"] for l in laps]
            positions = [l["lap_position"] for l in laps]
            times = [l["lap_time"] for l in laps if l["lap_time"] > 0]
            valid_laps = [l["lap"] for l in laps if l["lap_time"] > 0]

            for ax in (ax1, ax2):
                ax.set_facecolor("#0f0f1a")
                ax.tick_params(colors="#888", labelsize=8)
                for spine in ax.spines.values():
                    spine.set_edgecolor("#2a3050")

            # Position chart (inverted — P1 at top)
            ax1.plot(lap_nums, positions, color="#3498db", linewidth=1.8)
            ax1.fill_between(lap_nums, positions, max(positions) + 1,
                             color="#3498db", alpha=0.12)
            ax1.set_ylabel("Position", fontsize=8, color="#888")
            ax1.invert_yaxis()
            ax1.yaxis.set_tick_params(labelsize=7)

            # Lap time chart
            if valid_laps:
                median_t = sorted(times)[len(times) // 2]
                colours = [GREEN if t < median_t * 1.005 else
                           YELLOW if t < median_t * 1.02 else RED
                           for t in times]
                ax2.scatter(valid_laps, times, c=colours, s=20, zorder=3)
                ax2.plot(valid_laps, times, color="#555", linewidth=0.8, zorder=2)
                ax2.set_ylabel("Lap Time (s)", fontsize=8, color="#888")
                ax2.set_xlabel("Lap", fontsize=8, color="#888")
                ax2.yaxis.set_tick_params(labelsize=7)

            canvas = FigureCanvasTkAgg(fig, master=frame)
            canvas.draw()
            canvas.get_tk_widget().pack(fill="both", expand=True, padx=4, pady=4)
        except Exception:
            lbl(frame, "Could not render chart.", 11, color=DIM).pack(pady=20)

    def _ir_render_event_log(self, frame, loading_lbl, events: list[EventLogEntry]):
        loading_lbl.destroy()
        if not events:
            lbl(frame, "No incidents or events recorded.", 11, color=DIM).pack(pady=20)
            return

        sc = ctk.CTkScrollableFrame(frame, fg_color="transparent")
        sc.pack(fill="both", expand=True, padx=4, pady=4)

        cols = ["Lap", "Type", "Description", "Car #"]
        widths = [50, 120, 380, 60]
        hdr = ctk.CTkFrame(sc, fg_color=PANEL, corner_radius=4)
        hdr.pack(fill="x", pady=(0, 2))
        for col, w in zip(cols, widths):
            ctk.CTkLabel(hdr, text=col,
                         font=ctk.CTkFont(size=10, weight="bold"),
                         text_color=DIM, width=w, anchor="w",
                         ).pack(side="left", padx=4, pady=4)

        type_colors = {
            "incident": RED, "caution": YELLOW,
            "green": GREEN, "checkered": GREEN,
        }
        for i, e in enumerate(events):
            row_bg = PANEL if i % 2 == 0 else CARD
            row = ctk.CTkFrame(sc, fg_color=row_bg, corner_radius=3)
            row.pack(fill="x", pady=1)
            etype = e.event_type.lower()
            ecol = next((c for k, c in type_colors.items() if k in etype), DIM)
            for text, w, color in [
                (str(e.lap),              50, TEXT),
                (e.event_type[:18],      120, ecol),
                (e.description[:56],     380, TEXT),
                (e.car_number[:8],        60, DIM),
            ]:
                ctk.CTkLabel(row, text=text,
                             font=ctk.CTkFont(size=10),
                             text_color=color, width=w, anchor="w",
                             ).pack(side="left", padx=4, pady=3)

    def _ir_render_leaderboard(self, data: dict, standing: dict):
        for w in self._ir_lb_frame.winfo_children():
            w.destroy()

        entries = data.get("entries", [])
        if not entries:
            lbl(self._ir_lb_frame, "No entries yet — be the first to submit!", 11,
                color=DIM).pack(pady=8)
            return

        # Header
        hdr = ctk.CTkFrame(self._ir_lb_frame, fg_color="transparent")
        hdr.pack(fill="x", padx=10, pady=(8, 2))
        for text, anchor in [("Rank", "w"), ("Name", "w"), ("Time", "e"), ("", "e")]:
            lbl(hdr, text, 10, bold=True, color=DIM).pack(side="left", padx=(0, 24))

        for e in entries:
            row = ctk.CTkFrame(self._ir_lb_frame, fg_color=CARD, corner_radius=4)
            row.pack(fill="x", padx=10, pady=1)
            rank_col = GREEN if e["rank"] == 1 else (YELLOW if e["rank"] <= 3 else TEXT)
            lbl(row, f"#{e['rank']}", 11, bold=True, color=rank_col).pack(
                side="left", padx=(8, 12))
            lbl(row, e["display_name"][:28], 11).pack(side="left", expand=True, anchor="w")
            lbl(row, e["lap_time_fmt"], 11, color=GREEN, bold=True).pack(side="right", padx=8)
            if e.get("is_verified"):
                lbl(row, "✓", 10, color=BLUE).pack(side="right")

        # My standing badge
        if standing.get("entered"):
            badge = ctk.CTkFrame(self._ir_lb_frame, fg_color=PANEL, corner_radius=6)
            badge.pack(fill="x", padx=10, pady=(6, 8))
            lbl(badge,
                f"Your best: {standing['lap_time_fmt']}  •  "
                f"Rank #{standing['rank']} of {standing['total']}  •  "
                f"Top {100 - standing['percentile']:.0f}%",
                11, color=ACCENT).pack(pady=6)
