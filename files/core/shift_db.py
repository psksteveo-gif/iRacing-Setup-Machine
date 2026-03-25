"""
Shift Point Learning Database
==============================
Learns optimal upshift RPM per gear for each car by comparing the upshift RPM
used on the session's fastest laps vs slower laps.

After several sessions the database can say:
  "In the Porsche 9922 Cup, your fastest laps shifted 3rd→4th at 7 820 RPM.
   In slower laps you averaged 7 340 RPM — 480 RPM early."

Storage:  ~/.iracing_setup_advisor_logs/shift_db.json
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

import numpy as np

logger = logging.getLogger(__name__)

_DB_PATH = os.path.expanduser(
    "~/.iracing_setup_advisor_logs/shift_db.json"
)

_MIN_UPSHIFTS = 3       # minimum upshifts per gear per session to record
_FAST_LAP_PCT = 0.30    # top 30% of laps by time → "fast laps"
_OUTLIER_FACTOR = 1.10


@dataclass
class GearShiftRecord:
    """Observed upshift data for one gear transition of one car."""
    gear_from: int = 0
    gear_to: int = 0
    samples: int = 0          # total upshift observations
    # Stored as separate fast/slow lists to keep JSON size down
    fast_rpms: List[float] = field(default_factory=list)   # from fastest laps
    all_rpms: List[float] = field(default_factory=list)    # from all laps

    @property
    def optimal_rpm(self) -> Optional[float]:
        """Median RPM at upshift on fastest laps."""
        if not self.fast_rpms:
            return statistics.median(self.all_rpms) if self.all_rpms else None
        return statistics.median(self.fast_rpms)

    @property
    def typical_rpm(self) -> Optional[float]:
        return statistics.median(self.all_rpms) if self.all_rpms else None

    @property
    def delta_rpm(self) -> Optional[float]:
        """Fast minus typical: positive = shift later on fast laps (usually better)."""
        opt = self.optimal_rpm
        typ = self.typical_rpm
        if opt is None or typ is None:
            return None
        return round(opt - typ, 0)

    def add(self, rpms_fast: List[float], rpms_all: List[float]) -> None:
        self.fast_rpms.extend(rpms_fast)
        self.all_rpms.extend(rpms_all)
        # Cap to 2 000 observations to keep memory bounded
        self.fast_rpms = self.fast_rpms[-2000:]
        self.all_rpms  = self.all_rpms[-2000:]
        self.samples   = len(self.all_rpms)

    def to_dict(self) -> dict:
        return {
            "gear_from":  self.gear_from,
            "gear_to":    self.gear_to,
            "samples":    self.samples,
            "fast_rpms":  [round(r, 0) for r in self.fast_rpms[-500:]],
            "all_rpms":   [round(r, 0) for r in self.all_rpms[-500:]],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "GearShiftRecord":
        obj = cls(
            gear_from=d.get("gear_from", 0),
            gear_to=d.get("gear_to", 0),
            samples=d.get("samples", 0),
        )
        obj.fast_rpms = d.get("fast_rpms", [])
        obj.all_rpms  = d.get("all_rpms", [])
        return obj


@dataclass
class CarShiftRecord:
    display_name: str = ""
    last_updated: str = ""
    max_rpm: float = 0.0          # learned max RPM for this car
    gears: Dict[str, GearShiftRecord] = field(default_factory=dict)  # key: "3→4"

    def to_dict(self) -> dict:
        return {
            "display_name": self.display_name,
            "last_updated": self.last_updated,
            "max_rpm":      self.max_rpm,
            "gears":        {k: v.to_dict() for k, v in self.gears.items()},
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CarShiftRecord":
        obj = cls(
            display_name=d.get("display_name", ""),
            last_updated=d.get("last_updated", ""),
            max_rpm=d.get("max_rpm", 0.0),
        )
        for k, v in d.get("gears", {}).items():
            obj.gears[k] = GearShiftRecord.from_dict(v)
        return obj


class ShiftDB:
    """
    Thread-safe database of per-car, per-gear optimal upshift RPM values,
    learned from the user's own IBT telemetry files.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._cars: Dict[str, CarShiftRecord] = {}

    @classmethod
    def load(cls) -> "ShiftDB":
        db = cls()
        if os.path.exists(_DB_PATH):
            try:
                with open(_DB_PATH, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                for car_key, cdata in raw.items():
                    db._cars[car_key] = CarShiftRecord.from_dict(cdata)
                logger.debug("ShiftDB loaded: %d cars", len(db._cars))
            except Exception as e:
                logger.warning("ShiftDB load failed: %s", e)
        return db

    def save(self) -> None:
        os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
        with self._lock:
            data = {k: v.to_dict() for k, v in self._cars.items()}
        try:
            tmp = _DB_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp, _DB_PATH)
        except Exception as e:
            logger.warning("ShiftDB save failed: %s", e)

    # ── Ingestion ─────────────────────────────────────────────────────────────

    def ingest_ibt(self, ibt_path: str) -> bool:
        try:
            from core.ibt_parser import IBTParser
            parser = IBTParser(ibt_path)
            data = parser.parse()
        except Exception as e:
            logger.debug("ShiftDB: parse failed %s: %s", ibt_path, e)
            return False

        car_name = data.car_name or ""
        if not car_name:
            return False

        rpm_ch  = data.get_channel("RPM")
        gear_ch = data.get_channel("Gear")
        if rpm_ch is None or gear_ch is None or len(rpm_ch) < 100:
            return False

        rpm_arr  = np.array(rpm_ch,  dtype=float)
        gear_arr = np.array(gear_ch, dtype=float)

        max_rpm = float(np.percentile(rpm_arr[rpm_arr > 0], 99.5)) if np.any(rpm_arr > 0) else 0.0
        if max_rpm < 100:
            return False

        # Identify fast vs all laps
        boundaries = data.lap_boundaries
        lap_times  = data.lap_times
        if boundaries is None or not lap_times or len(boundaries) < 2:
            return False

        # Clean lap times to determine fast-lap threshold
        clean_times = [t for t in lap_times if t and t > 10.0]
        if not clean_times:
            return False
        median_time = statistics.median(clean_times)
        fast_threshold = median_time * (1.0 - _FAST_LAP_PCT * 0.5)  # within top 30%
        fast_lap_indices = {
            i for i, t in enumerate(lap_times)
            if t and t <= median_time * (1 + _FAST_LAP_PCT * 0.3)
               and t <= fast_threshold * 1.05
        }
        # Simpler: mark laps in the fastest 30% as "fast"
        sorted_times = sorted(t for t in clean_times)
        fast_cutoff = sorted_times[max(0, int(len(sorted_times) * _FAST_LAP_PCT))]
        fast_lap_set = {i for i, t in enumerate(lap_times) if t and t <= fast_cutoff}

        # Detect upshifts per lap
        gear_diff = np.diff(gear_arr)
        upshift_idx = np.where(gear_diff == 1)[0]

        # Group upshift RPMs by gear transition, split by fast/slow laps
        all_upshifts: Dict[str, List[float]] = {}
        fast_upshifts: Dict[str, List[float]] = {}

        for idx in upshift_idx:
            g_from = int(gear_arr[idx])
            g_to   = int(gear_arr[idx + 1])
            if g_from < 1 or g_to < 1 or g_to != g_from + 1:
                continue
            key = f"{g_from}→{g_to}"
            rpm_val = float(rpm_arr[idx])
            if rpm_val < 100:
                continue

            # Determine which lap this belongs to
            lap_num = None
            for li in range(len(boundaries) - 1):
                if boundaries[li] <= idx < boundaries[li + 1]:
                    lap_num = li
                    break

            all_upshifts.setdefault(key, []).append(rpm_val)
            if lap_num is not None and lap_num in fast_lap_set:
                fast_upshifts.setdefault(key, []).append(rpm_val)

        updated_any = False
        car_key = _norm(car_name)
        with self._lock:
            if car_key not in self._cars:
                self._cars[car_key] = CarShiftRecord(
                    display_name=car_name,
                    last_updated=str(date.today()),
                )
            car_rec = self._cars[car_key]
            car_rec.last_updated = str(date.today())
            # Update max RPM (keep highest seen)
            if max_rpm > car_rec.max_rpm:
                car_rec.max_rpm = round(max_rpm, 0)

            for key, all_rpms in all_upshifts.items():
                if len(all_rpms) < _MIN_UPSHIFTS:
                    continue
                fast_rpms = fast_upshifts.get(key, [])
                g_parts = key.split("→")
                if len(g_parts) != 2:
                    continue
                if key not in car_rec.gears:
                    car_rec.gears[key] = GearShiftRecord(
                        gear_from=int(g_parts[0]),
                        gear_to=int(g_parts[1]),
                    )
                car_rec.gears[key].add(fast_rpms, all_rpms)
                updated_any = True

        return updated_any

    # ── Query ─────────────────────────────────────────────────────────────────

    def get_optimal_shifts(self, car_name: str) -> Optional[Dict[str, dict]]:
        """
        Return dict of gear transition → {optimal_rpm, typical_rpm, delta_rpm, samples}.
        Returns None if no data.
        """
        car_key = _norm(car_name)
        with self._lock:
            car_rec = self._cars.get(car_key)
            if car_rec is None:
                return None
            result = {}
            for key, rec in car_rec.gears.items():
                opt = rec.optimal_rpm
                if opt is None:
                    continue
                result[key] = {
                    "optimal_rpm": round(opt, 0),
                    "typical_rpm": round(rec.typical_rpm or opt, 0),
                    "delta_rpm":   rec.delta_rpm or 0.0,
                    "samples":     rec.samples,
                    "max_rpm_pct": round(opt / car_rec.max_rpm * 100, 1) if car_rec.max_rpm > 0 else 0.0,
                }
        return result or None

    def format_for_prompt(self, car_name: str) -> str:
        """Compact text block for AI prompt injection."""
        shifts = self.get_optimal_shifts(car_name)
        if not shifts:
            return ""
        lines = [f"Learned optimal shift points for {car_name} (from fastest laps):"]
        for gear_key in sorted(shifts.keys()):
            s = shifts[gear_key]
            delta_str = ""
            if abs(s["delta_rpm"]) > 100:
                direction = "later" if s["delta_rpm"] > 0 else "earlier"
                delta_str = f"  ← fast laps shift {abs(s['delta_rpm']):.0f} RPM {direction} than average"
            lines.append(
                f"  Gear {gear_key}: optimal {s['optimal_rpm']:.0f} RPM "
                f"({s['max_rpm_pct']:.0f}% of max)  "
                f"typical {s['typical_rpm']:.0f} RPM  "
                f"[{s['samples']} obs]{delta_str}"
            )
        return "\n".join(lines)

    def summary(self) -> str:
        with self._lock:
            n_cars = len(self._cars)
            n_obs  = sum(
                rec.samples
                for car in self._cars.values()
                for rec in car.gears.values()
            )
        return f"{n_cars} cars  •  {n_obs} shift observations"


# ── Module-level singleton ─────────────────────────────────────────────────────

_instance: Optional[ShiftDB] = None
_lock = threading.Lock()


def get_shift_db() -> ShiftDB:
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = ShiftDB.load()
    return _instance


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())
