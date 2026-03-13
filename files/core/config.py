"""Configuration management: API key storage, config file I/O."""

import json, logging, os

logger = logging.getLogger(__name__)

CONFIG_FILE = os.path.expanduser("~/.iracing_setup_advisor.json")
_KEYRING_SERVICE = "iracing_setup_advisor"
_KEYRING_USER = "anthropic_api_key"


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
