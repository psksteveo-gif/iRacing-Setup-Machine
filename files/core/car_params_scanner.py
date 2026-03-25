"""
Car Parameter Scanner
=====================
Scans the user's iRacing telemetry (.ibt) files and builds a per-car parameter
database containing every setup parameter's name, unit, and observed value range
directly from iRacing's own data.

Why this matters
----------------
iRacing embeds a full CarSetup YAML block in every IBT telemetry file — with
the EXACT same parameter names, section hierarchy, and units as the garage UI.
By scanning every session the user has driven, we learn:
  • Which parameters exist for each specific car (not just its class)
  • The real units iRacing uses (kPa not psi; deg not "step"; etc.)
  • The realistic value range actually used (and thus legal)

The database is stored in ~/.iracing_setup_advisor_logs/car_params_db.json
and is automatically updated whenever a new IBT file is loaded.

Usage
-----
    from core.car_params_scanner import CarParamDB
    db = CarParamDB.load()
    bounds = db.get_bounds("porsche9922cup", "Chassis.Rear.WingAngle")
    # → {"unit": "", "obs_min": 0.0, "obs_max": 12.0, "typical": 6.0, "samples": 105}
"""

from __future__ import annotations

import json
import logging
import os
import re
import statistics
import threading
from dataclasses import dataclass, field, asdict
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_DB_PATH = os.path.expanduser(
    "~/.iracing_setup_advisor_logs/car_params_db.json"
)

# Parameters that are read-only telemetry, not garage adjustables.
# We skip these so the database only contains things you can actually change.
_SKIP_PATHS = {
    "UpdateCount",
    "LeftFront.LastHotPressure",
    "LeftRear.LastHotPressure",
    "RightFront.LastHotPressure",
    "RightRear.LastHotPressure",
    "LeftFront.LastTempsOMI",
    "LeftFront.LastTempsIMO",
    "LeftRear.LastTempsOMI",
    "LeftRear.LastTempsIMO",
    "RightFront.LastTempsOMI",
    "RightFront.LastTempsIMO",
    "RightRear.LastTempsOMI",
    "RightRear.LastTempsIMO",
    "LeftFront.TreadRemaining",
    "LeftRear.TreadRemaining",
    "RightFront.TreadRemaining",
    "RightRear.TreadRemaining",
    "LeftFront.CornerWeight",
    "LeftRear.CornerWeight",
    "RightFront.CornerWeight",
    "RightRear.CornerWeight",
    "LeftFront.FrontWeight",
    "AeroBalanceCalc.FrontRhAtSpeed",
    "AeroBalanceCalc.RearRhAtSpeed",
    "AeroBalanceCalc.FrontDownforce",
    "FuelLowWarning",
}

# Suffix tokens that make a path non-adjustable (e.g. brake pad mu values)
_SKIP_SUFFIXES = ("BrakePadMu", "FrictionFaces", "GearStack")


@dataclass
class ParamRecord:
    """Observed data for one parameter of one car."""
    unit: str = ""
    obs_min: float = 0.0
    obs_max: float = 0.0
    typical: float = 0.0      # median of observed values
    samples: int = 0
    # Raw sample list kept only in memory; not persisted (too large).
    _values: List[float] = field(default_factory=list, repr=False)

    def update(self, value: float) -> None:
        self._values.append(value)
        self.samples = len(self._values)
        self.obs_min = min(self._values)
        self.obs_max = max(self._values)
        self.typical = statistics.median(self._values)

    def to_dict(self) -> dict:
        return {
            "unit":     self.unit,
            "obs_min":  self.obs_min,
            "obs_max":  self.obs_max,
            "typical":  self.typical,
            "samples":  self.samples,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ParamRecord":
        return cls(
            unit=d.get("unit", ""),
            obs_min=d.get("obs_min", 0.0),
            obs_max=d.get("obs_max", 0.0),
            typical=d.get("typical", 0.0),
            samples=d.get("samples", 0),
        )


@dataclass
class CarRecord:
    """All observed parameters for one car."""
    display_name: str = ""
    sample_count: int = 0
    last_updated: str = ""
    params: Dict[str, ParamRecord] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "display_name":  self.display_name,
            "sample_count":  self.sample_count,
            "last_updated":  self.last_updated,
            "params":        {k: v.to_dict() for k, v in self.params.items()},
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CarRecord":
        rec = cls(
            display_name=d.get("display_name", ""),
            sample_count=d.get("sample_count", 0),
            last_updated=d.get("last_updated", ""),
        )
        for k, v in d.get("params", {}).items():
            rec.params[k] = ParamRecord.from_dict(v)
        return rec


class CarParamDB:
    """
    Thread-safe, file-backed database of per-car setup parameters learned from
    iRacing telemetry files.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._cars: Dict[str, CarRecord] = {}

    # ── Persistence ───────────────────────────────────────────────────────────

    @classmethod
    def load(cls) -> "CarParamDB":
        """Load the database from disk; return empty DB if file missing."""
        db = cls()
        if os.path.exists(_DB_PATH):
            try:
                with open(_DB_PATH, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                for car_key, car_data in raw.items():
                    db._cars[car_key] = CarRecord.from_dict(car_data)
                logger.debug("CarParamDB loaded: %d cars from %s",
                             len(db._cars), _DB_PATH)
            except Exception as e:
                logger.warning("CarParamDB load failed (%s): %s", _DB_PATH, e)
        return db

    def save(self) -> None:
        """Persist the database to disk."""
        os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
        with self._lock:
            data = {k: v.to_dict() for k, v in self._cars.items()}
        try:
            tmp = _DB_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp, _DB_PATH)
            logger.debug("CarParamDB saved: %d cars", len(data))
        except Exception as e:
            logger.warning("CarParamDB save failed: %s", e)

    # ── Ingestion ─────────────────────────────────────────────────────────────

    def ingest_ibt(self, ibt_path: str) -> bool:
        """
        Parse one IBT file and merge its CarSetup into the database.
        Returns True if setup data was found and ingested.
        """
        try:
            from core.ibt_parser import IBTParser
            parser = IBTParser(ibt_path)
            data = parser.parse()
        except Exception as e:
            logger.debug("CarParamDB: failed to parse %s: %s", ibt_path, e)
            return False

        car_key = _normalise_car_key(data.car_name or "")
        if not car_key:
            return False

        si = data.session_info or {}
        car_setup = si.get("car_setup")
        if not car_setup:
            return False

        params = _walk_setup(car_setup)
        if not params:
            return False

        with self._lock:
            if car_key not in self._cars:
                self._cars[car_key] = CarRecord(
                    display_name=data.car_name or car_key,
                    last_updated=str(date.today()),
                )
            car_rec = self._cars[car_key]
            car_rec.sample_count += 1
            car_rec.last_updated = str(date.today())

            for path, value, unit in params:
                if path not in car_rec.params:
                    car_rec.params[path] = ParamRecord(unit=unit)
                car_rec.params[path].update(value)

        return True

    def scan_directory(
        self,
        telemetry_dir: str,
        progress_cb=None,
    ) -> Dict[str, int]:
        """
        Scan all .ibt files in *telemetry_dir*.
        *progress_cb(done, total)* is called after each file if provided.
        Returns a dict {car_key: sessions_added}.
        """
        import glob
        files = glob.glob(os.path.join(telemetry_dir, "*.ibt"))
        total = len(files)
        added: Dict[str, int] = {}

        for i, path in enumerate(files):
            car_key_before = set(self._cars.keys())
            ok = self.ingest_ibt(path)
            if ok:
                # Figure out which car was updated
                car_key = _normalise_car_key(
                    _filename_to_car(os.path.basename(path))
                )
                added[car_key] = added.get(car_key, 0) + 1
            if progress_cb:
                try:
                    progress_cb(i + 1, total)
                except Exception:
                    pass

        self.save()
        return added

    # ── Query ─────────────────────────────────────────────────────────────────

    def get_bounds(
        self,
        car_key: str,
        param_path: str,
    ) -> Optional[dict]:
        """
        Return observed bounds for a specific parameter of a specific car,
        or None if no data available.

        Returns dict with keys: unit, obs_min, obs_max, typical, samples.
        """
        car_key = _normalise_car_key(car_key)
        with self._lock:
            car_rec = self._cars.get(car_key)
            if car_rec is None:
                return None
            rec = car_rec.params.get(param_path)
            if rec is None:
                return None
            return rec.to_dict()

    def get_car_params(self, car_key: str) -> Optional[Dict[str, dict]]:
        """Return all parameter records for a car, keyed by param path."""
        car_key = _normalise_car_key(car_key)
        with self._lock:
            car_rec = self._cars.get(car_key)
            if car_rec is None:
                return None
            return {k: v.to_dict() for k, v in car_rec.params.items()}

    def known_cars(self) -> List[str]:
        with self._lock:
            return list(self._cars.keys())

    def summary(self) -> str:
        """One-line summary for display."""
        with self._lock:
            total_params = sum(len(c.params) for c in self._cars.values())
            total_sessions = sum(c.sample_count for c in self._cars.values())
        return (
            f"{len(self._cars)} cars  •  "
            f"{total_sessions} sessions  •  "
            f"{total_params} parameters learned"
        )


# ── Module-level singleton ─────────────────────────────────────────────────────

_db_instance: Optional[CarParamDB] = None
_db_lock = threading.Lock()


def get_db() -> CarParamDB:
    """Return the global CarParamDB instance, loading from disk on first call."""
    global _db_instance
    if _db_instance is None:
        with _db_lock:
            if _db_instance is None:
                _db_instance = CarParamDB.load()
    return _db_instance


def ingest_on_load(ibt_path: str) -> None:
    """
    Called whenever an IBT file is loaded in the app.
    Updates the database in the background — never blocks the UI.
    """
    import threading

    def _worker():
        db = get_db()
        updated = db.ingest_ibt(ibt_path)
        if updated:
            db.save()

    threading.Thread(target=_worker, daemon=True).start()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _normalise_car_key(name: str) -> str:
    """Convert any car name form to a consistent lowercase key."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _filename_to_car(filename: str) -> str:
    """Extract car name from iRacing IBT filename (car_track_date.ibt)."""
    base = os.path.splitext(filename)[0]
    # iRacing format: <car>_<track> <date> <time>
    # Car name ends at the first underscore before a space-containing segment
    parts = base.split("_")
    # Heuristic: car name is everything before the first part containing a space
    car_parts = []
    for p in parts:
        if " " in p:
            break
        car_parts.append(p)
    return "_".join(car_parts)


_NUM_RE = re.compile(r"^([+-]?\d+\.?\d*(?:\.\d+)?)\s*([a-zA-Z%°]*)")


def _parse_value(v: Any) -> Tuple[Optional[float], str]:
    """
    Parse an iRacing setup value into (float, unit).
    Handles: int, float, "159 kPa", "-4.4 deg", "+9 clicks", "4 (ABS)", etc.
    Returns (None, '') if the value is non-numeric (e.g. "Dry", "FIA").
    """
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v), ""
    s = str(v).strip()
    m = _NUM_RE.match(s)
    if m:
        try:
            return float(m.group(1)), m.group(2).strip()
        except ValueError:
            pass
    return None, ""


def _walk_setup(
    node: Any,
    path: str = "",
    results: Optional[List] = None,
) -> List[Tuple[str, float, str]]:
    """
    Recursively walk a CarSetup dict and collect (path, numeric_value, unit).
    Skips non-adjustable / read-only entries.
    """
    if results is None:
        results = []
    if not isinstance(node, dict):
        return results

    for key, val in node.items():
        full_path = f"{path}.{key}" if path else key

        # Skip read-only / derived paths
        if any(full_path.endswith(s) or full_path == s for s in _SKIP_PATHS):
            continue
        if any(full_path.endswith(s) for s in _SKIP_SUFFIXES):
            continue

        if isinstance(val, dict):
            _walk_setup(val, full_path, results)
        else:
            num, unit = _parse_value(val)
            if num is not None:
                results.append((full_path, num, unit))

    return results
