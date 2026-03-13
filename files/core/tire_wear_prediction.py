"""
Tire Wear Prediction — nonlinear projection of tire life, grip cliff,
pit window recommendation, and per-lap wear-percentage model.
"""

import numpy as np
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from core.advanced_analysis import TireDegReport


# ── Tunables ──────────────────────────────────────────────────────────────
WEAR_OUTLIER_S = 3.0          # lap‐time seconds from median → outlier
MIN_LAPS_FOR_PREDICTION = 4   # need at least this many clean laps
PROJECTION_LAPS = 15          # how many future laps to project
CLIFF_THRESHOLD_PCT = 8.0     # wear % above which grip drops dramatically
CONFIDENCE_GROWTH = 0.12      # confidence band widens per projected lap (seconds)
PIT_WINDOW_MARGIN = 2         # laps before cliff to open pit window


@dataclass
class TireWearPrediction:
    """Result of tire wear projection analysis."""
    # Per-lap wear percentage (0 = fresh, 100 = destroyed)
    wear_pct_per_lap: List[float] = field(default_factory=list)

    # Projected future lap times (actual + extrapolated)
    actual_laps: List[int] = field(default_factory=list)
    actual_times: List[float] = field(default_factory=list)
    projected_laps: List[int] = field(default_factory=list)
    projected_times: List[float] = field(default_factory=list)
    confidence_upper: List[float] = field(default_factory=list)
    confidence_lower: List[float] = field(default_factory=list)

    # Key predictions
    grip_cliff_lap: int = 0           # lap where grip falls off sharply
    pit_window_open: int = 0          # recommended earliest pit
    pit_window_close: int = 0         # recommended latest pit (= cliff)
    tire_life_pct: float = 100.0      # current tire life (100 = fresh)
    peak_wear_corner: str = ""        # which corner is wearing fastest

    # Fit quality
    fit_type: str = "none"            # "linear", "quadratic", or "none"
    r_squared: float = 0.0

    findings: List[str] = field(default_factory=list)


def predict_tire_wear(report: TireDegReport,
                      projection_laps: int = PROJECTION_LAPS) -> TireWearPrediction:
    """
    Build a nonlinear tire‐wear prediction from a TireDegReport.

    Uses actual lap times to fit a quadratic or linear model, then
    projects future lap times with confidence bands.  Also computes
    per‐lap wear % from tire‐temp progression data.
    """
    pred = TireWearPrediction()
    lap_times = report.lap_times

    if not lap_times or len(lap_times) < 2:
        pred.findings.append("Not enough lap data for tire wear prediction.")
        return pred

    # ── 1. Clean lap times (remove outliers) ──────────────────────────
    times = np.array(lap_times, dtype=float)
    median = np.median(times)
    valid_mask = np.abs(times - median) < WEAR_OUTLIER_S
    clean_indices = np.where(valid_mask)[0]
    clean_times = times[valid_mask]

    # Store actual data
    pred.actual_laps = list(range(1, len(times) + 1))
    pred.actual_times = list(times)

    if len(clean_times) < MIN_LAPS_FOR_PREDICTION:
        pred.findings.append(
            f"Only {len(clean_times)} clean laps — need {MIN_LAPS_FOR_PREDICTION} for prediction."
        )
        return pred

    # ── 2. Fit model (try quadratic, fall back to linear) ─────────────
    x = clean_indices.astype(float)
    y = clean_times

    # Quadratic fit
    coeffs2 = np.polyfit(x, y, 2)
    y_pred2 = np.polyval(coeffs2, x)
    ss_res2 = np.sum((y - y_pred2) ** 2)
    ss_tot = np.sum((y - np.mean(y)) ** 2)
    r2_quad = 1.0 - ss_res2 / ss_tot if ss_tot > 0 else 0.0

    # Linear fit
    coeffs1 = np.polyfit(x, y, 1)
    y_pred1 = np.polyval(coeffs1, x)
    ss_res1 = np.sum((y - y_pred1) ** 2)
    r2_lin = 1.0 - ss_res1 / ss_tot if ss_tot > 0 else 0.0

    # Use quadratic if it fits notably better and curves upward (a > 0)
    if r2_quad > r2_lin + 0.02 and coeffs2[0] > 0:
        coeffs = coeffs2
        pred.fit_type = "quadratic"
        pred.r_squared = float(r2_quad)
    else:
        coeffs = np.append([0.0], coeffs1)  # pad to 3 coefficients
        pred.fit_type = "linear"
        pred.r_squared = float(r2_lin)

    # ── 3. Project future laps ────────────────────────────────────────
    last_lap = len(times)
    future_x = np.arange(last_lap, last_lap + projection_laps, dtype=float)
    future_times = np.polyval(coeffs, future_x)

    # Clamp projected times: never below best clean time
    best_clean = float(np.min(clean_times))
    future_times = np.maximum(future_times, best_clean)

    pred.projected_laps = list(range(last_lap + 1, last_lap + projection_laps + 1))
    pred.projected_times = [float(t) for t in future_times]

    # Confidence bands widen with distance from data
    for i, ft in enumerate(future_times):
        margin = CONFIDENCE_GROWTH * (i + 1)
        pred.confidence_upper.append(float(ft + margin))
        pred.confidence_lower.append(float(max(best_clean, ft - margin)))

    # ── 4. Grip cliff & pit window ───────────────────────────────────
    cliff_time = best_clean + 1.5  # 1.5s above best = cliff
    all_proj_laps = list(range(1, last_lap + projection_laps + 1))
    all_proj_times = np.polyval(coeffs, np.arange(0, last_lap + projection_laps, dtype=float))

    cliff_lap = 0
    for lap_i, t in enumerate(all_proj_times):
        if t > cliff_time and lap_i > 0:
            cliff_lap = lap_i + 1  # 1-indexed
            break
    if cliff_lap == 0 and len(all_proj_times) > 0:
        cliff_lap = last_lap + projection_laps  # no cliff in range

    pred.grip_cliff_lap = cliff_lap
    pred.pit_window_open = max(1, cliff_lap - PIT_WINDOW_MARGIN - 2)
    pred.pit_window_close = max(pred.pit_window_open + 1, cliff_lap - 1)

    # ── 5. Per-lap wear % from temp progression ──────────────────────
    _compute_wear_pct(report, pred)

    # ── 6. Current tire life ─────────────────────────────────────────
    if pred.wear_pct_per_lap:
        pred.tire_life_pct = max(0.0, 100.0 - pred.wear_pct_per_lap[-1])

    # ── 7. Findings ──────────────────────────────────────────────────
    if cliff_lap <= last_lap:
        pred.findings.append(
            f"⚠ Grip cliff may already be reached (lap {cliff_lap}). Consider pitting."
        )
    elif cliff_lap <= last_lap + 5:
        pred.findings.append(
            f"Grip cliff projected at lap {cliff_lap}. Pit window: laps {pred.pit_window_open}–{pred.pit_window_close}."
        )
    else:
        pred.findings.append(
            f"Tires projected to last well beyond current stint. Cliff ~lap {cliff_lap}."
        )

    if pred.peak_wear_corner:
        pred.findings.append(
            f"Fastest-wearing corner: {pred.peak_wear_corner} — monitor temps closely."
        )

    pred.findings.append(
        f"Fit: {pred.fit_type} (R²={pred.r_squared:.3f}). "
        f"Tire life: {pred.tire_life_pct:.0f}%."
    )

    return pred


def _compute_wear_pct(report: TireDegReport, pred: TireWearPrediction):
    """
    Compute per-lap wear percentage from tire temp progression.

    Wear model: baseline temp = lap 1 avg across corners.
    Wear % = (current_avg - baseline) / (overheat_threshold - baseline) × 100,
    clamped to [0, 100].
    """
    temps = report.tire_temp_progression
    if not temps:
        return

    # Average temp across all corners per lap
    all_corners = list(temps.keys())
    if not all_corners:
        return

    num_laps = min(len(v) for v in temps.values())
    if num_laps < 1:
        return

    avg_per_lap = []
    for lap_i in range(num_laps):
        lap_avg = float(np.mean([temps[c][lap_i] for c in all_corners]))
        avg_per_lap.append(lap_avg)

    baseline = avg_per_lap[0]
    overheat = baseline + 20.0  # 20°C above baseline = 100% wear

    for avg in avg_per_lap:
        wear = (avg - baseline) / (overheat - baseline) * 100.0 if overheat > baseline else 0.0
        pred.wear_pct_per_lap.append(float(np.clip(wear, 0.0, 100.0)))

    # Find peak-wearing corner (highest last-lap temp)
    max_delta = 0.0
    for corner, tvals in temps.items():
        if len(tvals) >= 2:
            delta = tvals[-1] - tvals[0]
            if delta > max_delta:
                max_delta = delta
                pred.peak_wear_corner = corner
