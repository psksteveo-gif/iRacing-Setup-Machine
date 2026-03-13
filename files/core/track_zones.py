"""
Track zone classification — maps throttle/brake traces to zone categories.
Used by the Track Map — Throttle/Brake Zones heatmap.
"""

import numpy as np
from typing import Tuple


# Zone thresholds
BRAKE_THRESHOLD = 0.10    # brake > this  → braking zone
THROTTLE_THRESHOLD = 0.40 # throttle > this (and not braking) → throttle zone

# Zone RGBA colors
COLOR_BRAKE   = (0.91, 0.30, 0.24, 0.90)   # red
COLOR_THROTTLE = (0.18, 0.80, 0.44, 0.90)  # green
COLOR_COAST   = (0.95, 0.61, 0.07, 0.75)   # amber


def classify_zones(throttle: np.ndarray,
                   brake: np.ndarray) -> Tuple[np.ndarray, float, float, float]:
    """
    Classify each sample as braking, throttle, or coasting.

    Parameters
    ----------
    throttle : 1-D array of throttle values (0–1)
    brake    : 1-D array of brake values (0–1)

    Returns
    -------
    colors       : (N, 4) RGBA array
    throttle_pct : percentage of samples classified as throttle
    braking_pct  : percentage classified as braking
    coast_pct    : percentage classified as coasting
    """
    n = min(len(throttle), len(brake))
    thr = np.asarray(throttle[:n], dtype=float)
    brk = np.asarray(brake[:n], dtype=float)

    is_brake = brk > BRAKE_THRESHOLD
    is_throttle = (thr > THROTTLE_THRESHOLD) & ~is_brake

    colors = np.empty((n, 4), dtype=float)
    colors[is_brake] = COLOR_BRAKE
    colors[is_throttle] = COLOR_THROTTLE
    coast_mask = ~is_brake & ~is_throttle
    colors[coast_mask] = COLOR_COAST

    braking_pct = float(np.sum(is_brake) / n * 100) if n > 0 else 0.0
    throttle_pct = float(np.sum(is_throttle) / n * 100) if n > 0 else 0.0
    coast_pct = 100.0 - braking_pct - throttle_pct

    return colors, throttle_pct, braking_pct, coast_pct
