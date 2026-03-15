"""
IBT Parse Result Cache

Caches parsed TelemetryData objects keyed on (absolute path, file size, mtime)
so that reloading the same file is near-instant.

Cache lives in: ~/.iracing_setup_advisor_logs/ibt_cache/
Entries are evicted after 30 days or when the cache exceeds 200 MB.
"""

import os
import pickle
import hashlib
import logging
import time
from typing import Optional

from core.ibt_parser import TelemetryData

logger = logging.getLogger(__name__)

_CACHE_DIR = os.path.expanduser("~/.iracing_setup_advisor_logs/ibt_cache")
_MAX_AGE_DAYS = 30
_MAX_CACHE_MB = 200


def _cache_key(path: str) -> str:
    """Generate a stable 20-char hex key from file identity (path + size + mtime)."""
    try:
        stat = os.stat(path)
        raw = f"{os.path.abspath(path)}|{stat.st_size}|{stat.st_mtime_ns}".encode()
        return hashlib.sha256(raw).hexdigest()[:20]
    except OSError:
        return ""


def _cache_path(key: str) -> str:
    os.makedirs(_CACHE_DIR, exist_ok=True)
    return os.path.join(_CACHE_DIR, f"{key}.pkl")


def load_cached(path: str) -> Optional[TelemetryData]:
    """Return cached TelemetryData if the cache entry is valid, else None."""
    key = _cache_key(path)
    if not key:
        return None
    cp = _cache_path(key)
    if not os.path.exists(cp):
        return None
    try:
        with open(cp, "rb") as f:
            data = pickle.load(f)
        logger.info("IBT cache hit: %s", os.path.basename(path))
        return data
    except Exception as exc:
        logger.debug("IBT cache miss (corrupt entry removed): %s", exc)
        try:
            os.remove(cp)
        except OSError:
            pass
        return None


def save_cached(path: str, data: TelemetryData) -> None:
    """Persist parsed TelemetryData to disk cache."""
    key = _cache_key(path)
    if not key:
        return
    cp = _cache_path(key)
    try:
        with open(cp, "wb") as f:
            pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)
        logger.debug("IBT cache saved: %s", os.path.basename(path))
    except Exception as exc:
        logger.warning("Failed to save IBT cache: %s", exc)


def evict_old_entries() -> int:
    """
    Remove cache entries older than _MAX_AGE_DAYS and trim to _MAX_CACHE_MB.
    Returns the number of files removed.
    """
    if not os.path.isdir(_CACHE_DIR):
        return 0

    cutoff = time.time() - _MAX_AGE_DAYS * 86400
    entries: list[tuple[float, int, str]] = []
    total_bytes = 0

    for fn in os.listdir(_CACHE_DIR):
        if not fn.endswith(".pkl"):
            continue
        fp = os.path.join(_CACHE_DIR, fn)
        try:
            stat = os.stat(fp)
            entries.append((stat.st_mtime, stat.st_size, fp))
            total_bytes += stat.st_size
        except OSError:
            continue

    removed = 0

    # Pass 1: remove by age
    for mtime, sz, fp in entries:
        if mtime < cutoff:
            try:
                os.remove(fp)
                removed += 1
                total_bytes -= sz
            except OSError:
                pass

    # Pass 2: trim by total size (remove oldest first)
    max_bytes = _MAX_CACHE_MB * 1024 * 1024
    if total_bytes > max_bytes:
        remaining = [(m, s, p) for m, s, p in entries if os.path.exists(p)]
        remaining.sort()  # oldest first
        for _, sz, fp in remaining:
            if total_bytes <= max_bytes:
                break
            try:
                os.remove(fp)
                removed += 1
                total_bytes -= sz
            except OSError:
                pass

    if removed:
        logger.info("IBT cache: evicted %d stale/oversized entries", removed)
    return removed
