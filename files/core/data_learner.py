"""
Data Learner — Unified IBT Ingestion
=====================================
Single entry point for updating every learning database whenever an IBT
telemetry file is loaded.  All work is done in a background thread so the
UI is never blocked.

Databases updated:
  • CarParamDB       — parameter names, units, observed ranges per car
  • FuelDB           — fuel burn per lap per car+track
  • TirePressureDB   — cold→hot pressure delta per car, by track temp
  • SetupPerfDB      — setup parameter correlation with lap times per car

Usage
-----
    from core.data_learner import ingest_all_on_load, scan_all_telemetry
    ingest_all_on_load(ibt_path)                      # fire-and-forget
    scan_all_telemetry(directory, progress_cb=cb)      # full folder scan
"""

from __future__ import annotations

import glob
import logging
import os
import threading
from typing import Callable, Dict, Optional

logger = logging.getLogger(__name__)


def ingest_all_on_load(ibt_path: str) -> None:
    """
    Called whenever an IBT file is loaded in the app.
    Updates all learning databases in the background — never blocks the UI.
    """
    def _worker():
        _ingest_one(ibt_path)

    threading.Thread(target=_worker, daemon=True).start()


def scan_all_telemetry(
    telemetry_dir: str,
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> Dict[str, int]:
    """
    Scan every .ibt file in *telemetry_dir*, updating all databases.
    *progress_cb(done, total)* is called after each file if provided.
    Returns counts: {"car_params": n, "fuel": n, "pressure": n, "perf": n}.
    """
    files = glob.glob(os.path.join(telemetry_dir, "*.ibt"))
    total = len(files)
    counts = {"car_params": 0, "fuel": 0, "pressure": 0, "perf": 0}

    for i, path in enumerate(files):
        updated = _ingest_one(path)
        for key in counts:
            if updated.get(key):
                counts[key] += 1
        if progress_cb:
            try:
                progress_cb(i + 1, total)
            except Exception:
                pass

    # Persist all databases after the full scan
    _save_all()
    return counts


def _ingest_one(ibt_path: str) -> Dict[str, bool]:
    """Ingest one IBT file into all databases. Returns which DBs were updated."""
    updated: Dict[str, bool] = {
        "car_params": False,
        "fuel":       False,
        "pressure":   False,
        "perf":       False,
    }
    try:
        from core.car_params_scanner import get_db
        if get_db().ingest_ibt(ibt_path):
            get_db().save()
            updated["car_params"] = True
    except Exception as e:
        logger.debug("data_learner car_params failed %s: %s", ibt_path, e)

    try:
        from core.fuel_db import get_fuel_db
        if get_fuel_db().ingest_ibt(ibt_path):
            get_fuel_db().save()
            updated["fuel"] = True
    except Exception as e:
        logger.debug("data_learner fuel failed %s: %s", ibt_path, e)

    try:
        from core.tire_pressure_db import get_tire_pressure_db
        if get_tire_pressure_db().ingest_ibt(ibt_path):
            get_tire_pressure_db().save()
            updated["pressure"] = True
    except Exception as e:
        logger.debug("data_learner pressure failed %s: %s", ibt_path, e)

    try:
        from core.setup_performance_db import get_setup_perf_db
        if get_setup_perf_db().ingest_ibt(ibt_path):
            get_setup_perf_db().save()
            updated["perf"] = True
    except Exception as e:
        logger.debug("data_learner perf failed %s: %s", ibt_path, e)

    try:
        from core.shift_db import get_shift_db
        if get_shift_db().ingest_ibt(ibt_path):
            get_shift_db().save()
            updated["shifts"] = True
    except Exception as e:
        logger.debug("data_learner shifts failed %s: %s", ibt_path, e)

    return updated


def _save_all() -> None:
    """Persist all databases — called once after a full directory scan."""
    for name, loader in [
        ("car_params",  lambda: __import__("core.car_params_scanner", fromlist=["get_db"]).get_db()),
        ("fuel",        lambda: __import__("core.fuel_db",            fromlist=["get_fuel_db"]).get_fuel_db()),
        ("pressure",    lambda: __import__("core.tire_pressure_db",   fromlist=["get_tire_pressure_db"]).get_tire_pressure_db()),
        ("perf",        lambda: __import__("core.setup_performance_db", fromlist=["get_setup_perf_db"]).get_setup_perf_db()),
        ("shifts",      lambda: __import__("core.shift_db",           fromlist=["get_shift_db"]).get_shift_db()),
    ]:
        try:
            loader().save()
        except Exception as e:
            logger.debug("data_learner save_all %s: %s", name, e)


def all_summaries() -> Dict[str, str]:
    """Return summary strings from all learning databases."""
    result = {}
    try:
        from core.car_params_scanner import get_db
        result["car_params"] = get_db().summary()
    except Exception:
        result["car_params"] = "unavailable"
    try:
        from core.fuel_db import get_fuel_db
        result["fuel"] = get_fuel_db().summary()
    except Exception:
        result["fuel"] = "unavailable"
    try:
        from core.tire_pressure_db import get_tire_pressure_db
        result["pressure"] = get_tire_pressure_db().summary()
    except Exception:
        result["pressure"] = "unavailable"
    try:
        from core.setup_performance_db import get_setup_perf_db
        result["perf"] = get_setup_perf_db().summary()
    except Exception:
        result["perf"] = "unavailable"
    try:
        from core.shift_db import get_shift_db
        result["shifts"] = get_shift_db().summary()
    except Exception:
        result["shifts"] = "unavailable"
    return result
