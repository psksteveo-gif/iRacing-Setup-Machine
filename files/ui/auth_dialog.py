"""
Cloud Account dialog — Login / Register / Account management.
Imported by main.py and triggered from the header "Account" button.
"""
from __future__ import annotations

import threading
import webbrowser
from typing import Callable, Optional

import customtkinter as ctk

# ── Theme constants (import from existing theme) ───────────────────────────
try:
    from ui.theme import DARK, PANEL, ACCENT, GREEN, RED, YELLOW, DIM, TEXT, lbl, BLUE
except ImportError:
    DARK = "#1a1a2e"; PANEL = "#16213e"; ACCENT = "#e94560"
    GREEN = "#2ecc71"; RED = "#e74c3c"; YELLOW = "#f39c12"
    DIM = "#8a8fa3";   TEXT = "#e0e0e0"; BLUE = "#00b4d8"
    def lbl(parent, text, size=12, **kw):
        return ctk.CTkLabel(parent, text=text, font=ctk.CTkFont(size=size))


# ── Auth Dialog ───────────────────────────────────────────────────────────

class AuthDialog(ctk.CTkToplevel):
    """Login / Register modal. Calls on_success(user_data) when auth succeeds."""

    def __init__(self, parent, on_success: Optional[Callable] = None):
        super().__init__(parent)
        self.on_success = on_success
        self.title("Sign In — iRacing Setup Advisor")
        self.geometry("440x520")
        self.resizable(False, False)
        self.configure(fg_color=DARK)
        self.grab_set()
        self.after(50, self.lift)

        self._mode = ctk.StringVar(value="login")  # "login" | "register"
        self._error_var = ctk.StringVar()
        self._build()

    def _build(self):
        # ── Header ────────────────────────────────────────────────────
        ctk.CTkLabel(self, text="iRacing Setup Advisor",
                     font=ctk.CTkFont(size=20, weight="bold"),
                     text_color=ACCENT).pack(pady=(24, 2))
        ctk.CTkLabel(self, text="Sign in to unlock cloud features",
                     font=ctk.CTkFont(size=12), text_color=DIM).pack()

        # ── Tab bar ───────────────────────────────────────────────────
        tab_row = ctk.CTkFrame(self, fg_color="transparent")
        tab_row.pack(pady=(16, 0))
        for mode, label in [("login", "Sign In"), ("register", "Create Account")]:
            ctk.CTkButton(
                tab_row, text=label, width=160, height=32,
                fg_color=PANEL if mode != "login" else ACCENT,
                hover_color=ACCENT,
                command=lambda m=mode: self._switch_mode(m),
            ).pack(side="left", padx=4)

        # ── Form container ────────────────────────────────────────────
        self._form_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._form_frame.pack(fill="x", padx=32, pady=(12, 0))
        self._build_form()

        # ── Error label ───────────────────────────────────────────────
        self._err_lbl = ctk.CTkLabel(self, textvariable=self._error_var,
                                      text_color=RED, wraplength=370,
                                      font=ctk.CTkFont(size=11))
        self._err_lbl.pack(pady=(6, 0), padx=32)

        # ── Submit button ─────────────────────────────────────────────
        self._submit_btn = ctk.CTkButton(
            self, text="Sign In", height=40, width=240,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=ACCENT, command=self._submit,
        )
        self._submit_btn.pack(pady=(12, 4))

        # ── Forgot password / terms ───────────────────────────────────
        self._extra_lbl = ctk.CTkLabel(
            self, text="Forgot password?",
            font=ctk.CTkFont(size=11), text_color=BLUE, cursor="hand2"
        )
        self._extra_lbl.bind("<Button-1>", lambda _: self._forgot_password())
        self._extra_lbl.pack()

        ctk.CTkLabel(self, text="By registering you agree to our Terms of Service",
                     font=ctk.CTkFont(size=10), text_color=DIM).pack(pady=(8, 16))

    def _build_form(self):
        for w in self._form_frame.winfo_children():
            w.destroy()

        mode = self._mode.get()

        if mode == "register":
            lbl(self._form_frame, "Display Name", 12, color=DIM).pack(anchor="w")
            self._name_entry = ctk.CTkEntry(self._form_frame, height=36, placeholder_text="Your name")
            self._name_entry.pack(fill="x", pady=(2, 8))
        else:
            self._name_entry = None

        lbl(self._form_frame, "Email", 12, color=DIM).pack(anchor="w")
        self._email_entry = ctk.CTkEntry(self._form_frame, height=36, placeholder_text="you@example.com")
        self._email_entry.pack(fill="x", pady=(2, 8))
        self._email_entry.bind("<Return>", lambda _: self._pw_entry.focus_set())

        lbl(self._form_frame, "Password", 12, color=DIM).pack(anchor="w")
        self._pw_entry = ctk.CTkEntry(self._form_frame, height=36, show="●",
                                       placeholder_text="At least 8 characters")
        self._pw_entry.pack(fill="x", pady=(2, 0))
        self._pw_entry.bind("<Return>", lambda _: self._submit())

        if mode == "register":
            lbl(self._form_frame, "Confirm Password", 12, color=DIM).pack(anchor="w", pady=(8, 0))
            self._pw2_entry = ctk.CTkEntry(self._form_frame, height=36, show="●")
            self._pw2_entry.pack(fill="x", pady=(2, 0))
            self._pw2_entry.bind("<Return>", lambda _: self._submit())
        else:
            self._pw2_entry = None

    def _switch_mode(self, mode: str):
        self._mode.set(mode)
        self._error_var.set("")
        self._submit_btn.configure(text="Sign In" if mode == "login" else "Create Account")
        # Rebuild tab styling
        for child in self.winfo_children():
            pass   # Tab buttons rebuild colour in _build_form
        self._build_form()

    def _submit(self):
        self._error_var.set("")
        email = self._email_entry.get().strip()
        password = self._pw_entry.get()

        if not email or not password:
            self._error_var.set("Email and password are required.")
            return

        if self._mode.get() == "register":
            pw2 = self._pw2_entry.get() if self._pw2_entry else ""
            if password != pw2:
                self._error_var.set("Passwords do not match.")
                return
            if len(password) < 8:
                self._error_var.set("Password must be at least 8 characters.")
                return

        self._submit_btn.configure(state="disabled", text="Please wait…")
        self._error_var.set("")

        def _do():
            try:
                from core.cloud_sync import login, register, CloudSyncError, AuthError
                if self._mode.get() == "login":
                    name = self._name_entry.get().strip() if self._name_entry else None
                    data = login(email, password)
                else:
                    name = self._name_entry.get().strip() if self._name_entry else None
                    data = register(email, password, display_name=name or None)
                self.after(0, lambda: self._on_auth_success(data))
            except (AuthError, Exception) as exc:
                self.after(0, lambda: self._on_auth_error(str(exc)))

        threading.Thread(target=_do, daemon=True).start()

    def _on_auth_success(self, data: dict):
        self._submit_btn.configure(state="normal", text="Sign In")
        if self.on_success:
            self.on_success(data)
        self.destroy()

    def _on_auth_error(self, message: str):
        self._submit_btn.configure(
            state="normal",
            text="Sign In" if self._mode.get() == "login" else "Create Account",
        )
        self._error_var.set(message)

    def _forgot_password(self):
        # TODO: integrate forgot-password flow or open web
        webbrowser.open("https://iracing-advisor.com/forgot-password")


# ── Account Widget (shown in header when logged in) ───────────────────────

class AccountWidget(ctk.CTkFrame):
    """Small widget showing user tier badge + name + logout button.
    Placed in the app header next to the title.
    """

    def __init__(self, parent, on_logout: Optional[Callable] = None, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.on_logout = on_logout
        self._build()

    def _build(self):
        from core.license import license_state
        tier = license_state.tier
        name = license_state.display_name or license_state.email or "Account"

        TIER_COLORS = {"pro": "#9b59b6", "team": "#e67e22", "free": DIM}
        badge_color = TIER_COLORS.get(tier, DIM)

        lbl(self, name, 12).pack(side="left", padx=(0, 6))

        ctk.CTkLabel(
            self, text=tier.upper(), font=ctk.CTkFont(size=10, weight="bold"),
            fg_color=badge_color, text_color="white", corner_radius=4,
            width=0, height=18, padx=6,
        ).pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            self, text="Sign Out", width=70, height=24,
            fg_color="transparent", border_width=1, border_color=DIM,
            text_color=DIM, hover_color=PANEL, font=ctk.CTkFont(size=11),
            command=self._logout,
        ).pack(side="left")

    def refresh(self):
        for w in self.winfo_children():
            w.destroy()
        self._build()

    def _logout(self):
        from core.cloud_sync import logout
        logout()
        if self.on_logout:
            self.on_logout()
        self.refresh()


# ── Usage Panel (shown in Settings or a dedicated Cloud tab) ──────────────

class UsagePanel(ctk.CTkFrame):
    """Displays current usage vs limits with progress bars."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color=PANEL, corner_radius=8, **kwargs)
        self._loading = True
        self._build_loading()
        threading.Thread(target=self._load, daemon=True).start()

    def _build_loading(self):
        lbl(self, "Loading usage…", 12, color=DIM).pack(pady=20)

    def _load(self):
        try:
            from core.cloud_sync import get_usage
            data = get_usage()
            self.after(0, lambda: self._build_data(data))
        except Exception as exc:
            self.after(0, lambda: self._build_error(str(exc)))

    def _build_data(self, data: dict):
        for w in self.winfo_children():
            w.destroy()

        tier = data.get("tier", "free")
        limits = data.get("limits", {})

        lbl(self, "Cloud Usage", 14, bold=True).pack(anchor="w", padx=12, pady=(10, 6))
        lbl(self, f"Plan: {tier.upper()}", 12, color=DIM).pack(anchor="w", padx=12)

        def _bar(label: str, used: int, limit: int, unit: str = ""):
            row = ctk.CTkFrame(self, fg_color="transparent")
            row.pack(fill="x", padx=12, pady=3)
            pct = min(1.0, used / limit) if limit else 0
            limit_str = "∞" if limit == 0 else f"{limit}"
            lbl(row, f"{label}:", 11, color=DIM).pack(side="left")
            lbl(row, f"{used} / {limit_str}{unit}", 11).pack(side="right")
            bar = ctk.CTkProgressBar(self, height=6, progress_color=GREEN if pct < 0.8 else YELLOW if pct < 1.0 else RED)
            bar.pack(fill="x", padx=12, pady=(0, 4))
            bar.set(pct)

        _bar("Sessions this month", data.get("sessions_this_month", 0),
             limits.get("sessions_per_month", 10))
        _bar("AI calls today", data.get("ai_calls_today", 0),
             limits.get("ai_per_day", 5))

        storage_mb = data.get("storage_bytes", 0) / 1_048_576
        _bar("Storage", round(storage_mb, 1), limits.get("storage_mb", 512), " MB")

        if tier == "free":
            ctk.CTkButton(
                self, text="Upgrade to Pro →", height=32,
                fg_color=ACCENT, hover_color="#c0392b",
                command=lambda: webbrowser.open("https://iracing-advisor.com/billing"),
            ).pack(pady=(8, 12), padx=12, fill="x")
        else:
            ctk.CTkButton(
                self, text="Manage Subscription", height=28,
                fg_color="transparent", border_width=1,
                command=lambda: webbrowser.open("https://iracing-advisor.com/billing"),
            ).pack(pady=(8, 12), padx=12, fill="x")

    def _build_error(self, msg: str):
        for w in self.winfo_children():
            w.destroy()
        lbl(self, f"Could not load usage: {msg}", 11, color=DIM).pack(pady=20, padx=12)
