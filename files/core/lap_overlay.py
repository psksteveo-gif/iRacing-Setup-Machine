"""
Telemetry Lap Overlay — Extract and compare per-lap traces.
Computes delta statistics between two laps: speed, throttle, brake, G-forces.
"""

import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class LapTrace:
    """Telemetry trace for a single lap, resampled to uniform track %."""
    lap_idx: int
    dist_pct: np.ndarray          # 0–1, uniform 1000 points
    speed: np.ndarray
    throttle: np.ndarray
    brake: np.ndarray
    lat_g: np.ndarray
    long_g: np.ndarray
    gear: np.ndarray
    steering: np.ndarray
    lap_time: float


@dataclass
class LapComparison:
    """Detailed comparison between two laps."""
    lap_a: LapTrace
    lap_b: LapTrace
    speed_delta: np.ndarray       # lap_b.speed - lap_a.speed
    throttle_delta: np.ndarray
    brake_delta: np.ndarray
    # Summary stats
    avg_speed_a: float
    avg_speed_b: float
    max_speed_a: float
    max_speed_b: float
    throttle_pct_a: float         # % of track on throttle (>40%)
    throttle_pct_b: float
    braking_pct_a: float          # % of track braking (>10%)
    braking_pct_b: float
    time_delta: float             # lap_b.lap_time - lap_a.lap_time
    # Sections where biggest differences occur
    speed_gain_zones: List[Tuple[float, float, float]]   # (start_pct, end_pct, avg_delta)
    speed_loss_zones: List[Tuple[float, float, float]]


RESAMPLE_POINTS = 1000


def extract_lap_trace(data, lap_idx: int, resample_n: int = RESAMPLE_POINTS) -> Optional[LapTrace]:
    """Extract a single lap's telemetry, resampled to uniform track %."""
    if lap_idx < 0 or lap_idx >= data.num_laps:
        return None
    s = data.lap_boundaries[lap_idx]
    e = data.lap_boundaries[lap_idx + 1]
    if e <= s:
        return None

    ld = data.get_channel('LapDistPct')
    x_raw = ld[s:e] if ld is not None else np.linspace(0, 1, e - s)
    x_uniform = np.linspace(0, 1, resample_n)

    def _resample(ch_name: str, default: float = 0.0) -> np.ndarray:
        arr = data.get_channel(ch_name)
        if arr is None:
            return np.full(resample_n, default)
        seg = arr[s:e]
        return np.interp(x_uniform, x_raw, seg)

    return LapTrace(
        lap_idx=lap_idx,
        dist_pct=x_uniform,
        speed=_resample('Speed'),
        throttle=_resample('Throttle'),
        brake=_resample('Brake'),
        lat_g=_resample('LatAccel'),
        long_g=_resample('LongAccel'),
        gear=_resample('Gear'),
        steering=_resample('SteeringWheelAngle'),
        lap_time=data.lap_times[lap_idx] if lap_idx < len(data.lap_times) else 0.0,
    )


def compare_laps(data, lap_a_idx: int, lap_b_idx: int) -> Optional[LapComparison]:
    """Compare two laps and produce detailed delta analysis."""
    ta = extract_lap_trace(data, lap_a_idx)
    tb = extract_lap_trace(data, lap_b_idx)
    if ta is None or tb is None:
        return None

    speed_delta = tb.speed - ta.speed
    throttle_delta = tb.throttle - ta.throttle
    brake_delta = tb.brake - ta.brake

    thr_thresh = 0.40
    brk_thresh = 0.10

    # Find zones of significant speed gain/loss (>2 m/s sustained over 3%+ of track)
    gain_zones = _find_zones(ta.dist_pct, speed_delta, threshold=2.0, min_length=30)
    loss_zones = _find_zones(ta.dist_pct, -speed_delta, threshold=2.0, min_length=30)
    # Invert loss deltas back to negative
    loss_zones = [(s, e, -d) for s, e, d in loss_zones]

    return LapComparison(
        lap_a=ta,
        lap_b=tb,
        speed_delta=speed_delta,
        throttle_delta=throttle_delta,
        brake_delta=brake_delta,
        avg_speed_a=float(np.mean(ta.speed)),
        avg_speed_b=float(np.mean(tb.speed)),
        max_speed_a=float(np.max(ta.speed)),
        max_speed_b=float(np.max(tb.speed)),
        throttle_pct_a=float(np.sum(ta.throttle > thr_thresh) / len(ta.throttle) * 100),
        throttle_pct_b=float(np.sum(tb.throttle > thr_thresh) / len(tb.throttle) * 100),
        braking_pct_a=float(np.sum(ta.brake > brk_thresh) / len(ta.brake) * 100),
        braking_pct_b=float(np.sum(tb.brake > brk_thresh) / len(tb.brake) * 100),
        time_delta=tb.lap_time - ta.lap_time,
        speed_gain_zones=gain_zones,
        speed_loss_zones=loss_zones,
    )


def _find_zones(dist_pct: np.ndarray, delta: np.ndarray,
                threshold: float = 2.0, min_length: int = 30
                ) -> List[Tuple[float, float, float]]:
    """Find contiguous zones where delta exceeds threshold."""
    above = delta > threshold
    zones: List[Tuple[float, float, float]] = []
    start = None
    for i in range(len(above)):
        if above[i] and start is None:
            start = i
        elif not above[i] and start is not None:
            if i - start >= min_length:
                zones.append((
                    float(dist_pct[start]),
                    float(dist_pct[i - 1]),
                    float(np.mean(delta[start:i])),
                ))
            start = None
    if start is not None and len(above) - start >= min_length:
        zones.append((
            float(dist_pct[start]),
            float(dist_pct[-1]),
            float(np.mean(delta[start:])),
        ))
    return zones
