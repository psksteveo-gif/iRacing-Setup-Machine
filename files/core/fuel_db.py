"""
Fuel Burn Database
==================
Learns exact per-lap fuel consumption for every car + track combination
directly from the user's iRacing IBT telemetry files.

Why this matters
----------------
iRacing's FuelLevel channel gives an exact fuel reading every sample.
By measuring the drop between lap boundaries we get per-lap burn with no
estimation.  Over many sessions this produces a tight, car-specific number
rather than the generic class-level average used as a fallback.

The database is stored at:
    ~/.iracing_setup_advisor_logs/fuel_db.json

Usage
-----
    from core.fuel_db import get_fuel_db
    rec = get_fuel_db().get("Porsche 911 GT3 Cup (992)", "Spa-Francorchamps")
    # → FuelRecord(avg_l_per_lap=2.83, samples=47, ...)
"""

from __future__ import annotations

import json
import logging
import os
import re
import statistics
import threading
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_DB_PATH = os.path.expanduser(
    "~/.iracing_setup_advisor_logs/fuel_db.json"
)

# Sanity bounds — ignore laps with suspiciously low or high fuel burn
# (catches outlaps, inlaps, safety car laps)
_MIN_BURN_L = 0.3
_MAX_BURN_L = 12.0


@dataclass
class FuelRecord:
    """Observed fuel consumption for one car + track combination."""
    car_name: str = ""
    track_name: str = ""
    samples: int = 0            # total valid laps observed
    avg_l_per_lap: float = 0.0
    min_l_per_lap: float = 0.0
    max_l_per_lap: float = 0.0
    last_updated: str = ""
    _values: List[float] = field(default_factory=list, repr=False)

    def add(self, burn_l: float) -> None:
        self._values.append(burn_l)
        self.samples = len(self._values)
        self.avg_l_per_lap = round(statistics.mean(self._values), 4)
        self.min_l_per_lap = round(min(self._values), 4)
        self.max_l_per_lap = round(max(self._values), 4)

    def to_dict(self) -> dict:
        return {
            "car_name":       self.car_name,
            "track_name":     self.track_name,
            "samples":        self.samples,
            "avg_l_per_lap":  self.avg_l_per_lap,
            "min_l_per_lap":  self.min_l_per_lap,
            "max_l_per_lap":  self.max_l_per_lap,
            "last_updated":   self.last_updated,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "FuelRecord":
        return cls(
            car_name=d.get("car_name", ""),
            track_name=d.get("track_name", ""),
            samples=d.get("samples", 0),
            avg_l_per_lap=d.get("avg_l_per_lap", 0.0),
            min_l_per_lap=d.get("min_l_per_lap", 0.0),
            max_l_per_lap=d.get("max_l_per_lap", 0.0),
            last_updated=d.get("last_updated", ""),
        )


class FuelDB:
    """Thread-safe, file-backed database of fuel consumption per car+track."""

    def __init__(self):
        self._lock = threading.Lock()
        self._records: Dict[str, FuelRecord] = {}   # key: "car_norm|track_norm"

    # ── Persistence ───────────────────────────────────────────────────────────

    @classmethod
    def load(cls) -> "FuelDB":
        db = cls()
        if os.path.exists(_DB_PATH):
            try:
                with open(_DB_PATH, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                for key, data in raw.items():
                    db._records[key] = FuelRecord.from_dict(data)
                logger.debug("FuelDB loaded: %d combos", len(db._records))
            except Exception as e:
                logger.warning("FuelDB load failed: %s", e)
        return db

    def save(self) -> None:
        os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
        with self._lock:
            data = {k: v.to_dict() for k, v in self._records.items()}
        try:
            tmp = _DB_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp, _DB_PATH)
        except Exception as e:
            logger.warning("FuelDB save failed: %s", e)

    # ── Ingestion ─────────────────────────────────────────────────────────────

    def ingest_ibt(self, ibt_path: str) -> bool:
        """
        Parse one IBT file and add its per-lap fuel burns to the database.
        Returns True if at least one valid lap was recorded.
        """
        try:
            from core.ibt_parser import IBTParser
            parser = IBTParser(ibt_path)
            data = parser.parse()
        except Exception as e:
            logger.debug("FuelDB: parse failed %s: %s", ibt_path, e)
            return False

        car_name = data.car_name or ""
        track_name = data.track_name or ""
        if not car_name or not track_name:
            return False

        fuel = data.get_channel("FuelLevel")
        boundaries = data.lap_boundaries
        if fuel is None or boundaries is None or len(boundaries) < 2:
            return False

        on_pit = data.get_channel("OnPitRoad")
        burns = []
        for i in range(len(boundaries) - 1):
            start = boundaries[i]
            end = boundaries[i + 1] - 1
            if end <= start or end >= len(fuel):
                continue
            # Skip laps that spent significant time on pit road
            if on_pit is not None:
                pit_samples = sum(
                    1 for j in range(start, min(end + 1, len(on_pit)))
                    if on_pit[j]
                )
                if pit_samples > (end - start) * 0.15:
                    continue
            burn = float(fuel[start]) - float(fuel[end])
            if _MIN_BURN_L <= burn <= _MAX_BURN_L:
                burns.append(burn)

        if not burns:
            return False

        key = f"{_norm(car_name)}|{_norm(track_name)}"
        with self._lock:
            if key not in self._records:
                self._records[key] = FuelRecord(
                    car_name=car_name,
                    track_name=track_name,
                    last_updated=str(date.today()),
                )
            rec = self._records[key]
            for b in burns:
                rec.add(b)
            rec.last_updated = str(date.today())

        return True

    # ── Query ─────────────────────────────────────────────────────────────────

    def get(self, car_name: str, track_name: str) -> Optional[FuelRecord]:
        """Return fuel record for a specific car + track, or None."""
        key = f"{_norm(car_name)}|{_norm(track_name)}"
        with self._lock:
            return self._records.get(key)

    def summary(self) -> str:
        with self._lock:
            combos = len(self._records)
            total_laps = sum(r.samples for r in self._records.values())
        return f"{combos} car/track combos  •  {total_laps} laps of fuel data"


# ── Module-level singleton ─────────────────────────────────────────────────────

_instance: Optional[FuelDB] = None
_lock = threading.Lock()


def get_fuel_db() -> FuelDB:
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = FuelDB.load()
    return _instance


# ── Helpers ───────────────────────────────────────────────────────────────────

def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())
