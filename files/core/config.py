"""Configuration management: API key storage, config file I/O."""

import json, logging, os

logger = logging.getLogger(__name__)

# ── App data directory ─────────────────────────────────────────────────────
# Windows: %APPDATA%\OptimalSector\
# macOS/Linux: ~/.config/OptimalSector/
def _app_data_dir() -> str:
    if os.name == "nt":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(base, "OptimalSector")
    return os.path.join(os.path.expanduser("~"), ".config", "OptimalSector")

APP_DATA_DIR = _app_data_dir()
os.makedirs(APP_DATA_DIR, exist_ok=True)

CONFIG_FILE = os.path.join(APP_DATA_DIR, "config.json")
_LEGACY_CONFIG = os.path.expanduser("~/.iracing_setup_advisor.json")

_KEYRING_SERVICE = "OptimalSector"
_KEYRING_USER = "anthropic_api_key"


def _migrate_legacy_config():
    """One-time migration: move old ~/.iracing_setup_advisor.json to new location."""
    if os.path.exists(_LEGACY_CONFIG) and not os.path.exists(CONFIG_FILE):
        try:
            import shutil
            shutil.copy2(_LEGACY_CONFIG, CONFIG_FILE)
            logger.info("Migrated config from %s to %s", _LEGACY_CONFIG, CONFIG_FILE)
        except Exception as e:
            logger.warning("Could not migrate legacy config: %s", e)

_migrate_legacy_config()


def get_api_key() -> str:
    """Retrieve API key from OS credential store, falling back to config file."""
    try:
        import keyring
        key = keyring.get_password(_KEYRING_SERVICE, _KEYRING_USER)
        if key:
            return key
    except Exception:
        pass
    cfg = load_cfg()
    return cfg.get("api_key", "")


def set_api_key(key: str):
    """Store API key in OS credential store. Never stores in plaintext."""
    try:
        import keyring
        if key:
            keyring.set_password(_KEYRING_SERVICE, _KEYRING_USER, key)
        else:
            try:
                keyring.delete_password(_KEYRING_SERVICE, _KEYRING_USER)
            except Exception:
                pass
    except ImportError:
        logger.warning("keyring package not available — API key will NOT be saved.")
    except Exception as e:
        logger.warning("Failed to store API key in keyring: %s", e)


def load_cfg():
    try:
        # Try encrypted config first
        try:
            from core.privacy import decrypt_config
            cfg = decrypt_config()
            if cfg is not None:
                # Strip sensitive keys that should never be in config
                for _sk in ("api_key", "iracing_password", "subscription_key"):
                    cfg.pop(_sk, None)
                return cfg
        except Exception:
            pass
        # Fall back to plaintext
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                cfg = json.load(f)
            # Migrate legacy api_key from plaintext to keyring
            if cfg.get("api_key"):
                try:
                    import keyring
                    keyring.set_password(_KEYRING_SERVICE, _KEYRING_USER,
                                         cfg["api_key"])
                    cfg.pop("api_key", None)
                    save_cfg(cfg)
                except Exception:
                    pass
            else:
                cfg.pop("api_key", None)
            # Strip sensitive keys that should never be in the config file
            for _sk in ("iracing_password", "subscription_key"):
                cfg.pop(_sk, None)
            return cfg
    except (json.JSONDecodeError, IOError, OSError) as e:
        logger.warning("Could not load config: %s", e)
    return {"last_dir": ""}


def save_cfg(c):
    """
    Save config to disk — NEVER writes sensitive credentials.
    Attempts encrypted save (Fernet AES-128). Falls back to plaintext JSON.
    """
    try:
        _NEVER_SAVE = {"api_key", "iracing_password", "subscription_key"}
        to_save = {k: v for k, v in c.items() if k not in _NEVER_SAVE}
        # Try encrypted save first
        try:
            from core.privacy import encrypt_config
            if encrypt_config(to_save):
                return  # encrypted save succeeded
        except Exception:
            pass
        # Fallback to plaintext
        with open(CONFIG_FILE, "w") as f:
            json.dump(to_save, f)
    except (IOError, OSError) as e:
        logger.warning("Could not save config: %s", e)


# ── iRacing SSO credentials ───────────────────────────────────────────────

_KEYRING_IR_EMAIL = "iracing_email"
_KEYRING_IR_PASS  = "iracing_password"


def get_iracing_credentials() -> tuple[str, str]:
    """Return (email, password) from OS keyring, or ('', '') if not set."""
    try:
        import keyring
        email = keyring.get_password(_KEYRING_SERVICE, _KEYRING_IR_EMAIL) or ""
        pw    = keyring.get_password(_KEYRING_SERVICE, _KEYRING_IR_PASS)  or ""
        return email, pw
    except Exception:
        return "", ""


def set_iracing_credentials(email: str, password: str) -> None:
    """Store iRacing credentials in OS keyring. Never written to config file."""
    try:
        import keyring
        if email:
            keyring.set_password(_KEYRING_SERVICE, _KEYRING_IR_EMAIL, email)
        if password:
            keyring.set_password(_KEYRING_SERVICE, _KEYRING_IR_PASS, password)
    except Exception as e:
        logger.warning("Failed to store iRacing credentials: %s", e)


def clear_iracing_credentials() -> None:
    """Remove stored iRacing credentials from OS keyring."""
    try:
        import keyring
        for user in (_KEYRING_IR_EMAIL, _KEYRING_IR_PASS):
            try:
                keyring.delete_password(_KEYRING_SERVICE, user)
            except Exception:
                pass
    except Exception:
        pass


# ── Subscription / license key ────────────────────────────────────────────────

_KEYRING_SUB_KEY = "subscription_key"


def get_subscription_key() -> str:
    """Return subscription key from OS keyring."""
    try:
        import keyring
        return keyring.get_password(_KEYRING_SERVICE, _KEYRING_SUB_KEY) or ""
    except Exception:
        return ""


def set_subscription_key(key: str) -> None:
    """Store subscription key in OS keyring. Never written to config file."""
    try:
        import keyring
        if key and key.strip():
            keyring.set_password(_KEYRING_SERVICE, _KEYRING_SUB_KEY,
                                 key.strip())
        else:
            try:
                keyring.delete_password(_KEYRING_SERVICE, _KEYRING_SUB_KEY)
            except Exception:
                pass
    except Exception as e:
        logger.warning("Failed to store subscription key: %s", e)


def validate_subscription_key(key: str) -> bool:
    """
    Validate subscription key format.
    Valid format: 32+ alphanumeric chars, optionally hyphen-separated groups.
    Simple length check is NOT sufficient — this validates character set too.
    """
    import re as _re
    if not key or not isinstance(key, str):
        return False
    clean = key.strip().replace("-", "").replace("_", "")
    if len(clean) < 24:
        return False
    if not _re.match(r'^[A-Za-z0-9]+$', clean):
        return False
    # Must contain both letters and digits (not just all-letters or all-digits)
    return bool(_re.search(r'[A-Za-z]', clean) and _re.search(r'[0-9]', clean))


# ── Config file security ───────────────────────────────────────────────────────

_SENSITIVE_KEYS = {
    "api_key", "iracing_password", "subscription_key",
    "iracing_email",  # not secret but better in keyring
}


def sanitize_cfg_for_save(cfg: dict) -> dict:
    """
    Return a copy of cfg with sensitive keys removed.
    These are stored in OS keyring, not in the JSON config file.
    Call this before writing cfg to disk.
    """
    return {k: v for k, v in cfg.items() if k not in _SENSITIVE_KEYS}


def migrate_sensitive_keys_to_keyring(cfg: dict) -> dict:
    """
    One-time migration: move any sensitive values from cfg dict to keyring,
    then remove them from cfg. Returns cleaned cfg.
    Called on app startup if legacy values are found in config.
    """
    changed = False

    if cfg.get("iracing_password"):
        try:
            set_iracing_credentials(
                cfg.get("iracing_email", ""),
                cfg["iracing_password"])
            cfg.pop("iracing_password", None)
            cfg.pop("iracing_email", None)
            changed = True
            logger.info("Migrated iRacing credentials to OS keyring")
        except Exception as e:
            logger.warning("Credential migration failed: %s", e)

    if cfg.get("subscription_key"):
        try:
            set_subscription_key(cfg["subscription_key"])
            cfg.pop("subscription_key", None)
            changed = True
            logger.info("Migrated subscription key to OS keyring")
        except Exception as e:
            logger.warning("Subscription key migration failed: %s", e)

    if changed:
        save_cfg(cfg)

    return cfg
