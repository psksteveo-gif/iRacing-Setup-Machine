"""
Racing Line from Telemetry — Reconstruct approximate track path from telemetry.

Strategy (best to worst accuracy):
  1. GPS (Lat/Lon channels) — equirectangular projection, zero drift, best shape.
  2. YawRate + Speed integration — avoids LatAccel/camber contamination.
  3. LatAccel/Speed dead-reckoning — original fallback, prone to drift on
     tracks with elevation change or banking (e.g. COTA).
"""

import numpy as np
from dataclasses import dataclass
from typing import Optional

# Earth radius in metres (WGS-84 mean)
_R_EARTH = 6_371_000.0


@dataclass
class RacingLine:
    """Reconstructed racing line from telemetry."""
    x: np.ndarray                # X positions (metres, arbitrary origin)
    y: np.ndarray                # Y positions
    speed: np.ndarray            # speed at each point (m/s)
    dist_pct: np.ndarray         # track % at each point
    lap_idx: int
    source: str = "unknown"      # "gps", "yawrate", or "lataccel"


def reconstruct_racing_line(data, lap_idx: int = 0) -> Optional[RacingLine]:
    """
    Reconstruct the racing line for *lap_idx* from telemetry.

    Tries three methods in order:
      1. GPS (Lat/Lon channels in radians) — equirectangular → metres.
      2. YawRate channel — integrate heading, then position.
      3. LatAccel/Speed — derive yaw rate, integrate heading then position.

    Returns RacingLine or None if insufficient data.
    """
    if lap_idx < 0 or lap_idx >= data.num_laps:
        return None

    s = data.lap_boundaries[lap_idx]
    e = data.lap_boundaries[lap_idx + 1]
    if e - s < 10:
        return None

    speed = data.get_channel('Speed')
    ld    = data.get_channel('LapDistPct')
    if speed is None:
        return None

    v    = speed[s:e].copy()
    dist = ld[s:e].copy() if ld is not None else np.linspace(0, 1, e - s)
    dt   = 1.0 / data.tick_rate

    # ── Method 1: GPS ────────────────────────────────────────────────────────
    lat_ch = data.get_channel('Lat')
    lon_ch = data.get_channel('Lon')
    if lat_ch is not None and lon_ch is not None:
        lat = lat_ch[s:e]
        lon = lon_ch[s:e]
        # iRacing stores Lat/Lon in radians
        lat0 = lat[0]
        lon0 = lon[0]
        x = (lon - lon0) * np.cos(lat0) * _R_EARTH
        y = (lat - lat0) * _R_EARTH
        if _valid_shape(x, y):
            return RacingLine(x=x, y=y, speed=v, dist_pct=dist,
                              lap_idx=lap_idx, source="gps")

    # ── Method 2: YawRate ────────────────────────────────────────────────────
    yr_ch = data.get_channel('YawRate')
    if yr_ch is not None:
        yaw_rate = yr_ch[s:e].copy()
        heading  = np.cumsum(yaw_rate) * dt
        vx = v * np.cos(heading)
        vy = v * np.sin(heading)
        x  = np.cumsum(vx) * dt
        y  = np.cumsum(vy) * dt
        if _valid_shape(x, y):
            return RacingLine(x=x, y=y, speed=v, dist_pct=dist,
                              lap_idx=lap_idx, source="yawrate")

    # ── Method 3: LatAccel / Speed dead-reckoning ────────────────────────────
    lat_g = data.get_channel('LatAccel')
    if lat_g is None:
        return None
    lat   = lat_g[s:e].copy()
    v_safe    = np.maximum(v, 1.0)   # avoid divide-by-zero at standstill
    yaw_rate  = lat / v_safe
    heading   = np.cumsum(yaw_rate) * dt
    vx = v * np.cos(heading)
    vy = v * np.sin(heading)
    x  = np.cumsum(vx) * dt
    y  = np.cumsum(vy) * dt
    return RacingLine(x=x, y=y, speed=v, dist_pct=dist,
                      lap_idx=lap_idx, source="lataccel")


def _valid_shape(x: np.ndarray, y: np.ndarray) -> bool:
    """Return True if the XY array looks like a plausible closed track shape."""
    if len(x) < 10:
        return False
    if not (np.isfinite(x).all() and np.isfinite(y).all()):
        return False
    # Require the shape to span at least a few metres in both axes
    if (x.max() - x.min()) < 5 or (y.max() - y.min()) < 5:
        return False
    return True


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
    colors[:, 0] = np.clip(1.0 - norm, 0, 1)                      # R: high at slow
    colors[:, 1] = np.clip(norm, 0, 1)                             # G: high at fast
    colors[:, 2] = np.clip(0.2 * (1 - abs(norm - 0.5) * 2), 0, 1) # B: peak at mid
    colors[:, 3] = 0.9  # alpha
    return colors
