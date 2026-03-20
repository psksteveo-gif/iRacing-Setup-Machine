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
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                cfg = json.load(f)
            if cfg.get("api_key"):
                try:
                    import keyring
                    keyring.set_password(_KEYRING_SERVICE, _KEYRING_USER, cfg["api_key"])
                    cfg.pop("api_key", None)
                    save_cfg(cfg)
                except Exception:
                    pass
            else:
                cfg.pop("api_key", None)
            return cfg
    except (json.JSONDecodeError, IOError, OSError) as e:
        logger.warning("Could not load config: %s", e)
    return {"last_dir": ""}


def save_cfg(c):
    try:
        to_save = {k: v for k, v in c.items() if k != "api_key"}
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
