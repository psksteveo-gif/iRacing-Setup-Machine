"""
Fuel Economy Analyzer
=====================
Maps instantaneous fuel consumption (FuelUsePerHour, L/hr) to track
position to reveal where fuel is being burned most heavily.

High-consumption zones = hard throttle / rich mixture areas.
Identifies lift-and-coast opportunities and fuel-saving sectors.

Also computes per-lap fuel use from the FuelLevel channel for
accurate pit strategy planning.
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from core.ibt_parser import TelemetryData

MIN_SAMPLES = 300
N_BINS = 200   # track-position bins for the map
SPEED_MIN_MS = 5.0
# Fuel use rate threshold for "high consumption" zone (L/hr)
HIGH_FUEL_THRESHOLD_LPH = 25.0


@dataclass
class FuelLapRecord:
    lap: int
    fuel_used_l: float
    lap_time_s: float
    fuel_per_km: Optional[float] = None   # L/km if track length known


@dataclass
class FuelEconomyReport:
    has_data: bool = False

    # Per-lap records
    lap_records: List[FuelLapRecord] = field(default_factory=list)

    # Track-position map
    bin_edges: List[float] = field(default_factory=list)      # len=N_BINS+1
    avg_consumption_map: List[float] = field(default_factory=list)  # L/hr per bin

    # High-consumption zones (start_pct, end_pct, avg_lph)
    hot_zones: List[Tuple[float, float, float]] = field(default_factory=list)

    # Lift-and-coast opportunities (track zones where coasting would save fuel)
    coast_opportunities: List[Tuple[float, float]] = field(default_factory=list)

    # Stats
    avg_fuel_per_lap_l: float = 0.0
    std_fuel_per_lap_l: float = 0.0
    best_economy_lap: int = 0
    worst_economy_lap: int = 0
    peak_consumption_pct: float = 0.0   # track position of max fuel use
    peak_consumption_lph: float = 0.0
    total_fuel_used_l: float = 0.0

    summary: str = ""


class FuelEconomyAnalyzer:

    def analyze(self, data: TelemetryData, track_length_km: float = 0.0) -> FuelEconomyReport:
        report = FuelEconomyReport()

        fph_ch   = data.get_channel('FuelUsePerHour')
        fuel_ch  = data.get_channel('FuelLevel')
        dist_ch  = data.get_channel('LapDistPct')
        speed_ch = data.get_channel('Speed')
        time_ch  = data.get_channel('SessionTime')

        if dist_ch is None or len(dist_ch) < MIN_SAMPLES:
            return report

        # Need at least one of: FuelUsePerHour or FuelLevel
        if fph_ch is None and fuel_ch is None:
            return report

        report.has_data = True
        dist  = dist_ch.astype(float)
        speed = speed_ch.astype(float) if speed_ch is not None else None
        moving = (speed > SPEED_MIN_MS) if speed is not None else np.ones(len(dist), dtype=bool)

        # ── Per-lap fuel use from FuelLevel drops ─────────────────────────────
        if fuel_ch is not None and data.lap_boundaries and data.num_laps >= 2:
            fuel = fuel_ch.astype(float)
            for lap_idx in range(data.num_laps - 1):  # skip last incomplete lap
                b0 = data.lap_boundaries[lap_idx]
                b1 = data.lap_boundaries[lap_idx + 1] if lap_idx + 1 < len(data.lap_boundaries) else len(fuel)
                if b1 <= b0:
                    continue
                used = float(fuel[b0]) - float(fuel[min(b1, len(fuel)-1)])
                if 0.1 < used < 20.0:  # sanity range
                    lt = data.lap_times[lap_idx] if lap_idx < len(data.lap_times) else 0.0
                    fpk = used / track_length_km if track_length_km > 0 else None
                    report.lap_records.append(FuelLapRecord(
                        lap=lap_idx + 1, fuel_used_l=round(used, 3),
                        lap_time_s=round(lt, 3), fuel_per_km=round(fpk, 4) if fpk else None
                    ))

            if report.lap_records:
                usages = [r.fuel_used_l for r in report.lap_records]
                report.avg_fuel_per_lap_l = round(float(np.mean(usages)), 3)
                report.std_fuel_per_lap_l = round(float(np.std(usages)), 4)
                report.total_fuel_used_l  = round(float(np.sum(usages)), 2)
                best_rec  = min(report.lap_records, key=lambda r: r.fuel_used_l)
                worst_rec = max(report.lap_records, key=lambda r: r.fuel_used_l)
                report.best_economy_lap  = best_rec.lap
                report.worst_economy_lap = worst_rec.lap

        # ── Track-position consumption map from FuelUsePerHour ────────────────
        if fph_ch is not None and len(fph_ch) >= MIN_SAMPLES:
            fph = fph_ch.astype(float)
            # Clamp absurd values (sensor noise)
            fph = np.clip(fph, 0.0, 200.0)

            bins = np.linspace(0.0, 1.0, N_BINS + 1)
            report.bin_edges = bins.tolist()
            bin_idx = np.clip(np.digitize(dist, bins) - 1, 0, N_BINS - 1)

            sum_fph   = np.zeros(N_BINS)
            count_fph = np.zeros(N_BINS)
            np.add.at(sum_fph,   bin_idx[moving], fph[moving])
            np.add.at(count_fph, bin_idx[moving], 1)

            safe_count = np.where(count_fph > 0, count_fph, 1)
            avg_map = sum_fph / safe_count
            report.avg_consumption_map = avg_map.tolist()

            # Peak consumption position
            peak_bin = int(np.argmax(avg_map))
            report.peak_consumption_pct = float(bins[peak_bin])
            report.peak_consumption_lph = float(avg_map[peak_bin])

            # High-consumption zones: bins above threshold
            hot = avg_map > HIGH_FUEL_THRESHOLD_LPH
            _extract_zones(bins, hot, avg_map, report.hot_zones)

            # Lift-and-coast opportunities: high speed + high throttle + high consumption zones
            # These are the straights where you could lift early
            throttle_ch = data.get_channel('Throttle')
            if throttle_ch is not None:
                throttle = throttle_ch.astype(float)
                # Zones where throttle > 80% AND fph > threshold
                full_gas = (throttle > 0.80) & (fph > HIGH_FUEL_THRESHOLD_LPH) & moving
                coast_hot = np.zeros(N_BINS)
                np.add.at(coast_hot, bin_idx[full_gas], 1)
                coast_opportunity = (coast_hot / safe_count) > 0.5  # >50% of the time
                _extract_zones(bins, coast_opportunity, avg_map, report.coast_opportunities,
                               as_tuples=True)

        # ── Summary ───────────────────────────────────────────────────────────
        parts = []
        if report.avg_fuel_per_lap_l > 0:
            parts.append(f"Avg: {report.avg_fuel_per_lap_l:.3f} L/lap")
        if report.peak_consumption_lph > 0:
            parts.append(f"Peak: {report.peak_consumption_lph:.0f} L/hr @{report.peak_consumption_pct*100:.0f}%")
        if report.hot_zones:
            parts.append(f"{len(report.hot_zones)} high-consumption zones")
        if report.coast_opportunities:
            parts.append(f"{len(report.coast_opportunities)} lift-and-coast opportunities")
        report.summary = "  |  ".join(parts) if parts else "No fuel economy data"
        return report


def _extract_zones(
    bins: np.ndarray,
    mask: np.ndarray,
    values: np.ndarray,
    out_list: list,
    as_tuples: bool = False,
    min_bins: int = 3,
) -> None:
    """Extract contiguous True regions from mask as (start_pct, end_pct[, avg_value]) tuples."""
    in_zone = False
    zone_start = 0
    for i in range(len(mask)):
        if mask[i] and not in_zone:
            in_zone = True
            zone_start = i
        elif not mask[i] and in_zone:
            in_zone = False
            if i - zone_start >= min_bins:
                s = float(bins[zone_start])
                e = float(bins[min(i, len(bins)-1)])
                if as_tuples:
                    out_list.append((s, e))
                else:
                    avg_v = float(np.mean(values[zone_start:i]))
                    out_list.append((s, e, round(avg_v, 1)))
    if in_zone and len(mask) - zone_start >= min_bins:
        s = float(bins[zone_start])
        e = float(bins[-1])
        if as_tuples:
            out_list.append((s, e))
        else:
            avg_v = float(np.mean(values[zone_start:]))
            out_list.append((s, e, round(avg_v, 1)))
