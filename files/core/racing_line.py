"""
Racing Line from Telemetry — Reconstruct approximate track path from telemetry.
Uses LapDistPct, Speed, SteeringWheelAngle, and LatAccel to estimate XY position.
Color-codes by speed for visualization.
"""

import numpy as np
from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass
class RacingLine:
    """Reconstructed racing line from telemetry."""
    x: np.ndarray                # X positions (meters, arbitrary origin)
    y: np.ndarray                # Y positions
    speed: np.ndarray            # speed at each point (m/s)
    dist_pct: np.ndarray         # track % at each point
    lap_idx: int


def reconstruct_racing_line(data, lap_idx: int = 0) -> Optional[RacingLine]:
    """
    Reconstruct approximate racing line from telemetry using speed and lateral acceleration.

    The approach integrates heading changes from lateral acceleration and speed
    to build an XY track map. This produces a shape that resembles the actual
    track layout.

    Parameters
    ----------
    data : TelemetryData
    lap_idx : lap to reconstruct (default: 0)

    Returns RacingLine or None if insufficient data.
    """
    if lap_idx < 0 or lap_idx >= data.num_laps:
        return None

    s = data.lap_boundaries[lap_idx]
    e = data.lap_boundaries[lap_idx + 1]
    if e - s < 10:
        return None

    speed = data.get_channel('Speed')
    lat_g = data.get_channel('LatAccel')
    ld = data.get_channel('LapDistPct')
    if speed is None or lat_g is None:
        return None

    v = speed[s:e].copy()
    lat = lat_g[s:e].copy()
    dist = ld[s:e].copy() if ld is not None else np.linspace(0, 1, e - s)

    dt = 1.0 / data.tick_rate
    n = len(v)

    # Heading from lateral acceleration: d(heading)/dt = lat_accel / speed
    # Avoid division by near-zero speed
    v_safe = np.maximum(v, 1.0)
    yaw_rate = lat / v_safe  # rad/s
    heading = np.cumsum(yaw_rate) * dt

    # Integrate position
    vx = v * np.cos(heading)
    vy = v * np.sin(heading)
    x = np.cumsum(vx) * dt
    y = np.cumsum(vy) * dt

    return RacingLine(x=x, y=y, speed=v, dist_pct=dist, lap_idx=lap_idx)


def speed_colormap(speed: np.ndarray) -> np.ndarray:
    """
    Map speed values to RGBA colors: red (slow) → yellow → green (fast).

    Returns (N, 4) RGBA array.
    """
    if len(speed) == 0:
        return np.empty((0, 4))
    vmin = np.min(speed)
    vmax = np.max(speed)
    rng = vmax - vmin if vmax > vmin else 1.0
    norm = (speed - vmin) / rng  # 0 = slow, 1 = fast

    colors = np.zeros((len(speed), 4))
    # Red → Yellow → Green gradient
    colors[:, 0] = np.clip(1.0 - norm, 0, 1)           # R: high at slow
    colors[:, 1] = np.clip(norm, 0, 1)                  # G: high at fast
    colors[:, 2] = np.clip(0.2 * (1 - abs(norm - 0.5) * 2), 0, 1)  # B: peak at mid
    colors[:, 3] = 0.9  # alpha
    return colors
