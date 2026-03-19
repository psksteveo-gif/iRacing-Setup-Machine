"""
Telemetry Analysis Engine
Analyzes TelemetryData and produces categorized issues with recommendations.
"""

import numpy as np
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from core.ibt_parser import TelemetryData  # type: ignore[import-unresolved]
from core.car_classifier import classify_car, CarClass, PRESSURE_TARGETS, PRESSURE_RISE

# ── Analysis thresholds (tunable) ─────────────────────────────────────────
TIRE_OVERHEAT_BASE_C = 100       # avg tire temp above this → warning (at 25°C air)
TIRE_OVERHEAT_SCALE = 0.4        # overheat threshold rises this many °C per 1°C air temp above 25
TIRE_SPREAD_C = 12               # inner-outer temp spread → uneven wear
PRESSURE_HIGH_PSI = 27.5         # hot pressure above this → info
HEAVY_BRAKE_THRESHOLD = 0.8      # brake input fraction considered "heavy"
HEAVY_BRAKE_PCT = 15             # % of session in heavy braking → warning
STEERING_CORNER_THRESHOLD = 0.1  # abs steering to count as "cornering"
BALANCE_UNDERSTEER_RATIO = 3.0   # lat/steer ratio below this → understeer
BALANCE_OVERSTEER_RATIO = 8.0    # lat/steer ratio above this → oversteer
BALANCE_ISSUE_THRESHOLD = 0.15   # abs score above this → issue reported
BRAKE_ENTRY_THRESHOLD = 0.1      # brake > this → trail-brake entry
THROTTLE_MID_THRESHOLD = 0.3     # throttle < this + brake < entry → mid-corner
THROTTLE_EXIT_THRESHOLD = 0.3    # throttle > this → power-on exit
FUEL_HIGH_L_PER_LAP = 4.5       # fuel/lap above this → info
CONSISTENCY_WARNING_STD = 1.5    # lap-time std above this → warning
CONSISTENCY_EXCELLENT_STD = 0.3  # lap-time std below this → info
GRIP_UTIL_FRACTION = 0.70        # fraction of max G for "utilized" threshold
GRIP_LOW_PCT = 30                # grip util % below this → info
BOTTOMING_RANGE_FRACTION = 0.05  # shock near min within this fraction → bottom
BOTTOMING_WARN_PCT = 5           # bottoming % above this → warning
ASYMMETRY_RATIO = 0.3            # avg deflection diff / range → asymmetry
RPM_PERCENTILE = 99.5            # percentile for "max RPM" estimate
RPM_LIMITER_FRACTION = 0.98      # RPM fraction above this → at limiter
RPM_LIMITER_WARN_PCT = 3         # limiter % above this → warning
UPSHIFT_LOW_PCT = 85             # avg upshift below this % of max → info
IQR_MULTIPLIER = 1.5             # IQR fence multiplier for outlier detection
IQR_MIN_SPREAD = 0.5             # min IQR floor for tight distributions
WARMUP_INLAP_FACTOR = 1.07      # first/last lap > median * this → outlier


def set_outlier_factor(factor: float) -> None:
    """Update the warmup/in-lap outlier threshold at runtime (from user settings)."""
    global WARMUP_INLAP_FACTOR
    WARMUP_INLAP_FACTOR = max(1.01, min(1.30, float(factor)))
DOWNSAMPLE_CHART = 2000          # max points for full-session charts
DOWNSAMPLE_LAP = 1500            # max points for per-lap overlays


class Severity(Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class Category(Enum):
    TIRES = "Tires"
    BRAKES = "Brakes"
    SUSPENSION = "Suspension"
    AERO = "Aero"
    DRIVING = "Driving"
    FUEL = "Fuel"
    GENERAL = "General"


@dataclass
class Issue:
    severity: Severity
    category: Category
    title: str
    description: str
    recommendation: str


@dataclass
class AnalysisReport:
    best_lap: float = 0.0
    avg_lap: float = 0.0
    lap_times: List[float] = field(default_factory=list)
    critical_count: int = 0
    warning_count: int = 0
    info_count: int = 0
    balance_score: float = 0.0  # -1 understeer, +1 oversteer
    tire_summary: Optional[Dict[str, Dict[str, float]]] = None
    issues: List[Issue] = field(default_factory=list)
    # G-G / grip utilization
    grip_utilization_pct: float = 0.0      # how much of friction circle is used
    max_lat_g: float = 0.0
    max_long_g: float = 0.0
    max_combined_g: float = 0.0
    # Suspension
    suspension_summary: Optional[Dict[str, Dict[str, float]]] = None  # corner -> {avg, min, max, range, bottoming_pct}
    # RPM / Shifting
    avg_upshift_rpm_pct: float = 0.0       # % of max RPM at upshift
    rev_limiter_pct: float = 0.0           # % of time at rev limiter
    gear_changes_per_lap: float = 0.0
    # Corner-phase balance
    balance_entry: float = 0.0    # -1 understeer, +1 oversteer (trail-brake phase)
    balance_mid: float = 0.0      # mid-corner (coasting / light inputs)
    balance_exit: float = 0.0     # power-on phase
    # Outlier filtering
    valid_lap_mask: List[bool] = field(default_factory=list)  # True = valid, False = outlier
    outlier_count: int = 0
    # Per-lap balance timeline (one score per lap, + oversteer / - understeer)
    balance_timeline: List[float] = field(default_factory=list)
    # Detected car class
    car_class: str = "default"

    def add_issue(self, severity: Severity, category: Category,
                  title: str, description: str, recommendation: str):
        self.issues.append(Issue(severity, category, title, description, recommendation))
        if severity == Severity.CRITICAL:
            self.critical_count += 1
        elif severity == Severity.WARNING:
            self.warning_count += 1
        else:
            self.info_count += 1


def format_laptime(s: float) -> str:
    """Format seconds as M:SS.sss, or '--:--.---' if invalid."""
    if s <= 0:
        return "--:--.---"
    m, sec = divmod(s, 60)
    return f"{int(m)}:{sec:06.3f}"


class AnalysisEngine:
    """Analyze telemetry data and produce a diagnostic report."""

    def __init__(self):
        pass

    def analyze(self, data: TelemetryData) -> AnalysisReport:
        """Run all analysis passes on telemetry data and return a diagnostic report."""
        report = AnalysisReport()
        report.lap_times = list(data.lap_times)
        self._session_info = data.session_info or {}
        self._car_class = classify_car(data.car_name)
        report.car_class = self._car_class.value

        if data.num_laps > 0:
            # Outlier detection: exclude warmup, in/out laps, and incident laps
            report.valid_lap_mask = self._detect_outliers(data.lap_times)
            # Refine with OnPitRoad channel: any lap that spent >20% time on pit road is invalid
            pit_ch = data.get_channel('OnPitRoad')
            if pit_ch is not None and len(data.lap_boundaries) > data.num_laps:
                for li in range(data.num_laps):
                    s = data.lap_boundaries[li]; e = data.lap_boundaries[li + 1]
                    lap_pit = pit_ch[s:e]
                    if len(lap_pit) > 0 and float(np.mean(lap_pit > 0)) > 0.20:
                        report.valid_lap_mask[li] = False
            valid_times = [t for t, v in zip(data.lap_times, report.valid_lap_mask) if v]
            report.outlier_count = sum(1 for v in report.valid_lap_mask if not v)
            if valid_times:
                report.best_lap = min(valid_times)
                report.avg_lap = float(np.mean(valid_times))
            else:
                report.best_lap = min(data.lap_times)
                report.avg_lap = float(np.mean(data.lap_times))

        self._analyze_tires(data, report)
        self._analyze_brakes(data, report)
        self._analyze_balance(data, report)
        self._analyze_fuel(data, report)
        self._analyze_consistency(data, report)
        self._analyze_grip(data, report)
        self._analyze_suspension(data, report)
        self._analyze_shifts(data, report)
        self._analyze_weather(data, report)
        self._analyze_wind(data, report)
        report.balance_timeline = self._compute_lap_balance_timeline(data)

        return report

    def _is_wet(self) -> bool:
        """Return True if the session has wet/rain conditions."""
        weather = str(self._session_info.get('weather_type', '')).lower()
        skies = str(self._session_info.get('skies', '')).lower()
        return any(w in weather or w in skies for w in ('rain', 'wet', 'storm', 'drizzle'))

    def _tire_overheat_threshold(self) -> float:
        """Return the overheat temperature threshold, adjusted for ambient and weather."""
        air_temp = self._session_info.get('air_temp_c')
        base = TIRE_OVERHEAT_BASE_C
        if air_temp is not None:
            base = TIRE_OVERHEAT_BASE_C + TIRE_OVERHEAT_SCALE * (air_temp - 25.0)
        # Wet conditions cool tires significantly
        if self._is_wet():
            base -= 15.0
        return base

    def _pressure_suggestion(self) -> str:
        """Return ambient-aware cold pressure advice."""
        air_temp = self._session_info.get('air_temp_c')
        if air_temp is not None and air_temp > 32:
            return "Lower cold pressures by 0.5-1.0 psi (hot ambient conditions)."
        if air_temp is not None and air_temp < 18:
            return "Raise cold pressures by 0.5-1.0 psi (cold ambient conditions)."
        return ""

    def _analyze_tires(self, data: TelemetryData, report: AnalysisReport):
        """Analyze tire temperatures and pressures."""
        tire_summary = {}
        corners = ['LF', 'RF', 'LR', 'RR']
        for corner in corners:
            inner = data.get_channel(f'{corner}tempCL')
            mid = data.get_channel(f'{corner}tempCM')
            outer = data.get_channel(f'{corner}tempCR')
            if inner is not None and mid is not None and outer is not None:
                tire_summary[corner] = {
                    'inner': float(np.mean(inner)),
                    'mid': float(np.mean(mid)),
                    'outer': float(np.mean(outer)),
                    'avg': float(np.mean([np.mean(inner), np.mean(mid), np.mean(outer)])),
                }

        if tire_summary:
            report.tire_summary = tire_summary
            overheat_c = self._tire_overheat_threshold()

            # Check for overheating (threshold scaled by ambient temp)
            for corner, temps in tire_summary.items():
                if temps['avg'] > overheat_c:
                    rec = (
                        f"Primary fix: increase {corner} cold pressure by 0.5–1.0 psi to reduce sidewall flex and heat buildup. "
                        f"Also consider reducing {corner} camber by 0.2–0.5° — excessive negative camber raises inner-edge temps. "
                        "If the whole axle is overheating, the compound may be too soft for this track surface; check brake duct sizing too. "
                        "Overheating accelerates wear and causes sudden grip loss — address before a long stint."
                    )
                    pressure_hint = self._pressure_suggestion()
                    if pressure_hint:
                        rec += f" Additional note: {pressure_hint}"
                    report.add_issue(Severity.WARNING, Category.TIRES,
                        f"{corner} Tire Overheating",
                        f"{corner} average temp {temps['avg']:.1f}°C exceeds optimal range "
                        f"(threshold {overheat_c:.0f}°C for current conditions). "
                        "Overheated tires lose grip rapidly and degrade faster, leading to increasing lap times.",
                        rec)

                # Check for uneven wear (inner vs outer spread)
                spread = abs(temps['inner'] - temps['outer'])
                if spread > TIRE_SPREAD_C:
                    if temps['inner'] > temps['outer']:
                        cause = "inner hotter than outer — too much negative camber or excessive toe-in is overloading the inner edge"
                        fix = (
                            f"Reduce {corner} camber by 0.3–0.5° and check toe alignment. "
                            "Uneven loading causes premature inner-edge wear and inconsistent mid-corner grip."
                        )
                    else:
                        cause = "outer hotter than inner — insufficient negative camber or bump causing outside-edge scrub"
                        fix = (
                            f"Increase {corner} negative camber by 0.3–0.5°. "
                            "Also check that the suspension isn't bottoming bump stops in hard corners, which can momentarily flatten camber."
                        )
                    report.add_issue(Severity.WARNING, Category.TIRES,
                        f"{corner} Uneven Tire Wear",
                        f"{corner} inner-outer temp spread is {spread:.1f}°C ({cause}). "
                        "Uneven temps mean only part of the contact patch is working — grip and life are both compromised.",
                        fix)

        # Ambient-aware pressure advice (general)
        pressure_hint = self._pressure_suggestion()
        if pressure_hint and tire_summary:
            report.add_issue(Severity.INFO, Category.TIRES,
                "Ambient Temperature Advisory",
                f"Air temp is {self._session_info.get('air_temp_c', 0):.0f}°C.",
                pressure_hint)

        # Pressure analysis — car-class-aware targets
        cold_targets = PRESSURE_TARGETS.get(self._car_class, PRESSURE_TARGETS[CarClass.DEFAULT])
        rise = PRESSURE_RISE.get(self._car_class, PRESSURE_RISE[CarClass.DEFAULT])
        tolerance = 1.5  # psi band around expected hot pressure
        for corner in corners:
            press = data.get_channel(f'{corner}press')
            if press is not None:
                avg_press = float(np.mean(press[-len(press)//4:]))  # last quarter (hot)
                target_hot = cold_targets.get(corner, 32.0) + rise
                if avg_press > target_hot + tolerance:
                    delta = avg_press - target_hot
                    report.add_issue(Severity.INFO, Category.TIRES,
                        f"{corner} Pressure High",
                        f"{corner} hot pressure {avg_press:.1f} psi "
                        f"(target ~{target_hot:.1f} psi for {self._car_class.value.upper()}, "
                        f"+{delta:.1f} psi over). "
                        "High pressure reduces the contact patch size, making the tire feel nervous and reducing peak mechanical grip.",
                        f"Lower cold pressure by ~{delta:.1f} psi before next session. "
                        "If pressures are consistently rising far above target, check for overheating — heat drives pressure up. "
                        "Measure cold-to-hot rise across multiple laps to ensure it stabilises.")
                elif avg_press < target_hot - tolerance:
                    delta = target_hot - avg_press
                    report.add_issue(Severity.INFO, Category.TIRES,
                        f"{corner} Pressure Low",
                        f"{corner} hot pressure {avg_press:.1f} psi "
                        f"(target ~{target_hot:.1f} psi for {self._car_class.value.upper()}, "
                        f"{delta:.1f} psi under). "
                        "Low pressure increases sidewall flex, generating excess heat and risking tire rollover off the rim on kerbs.",
                        f"Raise cold pressure by ~{delta:.1f} psi. "
                        "If tires aren't reaching target despite higher cold pressures, they may not be reaching temperature — check if tires need more heat cycles or a softer compound.")

    def _compute_lap_balance_timeline(self, data: TelemetryData) -> List[float]:
        """
        Compute a balance score for each lap.
        Returns a list with one float per lap:  -1 = strong understeer, +1 = strong oversteer.
        """
        lat = data.get_channel('LatAccel')
        steering = data.get_channel('SteeringWheelAngle')
        if lat is None or steering is None or data.num_laps == 0:
            return []

        scores: List[float] = []
        for i in range(data.num_laps):
            if i + 1 >= len(data.lap_boundaries):
                break
            s = data.lap_boundaries[i]
            e = data.lap_boundaries[i + 1]
            lat_sl = lat[s:e]
            steer_sl = steering[s:e]
            if len(lat_sl) < 60:
                scores.append(0.0)
                continue
            corner_mask = np.abs(steer_sl) > STEERING_CORNER_THRESHOLD
            if not np.any(corner_mask):
                scores.append(0.0)
                continue
            avg_steer = float(np.mean(np.abs(steer_sl[corner_mask])))
            avg_lat = float(np.mean(np.abs(lat_sl[corner_mask])))
            ratio = avg_lat / max(avg_steer, 0.01)
            if ratio < BALANCE_UNDERSTEER_RATIO:
                score = max(-1.0, -(BALANCE_UNDERSTEER_RATIO - ratio) / BALANCE_UNDERSTEER_RATIO)
            elif ratio > BALANCE_OVERSTEER_RATIO:
                score = min(1.0, (ratio - BALANCE_OVERSTEER_RATIO) / BALANCE_OVERSTEER_RATIO)
            else:
                score = 0.0
            scores.append(round(score, 3))
        return scores

    def _analyze_brakes(self, data: TelemetryData, report: AnalysisReport):
        brake = data.get_channel('Brake')
        speed = data.get_channel('Speed')
        if brake is None or speed is None:
            return

        # Check for brake lock-ups (high brake + very low speed change)
        heavy_brake_mask = brake > HEAVY_BRAKE_THRESHOLD
        if np.any(heavy_brake_mask):
            heavy_pct = np.sum(heavy_brake_mask) / len(brake) * 100
            if heavy_pct > HEAVY_BRAKE_PCT:
                report.add_issue(Severity.WARNING, Category.BRAKES,
                    "Excessive Heavy Braking",
                    f"Heavy braking at max pressure ({heavy_pct:.1f}% of session). "
                    "Sustained max-pressure braking risks flat-spotting tires, overheating brake discs, and skipping past the threshold — all causing longer stopping distances.",
                    "Brake a car-length earlier and apply pressure progressively (squeeze, don't stab). "
                    "This lets you trail off smoothly into the corner, which loads the front tires for better turn-in. "
                    "If braking feels unstable, check brake balance — too much rear bias causes rear lockup and snap. "
                    "Also verify brake duct sizing isn't causing overheating under heavy use.")

    def _analyze_balance(self, data: TelemetryData, report: AnalysisReport):
        lat = data.get_channel('LatAccel')
        steering = data.get_channel('SteeringWheelAngle')
        speed = data.get_channel('Speed')
        brake = data.get_channel('Brake')
        throttle = data.get_channel('Throttle')
        if lat is None or steering is None:
            return

        # Only consider cornering (significant steering input)
        corner_mask = np.abs(steering) > STEERING_CORNER_THRESHOLD
        if not np.any(corner_mask):
            return

        # Global balance (unchanged legacy metric)
        avg_steer = float(np.mean(np.abs(steering[corner_mask])))
        avg_lat = float(np.mean(np.abs(lat[corner_mask])))
        ratio = avg_lat / max(avg_steer, 0.01)

        if ratio < BALANCE_UNDERSTEER_RATIO:
            report.balance_score = -0.4
        elif ratio > BALANCE_OVERSTEER_RATIO:
            report.balance_score = 0.4
        else:
            report.balance_score = 0.0

        # Corner-phase balance: entry / mid / exit
        if brake is None or throttle is None:
            return

        def phase_balance(mask):
            """Compute balance score for a corner phase. Negative = understeer."""
            combined = corner_mask & mask
            if np.sum(combined) < 50:
                return 0.0
            s = float(np.mean(np.abs(steering[combined])))
            l = float(np.mean(np.abs(lat[combined])))
            r = l / max(s, 0.01)
            # Map ratio to score: low ratio → understeer (-), high → oversteer (+)
            if r < BALANCE_UNDERSTEER_RATIO:
                return max(-1.0, -(BALANCE_UNDERSTEER_RATIO - r) / BALANCE_UNDERSTEER_RATIO)
            elif r > BALANCE_OVERSTEER_RATIO:
                return min(1.0, (r - BALANCE_OVERSTEER_RATIO) / BALANCE_OVERSTEER_RATIO)
            return 0.0

        # Entry: braking while cornering (trail-brake zone)
        entry_mask = brake > BRAKE_ENTRY_THRESHOLD
        report.balance_entry = phase_balance(entry_mask)

        # Mid-corner: low brake AND low throttle (coast zone)
        mid_mask = (brake < BRAKE_ENTRY_THRESHOLD) & (throttle < THROTTLE_MID_THRESHOLD)
        report.balance_mid = phase_balance(mid_mask)

        # Exit: throttle on while cornering
        exit_mask = throttle > THROTTLE_EXIT_THRESHOLD
        report.balance_exit = phase_balance(exit_mask)

        # Phase-specific issues
        phases = [
            ('Entry (Trail-Brake)', report.balance_entry),
            ('Mid-Corner', report.balance_mid),
            ('Exit (Power-On)', report.balance_exit),
        ]
        understeer_fixes = {
            'Entry (Trail-Brake)': (
                "The front is not rotating under braking — likely brake bias is too far forward (locking fronts) or the front suspension is too stiff to load properly. "
                "Try: move brake bias 1–2 clicks rearward; soften front ARB by one step; "
                "or check if you're releasing the brake too early (carry more brake pressure into the apex to keep the nose loaded)."
            ),
            'Mid-Corner': (
                "The front loses grip while coasting through the corner — the front can't maintain its cornering load. "
                "Try: soften front spring rate (allows more roll and front-end load); "
                "lower front ride height slightly to improve aero balance; "
                "increase front toe-out by a small amount to sharpen turn-in; "
                "or reduce front bump damping so the tire can better follow track surface."
            ),
            'Exit (Power-On)': (
                "Power-on understeer means the front can't match the rear's traction — common in FWD and balanced AWD/RWD. "
                "Try: soften front ARB (allows the front to roll and load the outer front tire); "
                "increase front wing/splitter for more front downforce; "
                "reduce diff power ramp so the rear doesn't overpower the front; "
                "or delay throttle application slightly until the car is pointing straighter."
            ),
        }
        oversteer_fixes = {
            'Entry (Trail-Brake)': (
                "Rear is stepping out under braking — typically brake bias is too rearward or the rear is too stiff to absorb load transfer. "
                "Try: move brake bias 1–2 clicks forward; stiffen front ARB to shift roll resistance to the front; "
                "soften rear rebound damping so the rear settles faster under braking; "
                "or add rear toe-in slightly for stability under braking."
            ),
            'Mid-Corner': (
                "Mid-corner oversteer suggests the rear is losing grip while the car arcs through — often from rear stiffness or low rear downforce. "
                "Try: soften rear ARB (allows more rear roll to load the outer rear tire); "
                "increase rear wing for more rear downforce; "
                "raise rear ride height slightly; "
                "or check rear tire temperatures — an overheated rear is a key cause of mid-corner rotation."
            ),
            'Exit (Power-On)': (
                "Power oversteer — rear breaks away as throttle is applied. Common causes: rear ARB too stiff, diff too locked on power, or insufficient rear downforce. "
                "Try: soften rear ARB by one step; reduce diff power ramp/coast ramp; "
                "add rear wing angle; "
                "or apply throttle earlier and more progressively — a smooth squeeze avoids the initial snap."
            ),
        }

        for name, score in phases:
            if score < -BALANCE_ISSUE_THRESHOLD:
                report.add_issue(Severity.INFO, Category.SUSPENSION,
                    f"Understeer on {name}",
                    f"The car shows understeer during {name.lower()} (score {score:.2f}). "
                    "Understeer at this phase means the front tires are working harder than the rear, reducing rotation and requiring more steering angle — which costs time.",
                    understeer_fixes.get(name, "Adjust setup balance toward the rear."))
            elif score > BALANCE_ISSUE_THRESHOLD:
                report.add_issue(Severity.INFO, Category.SUSPENSION,
                    f"Oversteer on {name}",
                    f"The car shows oversteer during {name.lower()} (score {score:+.2f}). "
                    "Oversteer at this phase means the rear is rotating more than the front — controllable in small amounts but unpredictable under pressure and costs time when correcting.",
                    oversteer_fixes.get(name, "Adjust setup balance toward the front."))

    def _analyze_fuel(self, data: TelemetryData, report: AnalysisReport):
        fuel = data.get_channel('FuelLevel')
        if fuel is None or data.num_laps < 2:
            return

        # Use lap boundaries for accurate start/end fuel (avoids pit/warmup noise)
        if data.lap_boundaries and len(data.lap_boundaries) >= 2:
            start_fuel = float(fuel[data.lap_boundaries[0]])
            end_fuel = float(fuel[data.lap_boundaries[-1] - 1])
        else:
            start_fuel = float(fuel[0])
            end_fuel = float(fuel[-1])
        fuel_used = start_fuel - end_fuel
        fuel_per_lap = fuel_used / max(data.num_laps, 1)

        if fuel_per_lap > FUEL_HIGH_L_PER_LAP:
            report.add_issue(Severity.INFO, Category.FUEL,
                "High Fuel Consumption",
                f"Using {fuel_per_lap:.2f} L/lap — higher than typical range. "
                "High fuel use forces more pit stops or earlier stops, which can cost 20–30+ seconds in race strategy. "
                "A heavier fuel load also adds understeer and increases tire wear.",
                "Techniques to reduce consumption: "
                "(1) Short-shift 500–1000 RPM earlier on long straights — loses minimal time but saves fuel; "
                "(2) Lift-and-coast 50–100m before braking zones (release throttle fully, then brake) — effective on high-speed entries; "
                "(3) Avoid sitting at the rev limiter — every second there wastes fuel with no speed gain; "
                "(4) Use the highest gear possible through medium-speed corners to reduce RPM. "
                "Target: reduce by 0.2–0.4 L/lap to gain a full extra lap on a tank.")

    def _analyze_consistency(self, data: TelemetryData, report: AnalysisReport):
        if data.num_laps < 3:
            return

        # Use only valid laps (exclude warmup, in/out, outliers)
        valid = [t for t, v in zip(data.lap_times, report.valid_lap_mask) if v] \
                if report.valid_lap_mask else list(data.lap_times)
        if len(valid) < 3:
            return

        times = np.array(valid)
        std = float(np.std(times))
        if std > CONSISTENCY_WARNING_STD:
            report.add_issue(Severity.WARNING, Category.DRIVING,
                "Inconsistent Lap Times",
                f"Lap time std deviation is {std:.2f}s — significant variation between laps. "
                "Inconsistency usually means the car is at the limit in some areas and not in others — making it hard to trust the setup feedback or predict tire wear.",
                "Most common causes: (1) Changing brake points lap-to-lap — pick a fixed physical marker (post, curb patch) for each brake zone; "
                "(2) Inconsistent corner entry speed — especially in slow corners where small differences amplify through the entire corner; "
                "(3) Tire temperature swings — check if you're doing cool-down laps between push laps; "
                "(4) Track evolution — if the track is rubbering in, lap times should naturally drop; filter those laps out and check consistency within a block. "
                "Aim to reduce std below 0.8s before chasing outright pace.")
        elif std < CONSISTENCY_EXCELLENT_STD:
            report.add_issue(Severity.INFO, Category.DRIVING,
                "Excellent Consistency",
                f"Lap time std deviation is only {std:.2f}s — very consistent driving. "
                "This level of consistency means your setup feedback is reliable and tire wear will be predictable.",
                "Now focus on finding time: check the Sectors tab for your weakest sector, then use the Corners tab to identify which specific corner is costing the most. "
                "Small improvements at high-speed corners (higher minimum speed) usually give more reward than slow corners. "
                "Consider comparing to a reference lap with the AI Advisor for targeted coaching.")

    def _analyze_grip(self, data: TelemetryData, report: AnalysisReport):
        """G-G diagram / friction circle grip utilization analysis."""
        lat = data.get_channel('LatAccel')
        lon = data.get_channel('LongAccel')
        speed = data.get_channel('Speed')
        if lat is None or lon is None:
            return

        # Only analyze when moving (>15 m/s ≈ 54 km/h)
        moving = speed > 15 if speed is not None else np.ones(len(lat), dtype=bool)
        lat_m = lat[moving]
        lon_m = lon[moving]

        if len(lat_m) < 100:
            return

        combined = np.sqrt(lat_m**2 + lon_m**2)
        report.max_lat_g = float(np.percentile(np.abs(lat_m), 99))
        report.max_long_g = float(np.percentile(np.abs(lon_m), 99))
        report.max_combined_g = float(np.percentile(combined, 99))

        # Grip utilization: % of samples above 70% of the max friction circle
        if report.max_combined_g > 0.1:
            threshold = report.max_combined_g * GRIP_UTIL_FRACTION
            report.grip_utilization_pct = float(np.mean(combined > threshold) * 100)

        if report.grip_utilization_pct < GRIP_LOW_PCT:
            report.add_issue(Severity.INFO, Category.DRIVING,
                "Low Grip Utilization",
                f"Only {report.grip_utilization_pct:.0f}% of the available friction circle is being used. "
                "The tire can handle a combination of lateral and longitudinal G simultaneously — leaving grip unused means leaving cornering speed or braking performance on the table.",
                "Key techniques to fill the friction circle: "
                "(1) Trail braking — carry brake pressure into the corner so you're combining lateral and longitudinal G at entry instead of transitioning from one to the other; "
                "(2) Earlier throttle — begin squeezing the throttle before the apex so longitudinal G overlaps with lateral G on exit; "
                "(3) Higher minimum corner speeds — if you're not using full lateral G through mid-corner, you're slowing down too much on entry. "
                "Check the G-G diagram tab to see which quadrants are underfilled.")

    def _analyze_suspension(self, data: TelemetryData, report: AnalysisReport):
        """Analyze shock deflection for bottoming, asymmetry, and travel range."""
        corners = {'LF': 'LFshockDefl', 'RF': 'RFshockDefl',
                   'LR': 'LRshockDefl', 'RR': 'RRshockDefl'}
        summary = {}
        for corner, ch in corners.items():
            arr = data.get_channel(ch)
            if arr is None or len(arr) < 100:
                continue
            mn, mx = float(np.min(arr)), float(np.max(arr))
            rng = mx - mn
            # Bottoming: samples at or near minimum deflection
            bottom_threshold = mn + rng * BOTTOMING_RANGE_FRACTION
            bottoming_pct = float(np.mean(arr <= bottom_threshold) * 100)
            summary[corner] = {
                'avg': float(np.mean(arr)), 'min': mn, 'max': mx,
                'range': rng, 'bottoming_pct': bottoming_pct,
            }
            if bottoming_pct > BOTTOMING_WARN_PCT:
                report.add_issue(Severity.WARNING, Category.SUSPENSION,
                    f"{corner} Bottoming Out",
                    f"{corner} shock near full compression {bottoming_pct:.1f}% of the time (range: {rng:.1f}mm). "
                    "Bottoming causes a sudden loss of aero platform (underbody suction collapses), unpredictable handling on kerbs, and potential floor/splitter damage.",
                    f"Options in order of preference: "
                    f"(1) Raise {corner} ride height by 2–3mm — most effective with least side-effect; "
                    f"(2) Stiffen {corner} slow-bump damping — reduces dive without changing spring rate; "
                    f"(3) Add a progressive bump stop or shorten the bump stop gap — reduces impact harshness; "
                    f"(4) Increase {corner} spring rate — last resort as it increases stiffness everywhere. "
                    "Confirm the fix by checking that bottoming_pct drops below 2% in next session.")

        if summary:
            report.suspension_summary = summary
            # Check front-rear roll asymmetry
            for side in [('LF', 'RF'), ('LR', 'RR')]:
                if side[0] in summary and side[1] in summary:
                    diff = abs(summary[side[0]]['avg'] - summary[side[1]]['avg'])
                    total_range = max(summary[side[0]]['range'], summary[side[1]]['range'], 0.01)
                    if diff / total_range > ASYMMETRY_RATIO:
                        report.add_issue(Severity.INFO, Category.SUSPENSION,
                            f"{side[0]}/{side[1]} Asymmetric Travel",
                            f"{side[0]} vs {side[1]} average deflection differs by {diff:.2f}mm. "
                            "Asymmetric suspension travel means the car is riding unevenly side-to-side, which skews the balance and can make the car behave differently in left vs right corners.",
                            "Investigate: "
                            "(1) Corner weights — run a corner-weight check to ensure left/right balance is within spec; "
                            "(2) ARB preload — anti-roll bar preload can create static asymmetry; set to neutral first; "
                            "(3) Spring perch settings — verify both sides of the axle are set to the same ride height; "
                            "(4) Tire wear — a significantly worn tire on one side reduces effective spring rate. "
                            "Fixing asymmetry usually improves both left and right corner feel simultaneously.")

    def _analyze_shifts(self, data: TelemetryData, report: AnalysisReport):
        """Analyze RPM at upshift, rev limiter time, and gear changes."""
        rpm = data.get_channel('RPM')
        gear = data.get_channel('Gear')
        if rpm is None or gear is None or len(rpm) < 100:
            return

        max_rpm = float(np.percentile(rpm, RPM_PERCENTILE))
        if max_rpm < 100:
            return

        # Detect upshifts: gear increases by 1
        gear_diff = np.diff(gear)
        upshift_idx = np.where(gear_diff == 1)[0]

        if len(upshift_idx) > 2:
            upshift_rpms = rpm[upshift_idx]
            avg_shift_rpm = float(np.mean(upshift_rpms))
            report.avg_upshift_rpm_pct = avg_shift_rpm / max_rpm * 100

            if report.avg_upshift_rpm_pct < UPSHIFT_LOW_PCT:
                report.add_issue(Severity.INFO, Category.DRIVING,
                    "Early Upshifts",
                    f"Average upshift at {report.avg_upshift_rpm_pct:.0f}% of max RPM ({avg_shift_rpm:.0f}/{max_rpm:.0f}). "
                    "Shifting too early leaves power on the table — you're upshifting before the engine reaches its peak torque/power output, reducing acceleration out of corners and on straights.",
                    "Most cars produce peak power at 92–97% of their max RPM. "
                    "Shift at or just above the power peak for best acceleration. "
                    "Check the engine's power curve: if it's a flat torque curve, shifting early is less costly — but if the engine is peaky (like a naturally-aspirated Formula car), shifting early is very expensive. "
                    "Exception: on fuel-saving laps, short-shifting 500–1000 RPM earlier can save significant fuel with minimal time loss.")

        # Rev limiter time
        limiter_threshold = max_rpm * RPM_LIMITER_FRACTION
        report.rev_limiter_pct = float(np.mean(rpm > limiter_threshold) * 100)
        if report.rev_limiter_pct > RPM_LIMITER_WARN_PCT:
            report.add_issue(Severity.WARNING, Category.DRIVING,
                "Excessive Rev Limiter",
                f"Spending {report.rev_limiter_pct:.1f}% of the session bouncing off the rev limiter. "
                "While at the limiter the engine is cutting fuel/spark and producing no additional power — this is dead time that wastes fuel and stresses the drivetrain.",
                "Upshift slightly earlier on long straights — the time lost to a fractionally lower RPM in the next gear is far less than the time lost sitting on the limiter. "
                "If the limiter hits at corner exit, you may be short on gear ratios for this track; check if final drive or individual gear ratios can be lengthened. "
                "For ovals: brief limiter contact at top speed may be unavoidable — focus on approach angle instead.")

        # Gear changes per lap
        total_changes = int(np.sum(np.abs(gear_diff) > 0))
        report.gear_changes_per_lap = total_changes / max(data.num_laps, 1)

    @staticmethod
    def _detect_outliers(lap_times: list) -> list:
        """Mark outlier laps (warmup, in/out, incidents). Returns list of bools."""
        if len(lap_times) < 3:
            return [True] * len(lap_times)
        times = np.array(lap_times)
        median = np.median(times)
        # First lap is often a warmup / out-lap
        mask = [True] * len(lap_times)
        # IQR-based detection
        q1, q3 = np.percentile(times, [25, 75])
        iqr = q3 - q1
        lower = q1 - IQR_MULTIPLIER * max(iqr, IQR_MIN_SPREAD)
        upper = q3 + IQR_MULTIPLIER * max(iqr, IQR_MIN_SPREAD)
        for i, t in enumerate(lap_times):
            if t < lower or t > upper:
                mask[i] = False
            # First lap: flag if >107% of median (common warmup threshold)
            if i == 0 and t > median * WARMUP_INLAP_FACTOR:
                mask[i] = False
            # Last lap: flag if >107% of median (often in-lap)
            if i == len(lap_times) - 1 and t > median * WARMUP_INLAP_FACTOR:
                mask[i] = False
        return mask

    def _analyze_weather(self, data: TelemetryData, report: AnalysisReport):
        """Generate weather-specific findings and recommendations."""
        if self._is_wet():
            report.add_issue(Severity.WARNING, Category.GENERAL,
                "Wet Conditions Detected",
                "Session is running in rain/wet conditions. Grip is reduced by 30–50% and the car's balance and limits change dramatically.",
                "Setup changes: lower tire pressures by 1–2 psi (softer sidewall improves aquaplaning resistance); "
                "reduce camber by 0.3–0.5° per corner (more flat contact patch in lower grip); "
                "lower front/rear wing angles if adjustable — drag costs more relative to downforce in the wet; "
                "increase traction control and ABS sensitivity if available. "
                "Driving changes: brake earlier with lighter initial pressure (smooth threshold, not hard stab); "
                "stay off kerbs — they're extremely slippery; "
                "look for the dry line forming mid-session and transition onto it progressively.")
            report.add_issue(Severity.INFO, Category.TIRES,
                "Wet Tire Temperature Note",
                "Tires run much cooler in the wet — water constantly cools the surface, so overheat thresholds have been lowered for this session.",
                "In the wet, the biggest risk is aquaplaning (tire riding on a film of water). "
                "Smooth, progressive inputs are critical — sudden throttle, brake, or steering inputs break traction instantly. "
                "If the car feels loose, try scrubbing the tire gently to generate heat early in the lap.")

        # Day/night temperature note
        air_temp = self._session_info.get('air_temp_c')
        track_temp = self._session_info.get('track_temp_c')
        if air_temp is not None and track_temp is not None:
            delta = track_temp - air_temp
            if delta < 2.0 and air_temp < 20:
                report.add_issue(Severity.INFO, Category.TIRES,
                    "Cool Track / Night Conditions",
                    f"Track temp ({track_temp:.0f}°C) is close to air temp ({air_temp:.0f}°C) — "
                    "suggests evening, night, or overcast conditions. Cold tracks take much longer for tires to reach their operating window.",
                    "Raise cold pressures by 0.5–1.0 psi to compensate for lower heat generation. "
                    "Do 2–3 extra warm-up laps weaving and braking hard to generate tire heat before pushing. "
                    "Expect more understeer early in stints as cold fronts won't respond as quickly. "
                    "Setup tip: slightly stiffer springs can help in cold conditions because the tire sidewall is already doing more work — removing spring stiffness risks unpredictable mid-corner flex.")

    def _analyze_wind(self, data: TelemetryData, report: AnalysisReport):
        """Generate wind-related findings when significant wind is present."""
        wind_speed = self._session_info.get('wind_speed_ms')
        wind_dir = self._session_info.get('wind_direction_deg')
        if wind_speed is None or wind_speed < 3.0:
            return

        desc = f"Wind: {wind_speed:.1f} m/s"
        if wind_dir is not None:
            compass = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
            idx = int((wind_dir + 22.5) % 360 / 45)
            desc += f" from {compass[idx]} ({wind_dir:.0f}°)"

        severity = Severity.WARNING if wind_speed > 8.0 else Severity.INFO
        report.add_issue(severity, Category.AERO,
            "Significant Wind",
            f"{desc}. Wind directly affects straight-line speed, braking points, and aero balance lap-to-lap.",
            "Tactical notes: headwind on the main straight costs more in braking distance (slower speed = less aero bite on entry) and lap time; "
            "tailwind helps top speed but can make the car feel light at high speed — add rear wing if unstable. "
            "Crosswind: the car will push or pull through fast corners and on straight-line braking. "
            "Setup tip: if the wind is consistent (not gusty), you can optimise wing for the predominant direction. "
            "If gusty/variable, set a conservative (more downforce) baseline so the car stays consistent.")
