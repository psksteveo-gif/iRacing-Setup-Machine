"""
First-launch GDPR consent dialog (Art. 13).

Call show_consent_dialog(parent) before revealing the main window.
Returns True if the user accepted, False if they declined (caller should quit).
"""
from __future__ import annotations
import customtkinter as ctk
from ui.theme import DARK, PANEL, CARD, ACCENT, BLUE, TEXT, DIM


def show_consent_dialog(parent: ctk.CTk) -> bool:
    """
    Show the privacy consent dialog modally.
    Blocks until the user clicks Accept or Decline.
    Returns True if accepted.
    """
    result: list[bool] = [False]

    win = ctk.CTkToplevel(parent)
    win.title("Privacy Notice — Optimal Sector")
    win.geometry("520x570")
    win.configure(fg_color=DARK)
    win.resizable(False, False)
    win.grab_set()
    win.protocol("WM_DELETE_WINDOW", lambda: None)  # force explicit choice
    win.lift()
    win.focus_force()

    # ── Header ────────────────────────────────────────────────────────────
    ctk.CTkLabel(win, text="Privacy Notice",
                 font=ctk.CTkFont(size=18, weight='bold'),
                 text_color=TEXT).pack(pady=(22, 2))
    ctk.CTkLabel(win, text="Please review how Optimal Sector uses your data.",
                 font=ctk.CTkFont(size=11),
                 text_color=DIM).pack()

    # ── Scrollable body ───────────────────────────────────────────────────
    sc = ctk.CTkScrollableFrame(win, fg_color="transparent", height=260)
    sc.pack(fill='both', expand=True, padx=24, pady=(10, 4))

    def _section(title: str, body: str) -> None:
        ctk.CTkLabel(sc, text=title,
                     font=ctk.CTkFont(size=12, weight='bold'),
                     text_color=BLUE, anchor='w').pack(anchor='w', pady=(10, 2))
        ctk.CTkLabel(sc, text=body,
                     font=ctk.CTkFont(size=11),
                     text_color=TEXT, wraplength=450,
                     justify='left', anchor='w').pack(anchor='w', padx=4)

    _section(
        "What we store locally",
        "• Telemetry analysis results and session history\n"
        "• Driver profile built from your race data\n"
        "• Anthropic API key (OS keyring only — never written to disk)\n"
        "• App preferences (theme, units, recent files, etc.)",
    )

    _section(
        "Optional: Learning Databases",
        "Optimal Sector can learn from your telemetry to improve fuel, "
        "tire pressure, and setup recommendations.  All data is kept "
        "on this computer only — nothing is uploaded.",
    )

    _section(
        "Optional: Driver Profile",
        "A cumulative profile is built across your sessions to personalise "
        "coaching tips from your AI race engineer.  This data never leaves "
        "your computer.",
    )

    _section(
        "Your rights (GDPR Art. 17 & 20)",
        "You can export a copy of all your data, or permanently delete it, "
        "at any time from Settings → Privacy.",
    )

    # ── Separator ─────────────────────────────────────────────────────────
    ctk.CTkFrame(win, fg_color=CARD, height=1).pack(fill='x', padx=24, pady=(8, 6))

    # ── Opt-in checkboxes ─────────────────────────────────────────────────
    learning_var = ctk.BooleanVar(value=True)
    profile_var  = ctk.BooleanVar(value=True)

    ctk.CTkCheckBox(win,
                    text="Enable learning databases  (fuel, tire, setup — local only)",
                    variable=learning_var, fg_color=ACCENT, hover_color=BLUE,
                    font=ctk.CTkFont(size=11)).pack(anchor='w', padx=28, pady=(2, 3))

    ctk.CTkCheckBox(win,
                    text="Enable driver profile accumulation  (local only)",
                    variable=profile_var, fg_color=ACCENT, hover_color=BLUE,
                    font=ctk.CTkFont(size=11)).pack(anchor='w', padx=28, pady=(0, 4))

    ctk.CTkLabel(win,
                 text="You can change these choices at any time in Settings.",
                 font=ctk.CTkFont(size=9), text_color=DIM).pack()

    # ── Buttons ───────────────────────────────────────────────────────────
    br = ctk.CTkFrame(win, fg_color="transparent")
    br.pack(fill='x', padx=24, pady=(10, 18))

    def _accept() -> None:
        from core.privacy import record_consent
        record_consent(
            learning_data=learning_var.get(),
            driver_profile=profile_var.get(),
        )
        result[0] = True
        win.destroy()

    def _decline() -> None:
        result[0] = False
        win.destroy()

    ctk.CTkButton(br, text="Accept & Continue", width=160, height=34,
                  fg_color=ACCENT, hover_color="#a03010",
                  command=_accept).pack(side='right', padx=4)
    ctk.CTkButton(br, text="Decline & Quit", width=130, height=34,
                  fg_color=CARD, hover_color="#3a1a2a",
                  command=_decline).pack(side='right', padx=4)

    parent.wait_window(win)
    return result[0]
