"""
License / entitlement checking for the desktop app.

When the user is logged into the cloud backend their tier is cached locally
so the app works offline. Features are gated via has_feature() throughout
the UI; upgrade prompts are shown via require_feature().
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

_KEYRING_SERVICE = "OptimalSector"
_KEYRING_REFRESH_TOKEN = "cloud_refresh_token"


def _keyring_set(value: str) -> bool:
    try:
        import keyring
        keyring.set_password(_KEYRING_SERVICE, _KEYRING_REFRESH_TOKEN, value)
        return True
    except Exception as exc:
        logger.warning("Could not store refresh token in keyring: %s", exc)
        return False


def _keyring_get() -> Optional[str]:
    try:
        import keyring
        return keyring.get_password(_KEYRING_SERVICE, _KEYRING_REFRESH_TOKEN)
    except Exception as exc:
        logger.warning("Could not read refresh token from keyring: %s", exc)
        return None


def _keyring_delete() -> None:
    try:
        import keyring
        keyring.delete_password(_KEYRING_SERVICE, _KEYRING_REFRESH_TOKEN)
    except Exception:
        pass

# ── Tier feature matrix (mirrors backend/config.py) ───────────────────────

TIER_FEATURES: dict[str, set[str]] = {
    "free": {
        "telemetry_basic",
        "setup_analysis",
        "lap_delta",
        "track_map",
    },
    "pro": {
        "telemetry_basic", "telemetry_advanced",
        "setup_analysis",  "setup_diff",
        "lap_delta",       "track_map",
        "pdf_export",      "csv_export",
        "ai_advisor",      "session_history",
        "consistency_score", "ml_prediction",
        "reference_lap",   "stint_analysis",
    },
    "team": {
        "telemetry_basic", "telemetry_advanced",
        "setup_analysis",  "setup_diff",
        "lap_delta",       "track_map",
        "pdf_export",      "csv_export",
        "ai_advisor",      "session_history",
        "consistency_score", "ml_prediction",
        "reference_lap",   "stint_analysis",
        "teams",           "coach_view",
    },
}

# Upgrade CTA messages shown in the UI
UPGRADE_MESSAGES: dict[str, str] = {
    "telemetry_advanced": "Advanced telemetry overlays require Pro. Upgrade to unlock multi-lap comparison, CDEFS charts, and delta panels.",
    "setup_diff":       "Setup diff visualization requires Pro. Upgrade to compare setups side-by-side.",
    "pdf_export":       "PDF export requires Pro. Upgrade to generate shareable session reports.",
    "csv_export":       "CSV export requires Pro. Upgrade to export channel data for external analysis.",
    "ai_advisor":       "Optimal Sector requires Pro. Upgrade to get Claude-powered setup recommendations.",
    "session_history":  "Session history & trends require Pro. Upgrade to track your pace over time.",
    "consistency_score":"Consistency scoring requires Pro.",
    "ml_prediction":    "ML lap time prediction requires Pro.",
    "reference_lap":    "Reference lap comparison requires Pro.",
    "stint_analysis":   "Stint analysis requires Pro.",
    "teams":            "Team features require a Team subscription.",
    "coach_view":       "Coach view requires a Team subscription.",
}


# ── License state ─────────────────────────────────────────────────────────

class LicenseState:
    def __init__(self):
        self.user_id: Optional[str] = None
        self.email: Optional[str] = None
        self.display_name: Optional[str] = None
        self.tier: str = "free"
        self.is_authenticated: bool = False
        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.token_expires_at: Optional[datetime] = None
        self._cache_path = os.path.expanduser("~/.iracing_setup_advisor_license.json")

    # ── Auth state ────────────────────────────────────────────────────

    def login(self, user_id: str, email: str, tier: str,
              access_token: str, refresh_token: str,
              display_name: Optional[str] = None) -> None:
        self.user_id = user_id
        self.email = email
        self.display_name = display_name
        self.tier = tier
        self.is_authenticated = True
        self.access_token = access_token
        self.refresh_token = refresh_token
        _keyring_set(refresh_token)
        self._save_cache()
        logger.info("Logged in as %s (tier=%s)", email, tier)

    def logout(self) -> None:
        self.user_id = None
        self.email = None
        self.display_name = None
        self.tier = "free"
        self.is_authenticated = False
        self.access_token = None
        self.refresh_token = None
        _keyring_delete()
        self._delete_cache()
        logger.info("Logged out")

    def update_tier(self, tier: str) -> None:
        self.tier = tier
        self._save_cache()

    # ── Feature checks ────────────────────────────────────────────────

    def has_feature(self, feature: str) -> bool:
        """Return True if current tier includes the feature."""
        return feature in TIER_FEATURES.get(self.tier, set())

    def require_feature(self, feature: str, parent_widget=None) -> bool:
        """Return True if licensed. If not, show upgrade prompt. Returns False to abort."""
        if self.has_feature(feature):
            return True
        msg = UPGRADE_MESSAGES.get(feature, f"'{feature}' requires a higher subscription tier.")
        _show_upgrade_prompt(msg, parent_widget)
        return False

    # ── Cache (persist login across restarts) ────────────────────────

    def _save_cache(self) -> None:
        try:
            data = {
                "user_id": self.user_id,
                "email": self.email,
                "display_name": self.display_name,
                "tier": self.tier,
                # refresh_token is stored in OS keyring, not here
            }
            with open(self._cache_path, "w", encoding="utf-8") as f:
                json.dump(data, f)
        except Exception as exc:
            logger.warning("Could not save license cache: %s", exc)

    def _delete_cache(self) -> None:
        try:
            if os.path.exists(self._cache_path):
                os.unlink(self._cache_path)
        except Exception:
            pass

    def load_cache(self) -> bool:
        """Try to restore login state from disk. Returns True if cache found."""
        try:
            if not os.path.exists(self._cache_path):
                return False
            with open(self._cache_path, encoding="utf-8") as f:
                data = json.load(f)
            self.user_id = data.get("user_id")
            self.email = data.get("email")
            self.display_name = data.get("display_name")
            self.tier = data.get("tier", "free")
            # Migrate plaintext token from old cache files if present
            legacy_token = data.pop("refresh_token", None)
            if legacy_token:
                _keyring_set(legacy_token)
                # Rewrite cache without the token
                try:
                    with open(self._cache_path, "w", encoding="utf-8") as f:
                        json.dump(data, f)
                except Exception:
                    pass
            self.refresh_token = _keyring_get()
            self.is_authenticated = bool(self.user_id and self.refresh_token)
            return self.is_authenticated
        except Exception as exc:
            logger.warning("Could not load license cache: %s", exc)
            return False


# ── Singleton ─────────────────────────────────────────────────────────────

license_state = LicenseState()


# ── Convenience helpers ───────────────────────────────────────────────────

def has_feature(feature: str) -> bool:
    return license_state.has_feature(feature)


def require_feature(feature: str, parent=None) -> bool:
    return license_state.require_feature(feature, parent)


def is_pro_or_team() -> bool:
    return license_state.tier in ("pro", "team")


def current_tier() -> str:
    return license_state.tier


def is_logged_in() -> bool:
    return license_state.is_authenticated


# ── Upgrade prompt (CTk or fallback) ─────────────────────────────────────

def _show_upgrade_prompt(message: str, parent=None) -> None:
    try:
        import customtkinter as ctk

        def _build():
            dlg = ctk.CTkToplevel(parent)
            dlg.title("Upgrade Required")
            dlg.geometry("480x200")
            dlg.resizable(False, False)
            dlg.grab_set()

            ctk.CTkLabel(dlg, text="Feature Not Available",
                         font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(20, 6))
            ctk.CTkLabel(dlg, text=message, wraplength=440, justify="center",
                         font=ctk.CTkFont(size=12)).pack(padx=20)

            btn_row = ctk.CTkFrame(dlg, fg_color="transparent")
            btn_row.pack(pady=16)
            ctk.CTkButton(btn_row, text="Upgrade Now", width=140,
                          command=lambda: [_open_upgrade(), dlg.destroy()]).pack(side="left", padx=8)
            ctk.CTkButton(btn_row, text="Not Now", width=100,
                          fg_color="transparent", border_width=1,
                          command=dlg.destroy).pack(side="left", padx=8)

        if parent:
            parent.after(0, _build)
        else:
            _build()
    except Exception:
        # Fallback — log only (no CTk available in background threads)
        logger.info("Feature locked: %s", message)


def _open_upgrade() -> None:
    import webbrowser
    webbrowser.open("https://iracing-advisor.com/billing")
