"""
setup_learning_db.py — Setup recommendation outcome tracking.

When a driver applies a recommended setup change and drives again,
this module records whether the change helped, hurt, or was neutral.
Over time it calibrates the MAGNITUDE of deltas per car class.

Architecture:
  - SqliteDB (single JSON file — no external deps)
  - Per car-class delta magnitude adjustments
  - Confidence-weighted averaging
  - Exported to setup_generator for magnitude scaling

Usage:
    from core.setup_learning_db import get_learning_db
    db = get_learning_db()
    db.record_outcome(car='porsche_911_gt3_cup', track='watkins_glen',
                      param='arb_rear', delta=-1.0,
                      lap_delta_s=-0.312, driver_feel='better')
    scale = db.get_magnitude_scale('gt3', 'arb_rear')  # e.g. 1.4 = use 1.4x recommended magnitude
"""

from __future__ import annotations
import json, logging, os, threading
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_DB_PATH = Path.home() / '.optimalsector' / 'setup_learning.json'
_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

_MAX_OUTCOMES = 2000   # cap total entries
_MIN_SAMPLES  = 3      # need this many before magnitude scaling activates


@dataclass
class SetupOutcome:
    """One recorded outcome: a change was applied and the driver reported the result."""
    timestamp:    str
    car:          str
    track:        str
    car_class:    str
    param:        str           # e.g. 'arb_rear', 'camber_lf'
    delta:        float         # what we recommended: e.g. -1.0 (step)
    lap_delta_s:  float         # lap time change after applying: <0 = faster
    driver_feel:  str           # 'better' | 'neutral' | 'worse' | 'much_better' | 'much_worse'
    conditions:   dict = field(default_factory=dict)  # track_temp_c, air_temp_c, etc.
    confidence:   float = 1.0  # recommendation confidence at time of application
    notes:        str = ''


class SetupLearningDB:
    def __init__(self, path: Path = _DB_PATH):
        self._path    = path
        self._lock    = threading.Lock()
        self._outcomes: list[SetupOutcome] = []
        self._load()

    def _load(self):
        try:
            if self._path.exists():
                with open(self._path) as f:
                    data = json.load(f)
                self._outcomes = [SetupOutcome(**d) for d in data.get('outcomes', [])]
                logger.debug('SetupLearningDB: loaded %d outcomes', len(self._outcomes))
        except Exception as e:
            logger.warning('SetupLearningDB load failed: %s', e)
            self._outcomes = []

    def _save(self):
        try:
            with open(self._path, 'w') as f:
                json.dump({'outcomes': [asdict(o) for o in self._outcomes]},
                          f, indent=2)
        except Exception as e:
            logger.warning('SetupLearningDB save failed: %s', e)

    def record_outcome(self, car: str, track: str, car_class: str,
                       param: str, delta: float, lap_delta_s: float,
                       driver_feel: str, conditions: dict = None,
                       confidence: float = 1.0, notes: str = '') -> SetupOutcome:
        """
        Record that a setup change was applied and the lap delta observed.
        lap_delta_s < 0 means driver went faster (positive outcome).
        driver_feel: 'much_better' | 'better' | 'neutral' | 'worse' | 'much_worse'
        """
        outcome = SetupOutcome(
            timestamp=datetime.now().isoformat(),
            car=car.lower(), track=track.lower(),
            car_class=car_class.lower(),
            param=param, delta=delta,
            lap_delta_s=lap_delta_s,
            driver_feel=driver_feel,
            conditions=conditions or {},
            confidence=confidence, notes=notes,
        )
        with self._lock:
            self._outcomes.append(outcome)
            # Prune oldest if over cap
            if len(self._outcomes) > _MAX_OUTCOMES:
                self._outcomes = self._outcomes[-_MAX_OUTCOMES:]
            self._save()
        logger.info('SetupLearning: recorded %s %s%+.2f → %.3fs (%s)',
                    param, '+' if delta >= 0 else '', delta,
                    lap_delta_s, driver_feel)
        return outcome

    def get_outcomes(self, param: str = None, car_class: str = None,
                     car: str = None) -> list[SetupOutcome]:
        """Filter outcomes by param, class, or specific car."""
        with self._lock:
            results = self._outcomes[:]
        if param:
            results = [o for o in results if o.param == param]
        if car_class:
            results = [o for o in results if o.car_class == car_class.lower()]
        if car:
            results = [o for o in results if o.car == car.lower()]
        return results

    def get_magnitude_scale(self, car_class: str, param: str) -> float:
        """
        Return a magnitude scaling factor for a given param + car_class.
        1.0 = use recommended magnitude as-is.
        1.5 = recommended magnitude was consistently too small, scale up 50%.
        0.7 = recommended magnitude was too large, scale down 30%.

        Algorithm:
          - Take all outcomes for this class+param with the same delta direction
          - Compute weighted avg lap_delta_s (weight = confidence × |lap_delta_s|)
          - If outcomes suggest more change needed: scale > 1.0
          - If outcomes suggest less change needed: scale < 1.0
          - Returns 1.0 if insufficient data (< _MIN_SAMPLES)
        """
        outcomes = self.get_outcomes(param=param, car_class=car_class)
        if len(outcomes) < _MIN_SAMPLES:
            return 1.0

        # Feel scores: map driver_feel to numeric
        feel_map = {
            'much_better': 1.5, 'better': 1.0,
            'neutral': 0.0,
            'worse': -1.0, 'much_worse': -1.5,
        }

        total_weight = 0.0
        weighted_feel = 0.0
        for o in outcomes[-50:]:  # last 50 outcomes for this param/class
            feel_score = feel_map.get(o.driver_feel, 0.0)
            # Weight: recency (newer = higher weight) × confidence
            age_factor = 0.5 + 0.5 * (outcomes.index(o) / len(outcomes))
            w = o.confidence * age_factor * max(0.1, abs(feel_score))
            weighted_feel += feel_score * w
            total_weight  += w

        if total_weight < 0.1:
            return 1.0

        avg_feel = weighted_feel / total_weight
        # avg_feel > 0 → changes were positive → use same or more magnitude
        # avg_feel < 0 → changes hurt → scale down
        scale = 1.0 + (avg_feel * 0.3)  # max ±30% scaling from feel alone
        return max(0.5, min(2.0, round(scale, 2)))  # clamp 0.5–2.0

    def summary_for_param(self, param: str, car_class: str) -> str:
        """Human-readable summary for UI display."""
        outcomes = self.get_outcomes(param=param, car_class=car_class)
        if len(outcomes) < _MIN_SAMPLES:
            return f'No learning data yet ({len(outcomes)} recorded)'

        scale = self.get_magnitude_scale(car_class, param)
        feel_counts = {}
        for o in outcomes:
            feel_counts[o.driver_feel] = feel_counts.get(o.driver_feel, 0) + 1
        best = max(feel_counts, key=feel_counts.get)

        return (f'{len(outcomes)} outcomes recorded — '
                f'most common: {best.replace("_"," ")} — '
                f'magnitude scale: {scale:.1f}x')

    def total_outcomes(self) -> int:
        with self._lock:
            return len(self._outcomes)

    def clear(self):
        with self._lock:
            self._outcomes = []
            self._save()


_instance: Optional[SetupLearningDB] = None
_instance_lock = threading.Lock()


def get_learning_db() -> SetupLearningDB:
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = SetupLearningDB()
    return _instance
