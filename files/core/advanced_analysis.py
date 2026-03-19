"""
Sector Analysis, Theoretical Best Lap, Fuel Correction, and Tire Pressure Model
"""

import numpy as np
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from core.ibt_parser import TelemetryData
try:
    from data.track_corners import get_sectors as _get_track_sectors  # type: ignore[import-unresolved]
except ImportError:
    def _get_track_sectors(track_name): return [1/3, 2/3]  # type: ignore[misc]

# ── Analysis thresholds (tunable) ─────────────────────────────────────────
DEG_OUTLIER_S = 3.0              # lap time seconds from median → outlier for deg calc
DEG_RATE_THRESHOLD = 0.05        # seconds/lap above this → significant degradation
CLIFF_DELTA_S = 1.5              # seconds above best lap → performance cliff
CLIFF_MARGIN_LAPS = 3            # laps before cliff to end stint
MIN_STINT_LAPS = 5               # minimum optimal stint length
PRESSURE_DELTA_PSI = 1.5         # hot vs target delta above this → finding
TEMP_COEFF_PSI_PER_C = 0.05     # PSI adjustment per °C of track temp
TEMP_BASELINE_C = 25             # reference track temp for pressure model


# ══════════════════════════════════════════════════════════════════════════════
# SECTOR ANALYSIS
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class SectorData:
    sector_num: int
    start_pct: float
    end_pct: float
    lap_times: List[float] = field(default_factory=list)      # sector time per lap
    avg_speeds: List[float] = field(default_factory=list)
    avg_lat_g: List[float] = field(default_factory=list)
    lf_temps: List[float] = field(default_factory=list)
    rf_temps: List[float] = field(default_factory=list)
    lr_temps: List[float] = field(default_factory=list)
    rr_temps: List[float] = field(default_factory=list)
    throttle_pct: List[float] = field(default_factory=list)
    brake_pct: List[float] = field(default_factory=list)

    @property
    def best_time(self) -> float:
        return min(self.lap_times) if self.lap_times else 0.0

    @property
    def avg_time(self) -> float:
        return float(np.mean(self.lap_times)) if self.lap_times else 0.0

    @property
    def consistency(self) -> float:
        if len(self.lap_times) < 2: return 100.0
        return float(100 - np.std(self.lap_times) / max(np.mean(self.lap_times), 0.001) * 100)


@dataclass
class SectorAnalysisReport:
    num_sectors: int = 3
    sectors: List[SectorData] = field(default_factory=list)
    theoretical_best: float = 0.0
    actual_best: float = 0.0
    time_left_on_table: float = 0.0
    worst_sector: int = 0          # sector index where most time is lost
    thermal_hotspots: Dict[str, List[int]] = field(default_factory=dict)  # corner -> [sector nums]


class SectorAnalyzer:

    def analyze(self, data: TelemetryData, num_sectors: int = 3,
                track_name: str = "",
                sector_splits: list = None) -> SectorAnalysisReport:
        """Divide each lap into sectors, compute per-sector times and speeds, find the worst sector."""
        report = SectorAnalysisReport(num_sectors=num_sectors)

        lap_dist = data.get_channel('LapDistPct')
        session_time = data.get_channel('SessionTime')
        speed = data.get_channel('Speed')
        if lap_dist is None or data.num_laps < 1:
            return report

        # Priority: explicit sector_splits arg → track DB → equal split
        if sector_splits and len(sector_splits) >= 1:
            # sector_splits is a list of start-pct values (first is always 0.0)
            splits = [s for s in sector_splits if 0.0 < s < 1.0]
            boundaries = np.array([0.0] + sorted(splits) + [1.0])
            num_sectors = len(boundaries) - 1
            report = SectorAnalysisReport(num_sectors=num_sectors)
        else:
            _track = track_name or data.track_name
            real_splits = _get_track_sectors(_track) if _track else []
            if len(real_splits) == num_sectors - 1:
                boundaries = np.array([0.0] + real_splits + [1.0])
            else:
                boundaries = np.linspace(0, 1, num_sectors + 1)
        sectors = [SectorData(i, float(boundaries[i]), float(boundaries[i+1]))
                   for i in range(num_sectors)]

        # Process each lap
        for lap_idx in range(data.num_laps):
            start_sample = data.lap_boundaries[lap_idx]
            end_sample = data.lap_boundaries[lap_idx + 1]
            if end_sample - start_sample < 60:
                continue

            lap_dist_lap = lap_dist[start_sample:end_sample]

            for sec in sectors:
                mask = (lap_dist_lap >= sec.start_pct) & (lap_dist_lap < sec.end_pct)
                if not np.any(mask):
                    continue

                # Compute real sector time from SessionTime channel
                indices = np.where(mask)[0]
                if session_time is not None and len(indices) >= 2:
                    abs_start = start_sample + indices[0]
                    abs_end = start_sample + indices[-1]
                    sector_time = float(session_time[abs_end] - session_time[abs_start])
                    if sector_time > 0:
                        sec.lap_times.append(sector_time)

                if speed is not None:
                    spd = speed[start_sample:end_sample][mask]
                    sec.avg_speeds.append(float(np.mean(spd)) * 3.6 if len(spd) > 0 else 0)

                # Channel averages in this sector
                for ch_name, target_list, scale in (
                    ('LFtempCM', sec.lf_temps, 1.0),
                    ('RFtempCM', sec.rf_temps, 1.0),
                    ('LRtempCM', sec.lr_temps, 1.0),
                    ('RRtempCM', sec.rr_temps, 1.0),
                    ('Throttle', sec.throttle_pct, 100.0),
                    ('Brake', sec.brake_pct, 100.0),
                ):
                    arr = data.get_channel(ch_name)
                    if arr is not None:
                        sub = arr[start_sample:end_sample][mask]
                        target_list.append(float(np.mean(sub)) * scale if len(sub) > 0 else 0.0)
                    else:
                        target_list.append(0.0)

                lat = data.get_channel('LatAccel')
                if lat is not None:
                    sub = lat[start_sample:end_sample][mask]
                    sec.avg_lat_g.append(float(np.mean(np.abs(sub))) if len(sub) > 0 else 0)

        report.sectors = sectors

        # Theoretical best lap
        sector_bests = [s.best_time for s in sectors]
        if all(b > 0 for b in sector_bests):
            report.theoretical_best = sum(sector_bests)

        if data.lap_times:
            report.actual_best = min(data.lap_times)
            report.time_left_on_table = max(0, report.actual_best - report.theoretical_best)

        # Find worst sector (most time lost vs best)
        if sectors:
            deltas = []
            for sec in sectors:
                if sec.lap_times and len(sec.lap_times) >= 2:
                    deltas.append(sec.avg_time - sec.best_time)
                else:
                    deltas.append(0.0)
            if deltas:
                report.worst_sector = int(np.argmax(deltas))

        return report


# ══════════════════════════════════════════════════════════════════════════════
# THEORETICAL BEST LAP + FUEL CORRECTION
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class BestLapReport:
    lap_times: List[float] = field(default_factory=list)
    fuel_corrected: List[float] = field(default_factory=list)  # normalized to zero fuel
    theoretical_best: float = 0.0
    actual_best: float = 0.0
    fuel_corrected_best: float = 0.0
    laps_improving: bool = False
    improvement_trend: float = 0.0   # seconds per lap (negative = improving)
    fuel_per_lap_kg: float = 0.0


class BestLapAnalyzer:

    def analyze(self, data: TelemetryData) -> BestLapReport:
        """Compute fuel-corrected lap times and improvement trends."""
        report = BestLapReport()
        report.lap_times = list(data.lap_times)

        if not data.lap_times:
            return report

        report.actual_best = min(data.lap_times)
        report.theoretical_best = report.actual_best  # fallback

        # Fuel consumption
        fuel = data.get_channel('FuelLevel')
        if fuel is not None and data.num_laps > 1:
            start_fuel = float(fuel[data.lap_boundaries[0]])
            end_fuel = float(fuel[data.lap_boundaries[-1] - 1])
            total_fuel_used = start_fuel - end_fuel
            report.fuel_per_lap_kg = total_fuel_used / max(data.num_laps, 1) * 0.75  # liters to kg approx

        # Fuel correction using shared car classifier
        from core.car_classifier import classify_car, FUEL_EFFECT_S_PER_KG
        car_class = classify_car(data.car_name)
        fuel_eff = FUEL_EFFECT_S_PER_KG.get(car_class, 0.030)

        # Estimate fuel at each lap start
        if data.num_laps > 0 and report.fuel_per_lap_kg > 0:
            fuel_corrections = []
            for i, t in enumerate(data.lap_times):
                fuel_at_lap = report.fuel_per_lap_kg * (data.num_laps - i)
                correction = fuel_at_lap * fuel_eff
                corrected = t - correction
                fuel_corrections.append(corrected)
            report.fuel_corrected = fuel_corrections
            if fuel_corrections:
                report.fuel_corrected_best = min(fuel_corrections)
        else:
            report.fuel_corrected = list(data.lap_times)
            report.fuel_corrected_best = report.actual_best

        # Improvement trend (linear regression on lap times)
        if len(data.lap_times) >= 3:
            x = np.arange(len(data.lap_times), dtype=float)
            y = np.array(data.lap_times)
            if np.std(y) > 0:
                coeffs = np.polyfit(x, y, 1)
                report.improvement_trend = float(coeffs[0])  # seconds per lap
                report.laps_improving = coeffs[0] < -0.05

        return report


# ══════════════════════════════════════════════════════════════════════════════
# STINT / TIRE DEGRADATION MODEL
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class TireDegReport:
    lap_times: List[float] = field(default_factory=list)
    tire_temp_progression: Dict[str, List[float]] = field(default_factory=dict)
    deg_rate: float = 0.0             # seconds per lap degradation
    optimal_stint_length: int = 0     # estimated laps before critical deg
    cliff_lap: int = 0                # lap where performance drops sharply
    pressure_cold_targets: Dict[str, float] = field(default_factory=dict)  # cold PSI to hit target hot
    pressure_hot_actuals: Dict[str, float] = field(default_factory=dict)
    findings: List[str] = field(default_factory=list)


class StintAnalyzer:

    def analyze(self, data: TelemetryData) -> TireDegReport:
        """Model tire degradation, pressure targets, and optimal stint length."""
        report = TireDegReport()
        report.lap_times = list(data.lap_times)

        # Use shared car classifier for pressure targets
        from core.car_classifier import classify_car, PRESSURE_TARGETS, PRESSURE_RISE
        car_class = classify_car(data.car_name)

        # ── Pressure cold→hot model ────────────────────────────────────
        self._model_pressures(data, report, car_class)

        # ── Tire temp progression ──────────────────────────────────────
        self._analyze_temp_progression(data, report)

        # ── Degradation rate ──────────────────────────────────────────
        if len(data.lap_times) >= 3:
            laps = np.arange(len(data.lap_times), dtype=float)
            times = np.array(data.lap_times)
            # Remove outliers (safety car laps etc.)
            median = np.median(times)
            valid = np.abs(times - median) < DEG_OUTLIER_S
            if np.sum(valid) >= 3:
                coeffs = np.polyfit(laps[valid], times[valid], 1)
                report.deg_rate = float(coeffs[0])  # s/lap
                if report.deg_rate > DEG_RATE_THRESHOLD:
                    # Estimate cliff: where time exceeds best + cliff delta
                    best = min(times)
                    cliff_time = best + CLIFF_DELTA_S
                    cliff = int((cliff_time - coeffs[1]) / coeffs[0])
                    report.cliff_lap = max(0, cliff)
                    report.optimal_stint_length = max(MIN_STINT_LAPS, cliff - CLIFF_MARGIN_LAPS)
                    report.findings.append(
                        f"Tire degradation: +{report.deg_rate:.3f}s/lap. "
                        f"Estimated cliff at lap {report.cliff_lap}. "
                        f"Optimal stint: {report.optimal_stint_length} laps."
                    )

        return report

    def _model_pressures(self, data: TelemetryData, report: TireDegReport, car_class):
        from core.car_classifier import PRESSURE_TARGETS, PRESSURE_RISE, CarClass
        targets = PRESSURE_TARGETS.get(car_class, PRESSURE_TARGETS[CarClass.DEFAULT])
        rise = PRESSURE_RISE.get(car_class, 2.5)

        # Track temp adjustment
        track_temp = data.session_info.get('track_temp_c', 30)
        temp_adj = (track_temp - TEMP_BASELINE_C) * TEMP_COEFF_PSI_PER_C

        pressure_channels = {'LF': 'LFpress', 'RF': 'RFpress', 'LR': 'LRpress', 'RR': 'RRpress'}

        for corner, ch in pressure_channels.items():
            arr = data.get_channel(ch)
            if arr is not None and len(arr) > 0:
                # Hot pressure = mean over the session (excluding warmup)
                warmup = min(60 * 10, len(arr) // 4)  # skip first 10s
                hot = float(np.mean(arr[warmup:]))
                report.pressure_hot_actuals[corner] = hot

                target_hot = targets[corner] + temp_adj
                # cold = hot_target - rise  (temp_adj already in target_hot)
                cold = target_hot - rise
                report.pressure_cold_targets[corner] = round(cold, 1)
            else:
                target_hot = targets[corner]
                cold = target_hot - rise
                report.pressure_cold_targets[corner] = round(cold, 1)

        # Add finding if hot pressures differ significantly from targets
        for corner, hot in report.pressure_hot_actuals.items():
            target = targets.get(corner, 32.0)
            delta = hot - target
            if abs(delta) > PRESSURE_DELTA_PSI:
                direction = "above" if delta > 0 else "below"
                report.findings.append(
                    f"{corner} running {abs(delta):.1f} PSI {direction} target hot pressure ({target:.0f} PSI). "
                    f"Adjust cold pressure: {report.pressure_cold_targets[corner]:.1f} PSI recommended."
                )

    def _analyze_temp_progression(self, data: TelemetryData, report: TireDegReport):
        channels = {'LF': 'LFtempCM', 'RF': 'RFtempCM', 'LR': 'LRtempCM', 'RR': 'RRtempCM'}
        for corner, ch in channels.items():
            arr = data.get_channel(ch)
            if arr is None:
                continue
            lap_avgs = []
            for i in range(data.num_laps):
                start = data.lap_boundaries[i]
                end = data.lap_boundaries[i + 1]
                lap_avgs.append(float(np.mean(arr[start:end])))
            report.tire_temp_progression[corner] = lap_avgs


# ══════════════════════════════════════════════════════════════════════════════
# HISTORY TRACKER
# ══════════════════════════════════════════════════════════════════════════════

import json
import os
from datetime import datetime
from typing import List


@dataclass
class HistoryEntry:
    timestamp: str
    car: str
    track: str
    best_lap: float
    setup_snapshot: Dict
    changes_from_prev: List[Dict] = field(default_factory=list)
    notes: str = ""


class HistoryTracker:
    MAX_ENTRIES = 500             # absolute cap on stored entries
    MAX_PER_COMBO = 30            # max entries per car+track pair

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or os.path.expanduser("~/.iracing_setup_history.json")
        self.entries: List[HistoryEntry] = []
        self._load()

    def _load(self):
        if os.path.exists(self.db_path):
            try:
                file_size = os.path.getsize(self.db_path)
                if file_size > 50 * 1024 * 1024:  # 50 MB — corrupt / runaway
                    self.entries = []
                    self._prune()
                    return
                with open(self.db_path, 'r') as f:
                    data = json.load(f)
                allowed_keys = {'timestamp', 'car', 'track', 'best_lap', 'setup_snapshot', 'changes_from_prev', 'notes'}
                self.entries = [HistoryEntry(**{k: v for k, v in e.items() if k in allowed_keys}) for e in data]
                self._prune()
            except Exception:
                self.entries = []

    def _prune(self):
        """Rotate history: keep only MAX_PER_COMBO entries per car+track, MAX_ENTRIES total."""
        combo_buckets: Dict[str, List[HistoryEntry]] = {}
        for e in self.entries:
            key = f"{e.car}||{e.track}"
            combo_buckets.setdefault(key, []).append(e)

        if len(self.entries) <= self.MAX_ENTRIES:
            if not any(len(v) > self.MAX_PER_COMBO for v in combo_buckets.values()):
                return

        pruned = []
        for entries in combo_buckets.values():
            # Sort newest-first, keep only MAX_PER_COMBO
            entries.sort(key=lambda e: e.timestamp, reverse=True)
            pruned.extend(entries[:self.MAX_PER_COMBO])

        # Global cap: keep newest overall
        pruned.sort(key=lambda e: e.timestamp, reverse=True)
        self.entries = pruned[:self.MAX_ENTRIES]
        self.save()

    def save(self):
        import tempfile
        dir_name = os.path.dirname(self.db_path) or '.'
        fd, tmp = tempfile.mkstemp(dir=dir_name, suffix='.tmp')
        try:
            with os.fdopen(fd, 'w') as f:
                json.dump([vars(e) for e in self.entries], f, indent=2)
            os.replace(tmp, self.db_path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def add_entry(self, car: str, track: str, best_lap: float,
                  setup: dict, notes: str = "") -> HistoryEntry:
        # Diff against previous entry for same car+track
        prev = self._find_last(car, track)
        changes = []
        if prev:
            all_keys = set(prev.setup_snapshot.keys()) | set(setup.keys())
            for k in all_keys:
                a = prev.setup_snapshot.get(k, "—")
                b = setup.get(k, "—")
                if a != b:
                    changes.append({'param': k, 'before': a, 'after': b})

        entry = HistoryEntry(
            timestamp=datetime.now().isoformat(),
            car=car,
            track=track,
            best_lap=best_lap,
            setup_snapshot=setup,
            changes_from_prev=changes,
            notes=notes,
        )
        self.entries.append(entry)
        self._prune()
        self.save()
        return entry

    def _find_last(self, car: str, track: str) -> Optional[HistoryEntry]:
        matches = [e for e in self.entries if e.car == car and e.track == track]
        if not matches:
            return None
        # Return most recent by timestamp
        return max(matches, key=lambda e: e.timestamp)

    def get_history(self, car: Optional[str] = None, track: Optional[str] = None) -> List[HistoryEntry]:
        entries = self.entries
        if car:
            entries = [e for e in entries if car.lower() in e.car.lower()]
        if track:
            entries = [e for e in entries if track.lower() in e.track.lower()]
        return sorted(entries, key=lambda e: e.timestamp, reverse=True)

    def clear(self):
        self.entries = []
        self.save()


# ══════════════════════════════════════════════════════════════════════════════
# FUEL STRATEGY CALCULATOR
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class FuelStrategyReport:
    fuel_per_lap_l: float = 0.0         # liters per lap
    fuel_remaining_l: float = 0.0       # fuel at end of loaded session
    fuel_capacity_l: float = 0.0        # tank size (from session YAML or default)
    laps_remaining: int = 0             # laps until empty from current fuel
    avg_lap_time: float = 0.0           # average lap time in seconds
    # Race strategy (populated if race_laps provided)
    race_laps: int = 0
    total_fuel_needed_l: float = 0.0
    num_stops: int = 0
    pit_laps: List[int] = field(default_factory=list)  # recommended lap to pit
    fuel_per_stop_l: List[float] = field(default_factory=list)
    finish_fuel_l: float = 0.0          # predicted fuel at finish
    findings: List[str] = field(default_factory=list)


class FuelStrategyAnalyzer:
    SAFETY_MARGIN_LAPS = 0.5  # extra half-lap worth of fuel per stint

    def analyze(self, data: TelemetryData, race_laps: int = 0) -> FuelStrategyReport:
        report = FuelStrategyReport()

        fuel = data.get_channel('FuelLevel')
        if fuel is None or data.num_laps < 1:
            report.findings.append("No fuel data available.")
            return report

        # Compute fuel consumption
        start_fuel = float(fuel[data.lap_boundaries[0]])
        end_fuel = float(fuel[data.lap_boundaries[-1] - 1])
        total_used = start_fuel - end_fuel
        report.fuel_per_lap_l = total_used / max(data.num_laps, 1)
        report.fuel_remaining_l = end_fuel
        report.fuel_capacity_l = data.session_info.get('fuel_capacity_l', start_fuel)

        if report.fuel_per_lap_l <= 0:
            report.findings.append("Cannot compute strategy — fuel not decreasing.")
            return report

        report.laps_remaining = int(end_fuel / report.fuel_per_lap_l)

        if data.lap_times:
            report.avg_lap_time = float(np.mean(data.lap_times))

        report.findings.append(
            f"Fuel usage: {report.fuel_per_lap_l:.2f} L/lap. "
            f"Remaining: {report.fuel_remaining_l:.1f} L ({report.laps_remaining} laps)."
        )

        # Race strategy
        if race_laps > 0:
            report.race_laps = race_laps
            safety = self.SAFETY_MARGIN_LAPS * report.fuel_per_lap_l
            report.total_fuel_needed_l = race_laps * report.fuel_per_lap_l + safety

            max_fuel = report.fuel_capacity_l
            laps_per_tank = int((max_fuel - safety) / report.fuel_per_lap_l)

            if laps_per_tank >= race_laps:
                report.num_stops = 0
                report.findings.append(
                    f"No pit stop needed! {max_fuel:.1f} L covers {race_laps} laps "
                    f"(need {report.total_fuel_needed_l:.1f} L)."
                )
                report.finish_fuel_l = max_fuel - report.total_fuel_needed_l
            else:
                report.num_stops = max(1, -(-race_laps // laps_per_tank) - 1)
                laps_per_stint = race_laps // (report.num_stops + 1)
                remainder = race_laps - laps_per_stint * (report.num_stops + 1)

                # Distribute laps evenly across stints
                stints = [laps_per_stint] * (report.num_stops + 1)
                for i in range(remainder):
                    stints[i] += 1

                cumulative = 0
                for i, stint_laps in enumerate(stints[:-1]):
                    cumulative += stint_laps
                    report.pit_laps.append(cumulative)
                    fuel_needed = stints[i + 1] * report.fuel_per_lap_l + safety
                    report.fuel_per_stop_l.append(round(fuel_needed, 1))

                report.finish_fuel_l = max_fuel - stints[-1] * report.fuel_per_lap_l - safety

                report.findings.append(
                    f"Race strategy: {report.num_stops} stop(s) for {race_laps} laps. "
                    f"Pit on lap(s): {', '.join(str(l) for l in report.pit_laps)}."
                )
                for i, (pl, fl) in enumerate(zip(report.pit_laps, report.fuel_per_stop_l)):
                    report.findings.append(f"  Stop {i+1} (lap {pl}): add {fl:.1f} L.")

        return report
