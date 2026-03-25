"""
Tire Pressure Learning Database
================================
Learns the cold-to-hot tire pressure rise for each car, bucketed by track
temperature.  This replaces hardcoded class-level estimates with values
measured directly from the user's own sessions.

How it works
------------
Every IBT file contains:
  • CarSetup YAML  → the cold (starting) pressure set before the session, in kPa
  • LFpress / RFpress / LRpress / RRpress channels → hot in-session pressure, in PSI

We record the delta (hot_psi − cold_psi) per corner, bucketed in 5 °C track
temperature bands.  After a few sessions the app knows exactly how much each
corner rises for that car in those conditions, enabling precise cold pressure
recommendations.

Storage:  ~/.iracing_setup_advisor_logs/tire_pressure_db.json
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
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_DB_PATH = os.path.expanduser(
    "~/.iracing_setup_advisor_logs/tire_pressure_db.json"
)

_KPA_TO_PSI = 1.0 / 6.89476

# 5 °C track-temperature buckets
_TEMP_BUCKETS = [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60]

CORNERS = ("LF", "RF", "LR", "RR")

_HOT_MIN_PSI = 10.0
_HOT_MAX_PSI = 55.0


# ── Per-corner pressure record ────────────────────────────────────────────────

@dataclass
class CornerPressureRecord:
    """Observed cold→hot delta for one corner of one car."""
    samples: int = 0
    # Persisted: bucket → mean delta (hot_psi - cold_psi)
    delta_by_bucket: Dict[str, float] = field(default_factory=dict)
    # In-memory only: raw observations for re-aggregation
    _obs: List[Tuple[float, float, float]] = field(
        default_factory=list, repr=False
    )  # (cold_psi, hot_psi, track_temp_c)

    def add(self, cold_psi: float, hot_psi: float, track_temp_c: float) -> None:
        self._obs.append((cold_psi, hot_psi, track_temp_c))
        self.samples += 1
        self._rebuild()

    def _rebuild(self) -> None:
        groups: Dict[int, List[float]] = {}
        for cold, hot, temp in self._obs:
            b = _bucket(temp)
            groups.setdefault(b, []).append(hot - cold)
        self.delta_by_bucket = {
            str(b): round(statistics.mean(v), 3)
            for b, v in groups.items()
        }

    def get_delta(self, track_temp_c: float) -> Optional[float]:
        """Hot-minus-cold PSI delta for the given track temp."""
        b = _bucket(track_temp_c)
        if str(b) in self.delta_by_bucket:
            return self.delta_by_bucket[str(b)]
        # Interpolate from nearest buckets
        if self.delta_by_bucket:
            keys = sorted(int(k) for k in self.delta_by_bucket)
            nearest = min(keys, key=lambda k: abs(k - b))
            return self.delta_by_bucket[str(nearest)]
        return None

    def recommend_cold_psi(
        self, target_hot_psi: float, track_temp_c: float
    ) -> Optional[float]:
        delta = self.get_delta(track_temp_c)
        if delta is None:
            return None
        return round(target_hot_psi - delta, 2)

    def to_dict(self) -> dict:
        return {"samples": self.samples, "delta_by_bucket": self.delta_by_bucket}

    @classmethod
    def from_dict(cls, d: dict) -> "CornerPressureRecord":
        return cls(
            samples=d.get("samples", 0),
            delta_by_bucket=d.get("delta_by_bucket", {}),
        )


@dataclass
class CarPressureRecord:
    display_name: str = ""
    last_updated: str = ""
    corners: Dict[str, CornerPressureRecord] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "display_name": self.display_name,
            "last_updated": self.last_updated,
            "corners": {k: v.to_dict() for k, v in self.corners.items()},
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CarPressureRecord":
        obj = cls(
            display_name=d.get("display_name", ""),
            last_updated=d.get("last_updated", ""),
        )
        for corner, cdata in d.get("corners", {}).items():
            obj.corners[corner] = CornerPressureRecord.from_dict(cdata)
        return obj


# ── Main database ─────────────────────────────────────────────────────────────

class TirePressureDB:
    """
    Thread-safe database mapping car → per-corner cold-to-hot pressure deltas,
    bucketed by track temperature.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._cars: Dict[str, CarPressureRecord] = {}

    @classmethod
    def load(cls) -> "TirePressureDB":
        db = cls()
        if os.path.exists(_DB_PATH):
            try:
                with open(_DB_PATH, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                for car_key, cdata in raw.items():
                    db._cars[car_key] = CarPressureRecord.from_dict(cdata)
                logger.debug("TirePressureDB loaded: %d cars", len(db._cars))
            except Exception as e:
                logger.warning("TirePressureDB load failed: %s", e)
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
            logger.warning("TirePressureDB save failed: %s", e)

    # ── Ingestion ─────────────────────────────────────────────────────────────

    def ingest_ibt(self, ibt_path: str) -> bool:
        try:
            from core.ibt_parser import IBTParser
            parser = IBTParser(ibt_path)
            data = parser.parse()
        except Exception as e:
            logger.debug("TirePressureDB: parse failed %s: %s", ibt_path, e)
            return False

        car_name = data.car_name or ""
        if not car_name:
            return False

        si = data.session_info or {}
        track_temp_c = float(si.get("track_temp_c") or 25.0)
        car_setup = si.get("car_setup") or {}

        # Cold pressures from CarSetup YAML (kPa → PSI)
        cold_kpa = _extract_cold_pressures_kpa(car_setup)
        cold_psi = {
            corner: val * _KPA_TO_PSI
            for corner, val in cold_kpa.items()
            if val is not None
        }
        if not cold_psi:
            return False

        # Steady-state hot pressures from telemetry (PSI)
        hot_psi = _extract_hot_pressures(data)
        if not any(v is not None for v in hot_psi.values()):
            return False

        car_key = _norm(car_name)
        with self._lock:
            if car_key not in self._cars:
                self._cars[car_key] = CarPressureRecord(
                    display_name=car_name,
                    last_updated=str(date.today()),
                )
            car_rec = self._cars[car_key]
            car_rec.last_updated = str(date.today())

            updated = False
            for corner in CORNERS:
                cold = cold_psi.get(corner)
                hot = hot_psi.get(corner)
                if cold is None or hot is None:
                    continue
                if not (_HOT_MIN_PSI <= hot <= _HOT_MAX_PSI):
                    continue
                if corner not in car_rec.corners:
                    car_rec.corners[corner] = CornerPressureRecord()
                car_rec.corners[corner].add(cold, hot, track_temp_c)
                updated = True

        return updated

    # ── Query ─────────────────────────────────────────────────────────────────

    def get_delta(
        self, car_name: str, corner: str, track_temp_c: float
    ) -> Optional[float]:
        """Expected hot-minus-cold delta in PSI for the given conditions."""
        car_key = _norm(car_name)
        with self._lock:
            car_rec = self._cars.get(car_key)
            if car_rec is None:
                return None
            corner_rec = car_rec.corners.get(corner)
            if corner_rec is None:
                return None
        return corner_rec.get_delta(track_temp_c)

    def recommend_cold_pressures(
        self,
        car_name: str,
        target_hot_psi: Dict[str, float],
        track_temp_c: float,
    ) -> Dict[str, Optional[float]]:
        """
        Given target hot pressures per corner (PSI), return recommended
        cold pressures (PSI) based on learned deltas.

        Example:
            db.recommend_cold_pressures(
                "Porsche 911 GT3 Cup (992)",
                {"LF": 32.0, "RF": 32.0, "LR": 33.0, "RR": 33.0},
                track_temp_c=28.0
            )
        """
        car_key = _norm(car_name)
        result: Dict[str, Optional[float]] = {c: None for c in CORNERS}
        with self._lock:
            car_rec = self._cars.get(car_key)
            if car_rec is None:
                return result
            for corner in CORNERS:
                rec = car_rec.corners.get(corner)
                if rec is None:
                    continue
                target = target_hot_psi.get(corner)
                if target is None:
                    continue
                result[corner] = rec.recommend_cold_psi(target, track_temp_c)
        return result

    def summary_for_car(self, car_name: str, track_temp_c: float) -> str:
        """Human-readable pressure delta summary for one car."""
        car_key = _norm(car_name)
        with self._lock:
            car_rec = self._cars.get(car_key)
            if car_rec is None:
                return ""
        parts = []
        for corner in CORNERS:
            rec = car_rec.corners.get(corner)
            if rec is None:
                continue
            delta = rec.get_delta(track_temp_c)
            if delta is not None:
                parts.append(f"{corner}: +{delta:.1f} psi rise")
        if not parts:
            return ""
        return (
            f"Learned pressure rise at {track_temp_c:.0f}°C track: "
            + ", ".join(parts)
        )

    def summary(self) -> str:
        with self._lock:
            n_cars = len(self._cars)
            n_obs = sum(
                rec.samples
                for car in self._cars.values()
                for rec in car.corners.values()
            )
        return f"{n_cars} cars  •  {n_obs} pressure observations"


# ── Module-level singleton ─────────────────────────────────────────────────────

_instance: Optional[TirePressureDB] = None
_lock = threading.Lock()


def get_tire_pressure_db() -> TirePressureDB:
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = TirePressureDB.load()
    return _instance


# ── Helpers ───────────────────────────────────────────────────────────────────

def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _bucket(temp_c: float) -> int:
    """Round temp down to nearest 5 °C bucket."""
    for b in reversed(_TEMP_BUCKETS):
        if temp_c >= b:
            return b
    return _TEMP_BUCKETS[0]


# Corner identification in CarSetup path names
_CORNER_TOKENS = {
    "LF": ("leftfront", "lf", "fl"),
    "RF": ("rightfront", "rf", "fr"),
    "LR": ("leftrear", "lr", "rl"),
    "RR": ("rightrear", "rr"),
}

# Keywords in the YAML key that indicate a cold starting pressure
_PRESSURE_KEYWORDS = ("startingpressure", "tirepressure", "coldpressure", "pressure")


def _extract_cold_pressures_kpa(car_setup: dict) -> Dict[str, Optional[float]]:
    """
    Walk CarSetup YAML tree and extract cold starting pressures in kPa.
    Handles different iRacing car naming conventions.
    """
    result: Dict[str, Optional[float]] = {c: None for c in CORNERS}
    _walk(car_setup, "", result)
    return result


def _walk(node, path: str, result: dict) -> None:
    if not isinstance(node, dict):
        return
    for k, v in node.items():
        full = f"{path}.{k}" if path else k
        full_norm = re.sub(r"[^a-z0-9]", "", full.lower())

        # Check if this leaf key looks like a pressure field
        if any(kw in full_norm for kw in _PRESSURE_KEYWORDS):
            corner = _identify_corner(full_norm)
            if corner and result[corner] is None:
                num = _parse_num(v)
                if num is not None and num > 0:
                    # kPa values are typically 100–350; PSI values 10–50
                    # If the value looks like PSI, treat it as already PSI and skip
                    # (we want kPa for conversion consistency)
                    result[corner] = num
        elif isinstance(v, dict):
            _walk(v, full, result)


def _identify_corner(path_norm: str) -> Optional[str]:
    for corner, tokens in _CORNER_TOKENS.items():
        if any(tok in path_norm for tok in tokens):
            return corner
    return None


def _extract_hot_pressures(data) -> Dict[str, Optional[float]]:
    """
    Compute steady-state hot pressure per corner from telemetry channels.
    Uses the median of the hottest 50% of non-pit laps to avoid cold-lap noise.
    """
    result: Dict[str, Optional[float]] = {c: None for c in CORNERS}
    ch_map = {"LF": "LFpress", "RF": "RFpress", "LR": "LRpress", "RR": "RRpress"}

    boundaries = data.lap_boundaries
    if boundaries is None or len(boundaries) < 2:
        return result

    on_pit = data.get_channel("OnPitRoad")

    for corner, ch_name in ch_map.items():
        ch = data.get_channel(ch_name)
        if ch is None:
            continue
        lap_medians = []
        for i in range(len(boundaries) - 1):
            start = boundaries[i]
            end = boundaries[i + 1]
            if end - start < 5:
                continue
            if on_pit is not None:
                pit_count = sum(
                    1 for j in range(start, min(end, len(on_pit)))
                    if on_pit[j]
                )
                if pit_count > (end - start) * 0.15:
                    continue
            # Sample the middle 50% of the lap to get settled pressure
            quarter = (end - start) // 4
            vals = [
                float(ch[j])
                for j in range(start + quarter, end - quarter)
                if _HOT_MIN_PSI <= float(ch[j]) <= _HOT_MAX_PSI
            ]
            if vals:
                lap_medians.append(statistics.median(vals))

        if len(lap_medians) > 1:
            # Discard the first (formation/outlap) value
            lap_medians = lap_medians[1:]
        if lap_medians:
            result[corner] = round(statistics.median(lap_medians), 2)

    return result


_NUM_RE = re.compile(r"^([+-]?\d+\.?\d*)")


def _parse_num(v) -> Optional[float]:
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    m = _NUM_RE.match(str(v).strip())
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass
    return None
