"""
Setup Performance Correlation Database
=======================================
Correlates car setup parameter values with median lap times across all of
the user's sessions.  Over many IBT files this reveals which parameter values
produce the fastest laps — for that specific car, at that specific track.

How it works
------------
For each IBT file loaded:
  1. Extract all numeric CarSetup parameters (via car_params_scanner._walk_setup)
  2. Compute the median of the session's clean lap times
  3. Record (param_value, median_lap_time, track) for every parameter

After enough sessions the database can answer:
  "For the Porsche 9922 Cup at Spa, rear wing angle 8 produced a median lap
   0.4s faster than wing angle 5 — based on 12 sessions."

Storage:  ~/.iracing_setup_advisor_logs/setup_perf_db.json
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
    "~/.iracing_setup_advisor_logs/setup_perf_db.json"
)

_MIN_LAPS = 3           # minimum laps for a session to count
_OUTLIER_FACTOR = 1.15  # exclude laps > 115% of session median
_MAX_OBS_PER_PARAM = 500  # cap stored observations to keep file size sane


# ── Per-parameter record ──────────────────────────────────────────────────────

@dataclass
class ParamPerfRecord:
    """
    Correlation data between one setup parameter value and lap time,
    for one car across all tracks (or filtered to one track).
    """
    samples: int = 0
    # Each entry: {"v": value, "t": median_lap_time, "track": track_key, "date": date}
    observations: List[dict] = field(default_factory=list)

    def add(self, value: float, median_lap_time: float, track_key: str) -> None:
        self.observations.append({
            "v":     round(value, 4),
            "t":     round(median_lap_time, 3),
            "track": track_key,
            "date":  str(date.today()),
        })
        self.samples = len(self.observations)

    def best_value(self, track_key: str = "") -> Optional[float]:
        """
        Return the parameter value associated with the lowest median lap time.
        Optionally filter to a specific track; falls back to all tracks.
        """
        obs = [o for o in self.observations if not track_key or o["track"] == track_key]
        if not obs:
            obs = self.observations
        if not obs:
            return None
        groups: Dict[float, List[float]] = {}
        for o in obs:
            groups.setdefault(o["v"], []).append(o["t"])
        return min(groups, key=lambda v: statistics.median(groups[v]))

    def correlation_summary(self, track_key: str = "") -> List[dict]:
        """
        Returns [{value, median_lap_time, samples}, ...] sorted by value.
        Only includes values seen at least twice.
        """
        obs = [o for o in self.observations if not track_key or o["track"] == track_key]
        if not obs:
            obs = self.observations
        groups: Dict[float, List[float]] = {}
        for o in obs:
            groups.setdefault(o["v"], []).append(o["t"])
        return sorted(
            [
                {
                    "value":           v,
                    "median_lap_time": round(statistics.median(times), 3),
                    "samples":         len(times),
                }
                for v, times in groups.items()
                if len(times) >= 2
            ],
            key=lambda x: x["value"],
        )

    def to_dict(self) -> dict:
        return {
            "samples":      self.samples,
            "observations": self.observations[-_MAX_OBS_PER_PARAM:],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ParamPerfRecord":
        obj = cls(samples=d.get("samples", 0))
        obj.observations = d.get("observations", [])
        return obj


@dataclass
class CarPerfRecord:
    display_name: str = ""
    last_updated: str = ""
    session_count: int = 0
    params: Dict[str, ParamPerfRecord] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "display_name":  self.display_name,
            "last_updated":  self.last_updated,
            "session_count": self.session_count,
            "params":        {k: v.to_dict() for k, v in self.params.items()},
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CarPerfRecord":
        obj = cls(
            display_name=d.get("display_name", ""),
            last_updated=d.get("last_updated", ""),
            session_count=d.get("session_count", 0),
        )
        for k, v in d.get("params", {}).items():
            obj.params[k] = ParamPerfRecord.from_dict(v)
        return obj


# ── Main database ─────────────────────────────────────────────────────────────

class SetupPerfDB:
    """
    Thread-safe database correlating setup parameter values with lap times,
    per car, learned from IBT telemetry.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._cars: Dict[str, CarPerfRecord] = {}

    @classmethod
    def load(cls) -> "SetupPerfDB":
        db = cls()
        if os.path.exists(_DB_PATH):
            try:
                with open(_DB_PATH, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                for car_key, cdata in raw.items():
                    db._cars[car_key] = CarPerfRecord.from_dict(cdata)
                logger.debug("SetupPerfDB loaded: %d cars", len(db._cars))
            except Exception as e:
                logger.warning("SetupPerfDB load failed: %s", e)
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
            logger.warning("SetupPerfDB save failed: %s", e)

    # ── Ingestion ─────────────────────────────────────────────────────────────

    def ingest_ibt(self, ibt_path: str) -> bool:
        try:
            from core.ibt_parser import IBTParser
            parser = IBTParser(ibt_path)
            data = parser.parse()
        except Exception as e:
            logger.debug("SetupPerfDB: parse failed %s: %s", ibt_path, e)
            return False

        car_name = data.car_name or ""
        track_name = data.track_name or ""
        if not car_name or not track_name:
            return False

        si = data.session_info or {}
        car_setup = si.get("car_setup") or {}
        if not car_setup:
            return False

        laps = _clean_lap_times(data)
        if len(laps) < _MIN_LAPS:
            return False

        median_time = statistics.median(laps)
        track_key = _norm(track_name)
        car_key = _norm(car_name)

        from core.car_params_scanner import _walk_setup
        params = _walk_setup(car_setup)
        if not params:
            return False

        with self._lock:
            if car_key not in self._cars:
                self._cars[car_key] = CarPerfRecord(
                    display_name=car_name,
                    last_updated=str(date.today()),
                )
            car_rec = self._cars[car_key]
            car_rec.last_updated = str(date.today())
            car_rec.session_count += 1

            for path, value, _unit in params:
                if path not in car_rec.params:
                    car_rec.params[path] = ParamPerfRecord()
                car_rec.params[path].add(value, median_time, track_key)

        return True

    # ── Query ─────────────────────────────────────────────────────────────────

    def get_best_value(
        self, car_name: str, param_path: str, track_name: str = ""
    ) -> Optional[float]:
        """Return the param value associated with the best (lowest) median lap time."""
        car_key = _norm(car_name)
        track_key = _norm(track_name)
        with self._lock:
            car_rec = self._cars.get(car_key)
            if car_rec is None:
                return None
            param_rec = car_rec.params.get(param_path)
            if param_rec is None:
                return None
        return param_rec.best_value(track_key)

    def get_correlation(
        self, car_name: str, param_path: str, track_name: str = ""
    ) -> Optional[List[dict]]:
        """Return [{value, median_lap_time, samples}, ...] or None."""
        car_key = _norm(car_name)
        track_key = _norm(track_name)
        with self._lock:
            car_rec = self._cars.get(car_key)
            if car_rec is None:
                return None
            param_rec = car_rec.params.get(param_path)
            if param_rec is None:
                return None
        return param_rec.correlation_summary(track_key)

    def top_correlated_params(
        self,
        car_name: str,
        track_name: str = "",
        top_n: int = 8,
        min_delta_s: float = 0.05,
    ) -> List[dict]:
        """
        Return the setup parameters with the strongest lap-time correlation
        for the given car (and optionally track).

        Returns list of:
            {param, best_value, delta_seconds, samples, breakdown}

        Sorted by delta_seconds descending (biggest impact first).
        """
        car_key = _norm(car_name)
        track_key = _norm(track_name)
        with self._lock:
            car_rec = self._cars.get(car_key)
            if car_rec is None:
                return []
            params_snapshot = {k: v for k, v in car_rec.params.items()}

        results = []
        for param_path, param_rec in params_snapshot.items():
            corr = param_rec.correlation_summary(track_key)
            if len(corr) < 2:
                continue
            times = [c["median_lap_time"] for c in corr]
            delta = max(times) - min(times)
            if delta < min_delta_s:
                continue
            best_val = param_rec.best_value(track_key)
            total_samples = sum(c["samples"] for c in corr)
            results.append({
                "param":          param_path,
                "best_value":     best_val,
                "delta_seconds":  round(delta, 3),
                "samples":        total_samples,
                "breakdown":      corr,
            })

        results.sort(key=lambda x: x["delta_seconds"], reverse=True)
        return results[:top_n]

    def format_for_prompt(
        self,
        car_name: str,
        track_name: str = "",
        top_n: int = 6,
    ) -> str:
        """
        Return a concise text block suitable for injection into the AI prompt,
        describing the highest-impact setup findings from historical data.
        """
        top = self.top_correlated_params(car_name, track_name, top_n=top_n)
        if not top:
            return ""

        scope = f"at {track_name}" if track_name else "across all tracks"
        lines = [
            f"Historical setup correlations for this car {scope} "
            f"(from real session data — higher delta = bigger lap time impact):"
        ]
        from core.analysis_engine import format_laptime
        for item in top:
            breakdown = item["breakdown"]
            best = item["best_value"]
            delta_ms = int(item["delta_seconds"] * 1000)
            param_short = item["param"].split(".")[-1]  # last segment e.g. "WingAngle"
            values_str = "  |  ".join(
                f"value {c['value']:g} → {format_laptime(c['median_lap_time'])} "
                f"({c['samples']} sess)"
                for c in breakdown
            )
            lines.append(
                f"  • {param_short}: best={best:g}  "
                f"Δ={delta_ms}ms spread  [{values_str}]"
            )
        return "\n".join(lines)

    def summary(self) -> str:
        with self._lock:
            n_cars = len(self._cars)
            n_sessions = sum(c.session_count for c in self._cars.values())
        return f"{n_cars} cars  •  {n_sessions} sessions correlated"


# ── Module-level singleton ─────────────────────────────────────────────────────

_instance: Optional[SetupPerfDB] = None
_lock = threading.Lock()


def get_setup_perf_db() -> SetupPerfDB:
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = SetupPerfDB.load()
    return _instance


# ── Helpers ───────────────────────────────────────────────────────────────────

def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _clean_lap_times(data) -> List[float]:
    """Return outlier-filtered lap times from a TelemetryData object."""
    if not data.laps:
        return []
    times = [
        lap.lap_time for lap in data.laps
        if lap.lap_time is not None and lap.lap_time > 10.0
    ]
    if not times:
        return []
    median = statistics.median(times)
    return [t for t in times if t <= median * _OUTLIER_FACTOR]
