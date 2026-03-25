"""
Privacy & GDPR utilities.

  Art. 6/7  — Consent state management (stored in main config.json)
  Art. 13   — Transparency: first-launch notice via ui/privacy_consent.py
  Art. 17   — Right to Erasure: delete_all_user_data()
  Art. 20   — Data Portability: export_user_data()
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Dict

from core.config import APP_DATA_DIR, load_cfg, save_cfg

logger = logging.getLogger(__name__)

CONSENT_VERSION = "1.0"

# ── Personal data paths ───────────────────────────────────────────────────

_PROFILE_PATH       = os.path.expanduser("~/.iracing_engineer_profile.json")
_LICENSE_CACHE_PATH = os.path.expanduser("~/.iracing_setup_advisor_license.json")
_HISTORY_PATH       = os.path.expanduser("~/.iracing_setup_history.json")
_LOG_DIR            = os.path.join(APP_DATA_DIR, "logs")


def _db_paths() -> list[str]:
    """Paths of the five learning databases."""
    return [
        os.path.join(_LOG_DIR, "car_params_db.json"),
        os.path.join(_LOG_DIR, "fuel_db.json"),
        os.path.join(_LOG_DIR, "tire_pressure_db.json"),
        os.path.join(_LOG_DIR, "setup_perf_db.json"),
        os.path.join(_LOG_DIR, "shift_db.json"),
    ]


# ── Consent helpers ───────────────────────────────────────────────────────

def has_consent() -> bool:
    """Return True if the user has completed the privacy consent flow."""
    return bool(load_cfg().get("privacy_consent_given", False))


def learning_enabled() -> bool:
    """Return True if the user consented to learning database ingestion."""
    return bool(load_cfg().get("learning_data_enabled", True))


def profile_enabled() -> bool:
    """Return True if the user consented to driver profile accumulation."""
    return bool(load_cfg().get("driver_profile_enabled", True))


def record_consent(learning_data: bool = True, driver_profile: bool = True) -> None:
    """Persist the user's initial consent choices."""
    cfg = load_cfg()
    cfg["privacy_consent_given"]   = True
    cfg["privacy_consent_version"] = CONSENT_VERSION
    cfg["privacy_consent_date"]    = datetime.now(timezone.utc).isoformat()
    cfg["learning_data_enabled"]   = learning_data
    cfg["driver_profile_enabled"]  = driver_profile
    save_cfg(cfg)
    logger.info("Privacy consent recorded (version=%s)", CONSENT_VERSION)


def update_consent_preferences(learning_data: bool, driver_profile: bool) -> None:
    """Update the user's consent choices from the Settings dialog."""
    cfg = load_cfg()
    cfg["learning_data_enabled"]  = learning_data
    cfg["driver_profile_enabled"] = driver_profile
    save_cfg(cfg)
    logger.info("Consent preferences updated (learning=%s, profile=%s)",
                learning_data, driver_profile)


# ── Art. 17 — Right to Erasure ────────────────────────────────────────────

def delete_all_user_data() -> Dict[str, bool]:
    """
    Delete every personal data file held locally by the app.
    Returns a mapping of file path → True (deleted/absent) | False (failed).

    Also revokes cloud auth tokens from the OS keyring and resets the
    consent flag so the privacy notice is shown again on next launch.
    """
    results: Dict[str, bool] = {}

    targets = [_PROFILE_PATH, _LICENSE_CACHE_PATH, _HISTORY_PATH] + _db_paths()
    for path in targets:
        try:
            if os.path.exists(path):
                os.unlink(path)
            results[path] = True
            logger.info("Deleted personal data file: %s", path)
        except Exception as exc:
            logger.warning("Could not delete %s: %s", path, exc)
            results[path] = False

    # Revoke stored credentials from OS keyring
    try:
        import keyring
        for key in ("cloud_refresh_token", "iracing_email", "iracing_password"):
            try:
                keyring.delete_password("OptimalSector", key)
            except Exception:
                pass
    except Exception:
        pass

    # Reset consent so the privacy notice shows again on next launch
    cfg = load_cfg()
    for key in ("privacy_consent_given", "privacy_consent_version",
                "privacy_consent_date", "learning_data_enabled",
                "driver_profile_enabled"):
        cfg.pop(key, None)
    save_cfg(cfg)

    return results


# ── Art. 20 — Data Portability ────────────────────────────────────────────

def export_user_data(dest_path: str) -> str:
    """
    Write a structured JSON export of all personal data to *dest_path*.
    Returns the path written.
    """
    def _load_json(path: str):
        try:
            if os.path.exists(path):
                with open(path, encoding="utf-8") as f:
                    return json.load(f)
            return None
        except Exception as exc:
            return {"error": str(exc)}

    export: dict = {
        "export_time": datetime.now(timezone.utc).isoformat(),
        "app": "Optimal Sector",
        "note": (
            "This file contains all personal data held locally by Optimal Sector. "
            "Raw telemetry (IBT files) is never stored by the cloud service — "
            "all data below is local to this computer only."
        ),
        "driver_profile":   _load_json(_PROFILE_PATH),
        "session_history":  _load_json(_HISTORY_PATH),
    }

    # Account cache — strip tokens (they live in OS keyring, not on disk)
    raw_cache = _load_json(_LICENSE_CACHE_PATH)
    if isinstance(raw_cache, dict):
        export["account"] = {
            k: v for k, v in raw_cache.items()
            if k in ("user_id", "email", "display_name", "tier")
        }
    else:
        export["account"] = raw_cache

    db_names = ["car_params_db", "fuel_db", "tire_pressure_db",
                "setup_perf_db", "shift_db"]
    export["learning_databases"] = {
        name: _load_json(path)
        for name, path in zip(db_names, _db_paths())
    }

    dest_dir = os.path.dirname(dest_path)
    if dest_dir:
        os.makedirs(dest_dir, exist_ok=True)
    with open(dest_path, "w", encoding="utf-8") as f:
        json.dump(export, f, indent=2, ensure_ascii=False, default=str)

    logger.info("User data exported to %s", dest_path)
    return dest_path
