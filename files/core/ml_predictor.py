"""
ML Lap Time Predictor

Trains a Ridge Regression on past sessions to predict the achievable
lap time under current conditions/setup. No external ML library required —
implemented with NumPy least-squares.

Requires at least 3 loaded sessions for meaningful predictions.
"""

import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional, Dict


# ── Feature / result types ────────────────────────────────────────────────────

@dataclass
class SessionFeatures:
    """Extracted feature vector for a single session."""
    balance_score: float = 0.0
    avg_tire_temp: float = 0.0
    temp_spread: float = 0.0       # max – min avg tire temp across corners
    air_temp_c: float = 25.0
    track_temp_c: float = 35.0
    fuel_per_lap: float = 0.0
    best_lap_s: float = 0.0        # target variable
    session_label: str = ""


@dataclass
class PredictionResult:
    predicted_lap_s: float
    delta_vs_actual: float          # predicted - actual best (s); negative = model says you can go faster
    confidence: float               # 0–1
    feature_importance: Dict[str, float]   # normalised absolute weights
    n_sessions: int
    residual_std: float             # training residual std (s)
    insight: str                    # human-readable take


_FEATURE_NAMES = [
    'balance_score', 'avg_tire_temp', 'temp_spread',
    'air_temp_c', 'track_temp_c', 'fuel_per_lap',
]


# ── Predictor ────────────────────────────────────────────────────────────────

class LapTimePredictor:
    """
    Incremental Ridge Regression lap time predictor.

    Usage::

        pred = LapTimePredictor()
        feats = [pred.extract(data, report) for data, report in sessions]
        feats = [f for f in feats if f is not None]
        pred.train(feats)
        result = pred.predict(feats[-1])
    """

    def __init__(self):
        self._w: Optional[np.ndarray] = None
        self._x_mean: Optional[np.ndarray] = None
        self._x_std: Optional[np.ndarray] = None
        self._y_mean: float = 0.0
        self._residual_std: float = 0.0
        self._n: int = 0

    @property
    def is_trained(self) -> bool:
        return self._w is not None and self._n >= 3

    # ── Feature extraction ────────────────────────────────────────────────────

    def extract(self, data, report) -> Optional[SessionFeatures]:
        """
        Extract a SessionFeatures vector from a (TelemetryData, AnalysisReport) pair.
        Returns None if data is insufficient.
        """
        if data is None or report is None or report.best_lap <= 0:
            return None

        si = data.session_info

        # Tire temps — use summary averages
        avg_temp = 0.0
        spread = 0.0
        if report.tire_summary:
            avgs = [v['avg'] for v in report.tire_summary.values() if 'avg' in v]
            if avgs:
                avg_temp = float(np.mean(avgs))
                spread = float(max(avgs) - min(avgs))

        # Fuel use per lap
        fuel_ch = data.get_channel('FuelLevel')
        fuel_per_lap = 0.0
        if fuel_ch is not None and data.num_laps > 1 and len(fuel_ch) > 1:
            fuel_per_lap = float((fuel_ch[0] - fuel_ch[-1]) / data.num_laps)

        return SessionFeatures(
            balance_score=float(report.balance_score),
            avg_tire_temp=avg_temp,
            temp_spread=spread,
            air_temp_c=float(si.get('air_temp_c', 25.0)),
            track_temp_c=float(si.get('track_temp_c', 35.0)),
            fuel_per_lap=fuel_per_lap,
            best_lap_s=float(report.best_lap),
            session_label=f"{data.car_name} @ {data.track_name}",
        )

    # ── Training ──────────────────────────────────────────────────────────────

    def train(self, sessions: List[SessionFeatures], alpha: float = 0.5):
        """
        Fit Ridge Regression on a list of session features.

        Parameters
        ----------
        sessions : list of SessionFeatures (need ≥ 3)
        alpha    : L2 regularisation strength (default 0.5)
        """
        if len(sessions) < 3:
            return

        X = np.array([
            [s.balance_score, s.avg_tire_temp, s.temp_spread,
             s.air_temp_c, s.track_temp_c, s.fuel_per_lap]
            for s in sessions
        ], dtype=float)
        y = np.array([s.best_lap_s for s in sessions], dtype=float)

        # Standardize
        self._x_mean = X.mean(axis=0)
        raw_std = X.std(axis=0)
        self._x_std = np.where(raw_std > 1e-9, raw_std, 1.0)
        Xs = (X - self._x_mean) / self._x_std

        self._y_mean = y.mean()
        ys = y - self._y_mean

        # Ridge: w = (XᵀX + αI)⁻¹ Xᵀy
        A = Xs.T @ Xs + alpha * np.eye(Xs.shape[1])
        self._w = np.linalg.solve(A, Xs.T @ ys)

        y_hat = Xs @ self._w + self._y_mean
        self._residual_std = float(np.std(y - y_hat))
        self._n = len(sessions)

    # ── Prediction ────────────────────────────────────────────────────────────

    def predict(self, features: SessionFeatures) -> Optional[PredictionResult]:
        """
        Predict the achievable lap time for a given session's features.
        Returns None if the model hasn't been trained yet.
        """
        if not self.is_trained:
            return None

        x = np.array([
            features.balance_score, features.avg_tire_temp, features.temp_spread,
            features.air_temp_c, features.track_temp_c, features.fuel_per_lap,
        ])
        xs = (x - self._x_mean) / self._x_std
        pred = float(xs @ self._w + self._y_mean)

        # Confidence: rises with n_sessions and falls with residual_std
        conf = min(1.0, (self._n - 2) / 12.0) * max(0.1, 1.0 - self._residual_std / 3.0)

        # Feature importances (normalised absolute weights)
        abs_w = np.abs(self._w)
        total = abs_w.sum() or 1.0
        importance = {name: float(abs_w[i] / total) for i, name in enumerate(_FEATURE_NAMES)}

        delta = pred - features.best_lap_s
        insight = _build_insight(delta, features, importance)

        return PredictionResult(
            predicted_lap_s=pred,
            delta_vs_actual=delta,
            confidence=conf,
            feature_importance=importance,
            n_sessions=self._n,
            residual_std=self._residual_std,
            insight=insight,
        )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_insight(delta: float, feat: SessionFeatures, imp: Dict[str, float]) -> str:
    """Generate a one-sentence human-readable insight."""
    top_feat = max(imp, key=imp.get)
    top_label = top_feat.replace('_', ' ')

    if abs(delta) < 0.05:
        return "Model predicts you are already near your theoretical pace for these conditions."
    if delta < 0:
        return (
            f"Model predicts {abs(delta):.3f}s of improvement is available. "
            f"'{top_label}' has the strongest influence — focus there first."
        )
    return (
        f"Actual pace is {delta:.3f}s better than model prediction — "
        f"exceptional driving or favourable conditions. '{top_label}' is the dominant factor."
    )
