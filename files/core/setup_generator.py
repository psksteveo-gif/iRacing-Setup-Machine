"""
setup_generator.py — Optimal Sector Setup Generator
=====================================================

The core engine that turns IBT telemetry signals into a legal, personalized
setup file with a plain-language driver brief.

Architecture
------------
1. IBTSignalExtractor   — reads AnalysisReport + CornerAnalysisReport and
                          produces a structured SignalBundle of driver/car signals
2. SetupDeltaEngine     — maps signals → parameter deltas using confidence-gated
                          rules. Outputs only changes the data justifies.
3. SetupAssembler       — applies deltas to the baseline setup, clamps every
                          value through tech_inspector, and returns a validated
                          SetupResult with a pass/fail guarantee.
4. BriefGenerator       — produces the AI driver brief from the SetupResult.
   (AI call via ai_advisor — this module stays deterministic)

Usage
-----
    from core.setup_generator import generate_setup

    result = generate_setup(
        analysis=report,
        corner_report=corners,
        style_report=style,
        baseline_setup=parsed_setup,
        car_class=car_class,
        car_name="Porsche 911 Cup (992.2)",
        track_name="Barber Motorsports Park",
    )

    if result.tech_pass:
        # Write result.final_setup to .sto file
        # Show result.driver_brief to driver
        # Show result.changes_table for garage tab walkthrough
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any

from core.tech_inspector import (
    validate_setup, clamp_to_legal, get_bounds,
    ParamBounds, TechIssue, bounds_summary_for_prompt
)
from core.car_classifier import CarClass

logger = logging.getLogger(__name__)


def generate_wet_setup_overlay(
    car_class,
    baseline_setup: dict = None,
    track_wetness: int = 2,
) -> dict:
    """
    Generate a wet/damp condition setup overlay on top of a baseline.

    Unlike the main generate_setup() which makes incremental deltas,
    this produces a full overlay of all parameters that should change
    for wet conditions — independent of session balance data.

    Philosophy: wet setup is NOT just "soften everything".
    Key changes per motorsport engineering practice:
      - ARBs: soften significantly (compliance > stiffness in wet)
      - Springs: soften front more than rear (weight transfer balance)
      - Ride height: raise slightly (aquaplaning margin)
      - Brake bias: forward (rear locks easily in wet)
      - Tire pressure: lower cold start (less heat buildup)
      - Camber: reduce (wider contact patch in wet > heat generation)
      - Downforce: increase if available (wet needs more mechanical load)
      - Dampers: slower rebound (let tire find grip on recovery)

    Parameters
    ----------
    car_class : CarClass or str
    baseline_setup : dict — current dry setup values
    track_wetness : int — 1=damp, 2=wet, 3=very wet

    Returns
    -------
    dict of param → recommended value with 'delta' and 'reason' sub-keys
    """
    from core.tech_inspector import get_bounds, _resolve_car_class

    if not isinstance(car_class, CarClass):
        from core.tech_inspector import _resolve_car_class
        car_class = _resolve_car_class(car_class)

    bounds  = get_bounds(car_class)
    base    = baseline_setup or {}
    overlay = {}

    def _current(param, fallback):
        v = base.get(param)
        if v is not None:
            try: return float(v)
            except: pass
        b = bounds.get(param)
        return (b.min_val + b.max_val) / 2 if b else fallback

    def _clamp(param, value):
        b = bounds.get(param)
        if b:
            return max(b.min_val, min(b.max_val, round(value / b.step) * b.step))
        return value

    # Intensity scales with wetness level
    wet_factor = {1: 0.5, 2: 1.0, 3: 1.35}.get(track_wetness, 1.0)
    condition  = {1: 'Damp', 2: 'Wet', 3: 'Very Wet'}.get(track_wetness, 'Wet')

    # ── ARBs — soften significantly ─────────────────────────────────────────
    for param, baseline_soft, reason in [
        ('arb_front', -2, 'Soft front ARB allows front tires to find grip on wet surface'),
        ('arb_rear',  -2, 'Soft rear ARB prevents snap oversteer on power application in wet'),
    ]:
        cur = _current(param, 4)
        delta = round(-1 * wet_factor * (2 if 'rear' in param else 1.5))
        rec   = _clamp(param, cur + delta)
        if rec != cur:
            overlay[param] = {'current': cur, 'recommended': rec,
                              'delta': rec - cur, 'reason': reason,
                              'condition': condition}

    # ── Brake bias — more forward ────────────────────────────────────────────
    cur_bb = _current('brake_bias', 57.0)
    bb_delta = round(1.5 * wet_factor, 1)
    rec_bb   = _clamp('brake_bias', cur_bb + bb_delta)
    if abs(rec_bb - cur_bb) > 0.2:
        overlay['brake_bias'] = {
            'current': cur_bb, 'recommended': rec_bb,
            'delta': round(rec_bb - cur_bb, 1),
            'reason': 'Rear brakes lock easily in wet — move bias forward to prevent rear lock',
            'condition': condition}

    # ── Tire pressure — lower cold start ────────────────────────────────────
    psi_reduction = round(0.75 * wet_factor, 1)
    for corner in ['lf', 'rf', 'lr', 'rr']:
        param = f'pressure_{corner}'
        cur_p = _current(param, 27.5)
        rec_p = _clamp(param, cur_p - psi_reduction)
        if abs(rec_p - cur_p) > 0.05:
            overlay[param] = {
                'current': cur_p, 'recommended': rec_p,
                'delta': round(rec_p - cur_p, 1),
                'reason': f'Wet tires run cooler — lower cold start pressure '
                          f'to hit target hot pressure range',
                'condition': condition}

    # ── Camber — reduce slightly ─────────────────────────────────────────────
    cam_reduction = round(0.1 * wet_factor, 2)
    for corner, cam_sign in [('camber_lf', -1), ('camber_rf', -1),
                              ('camber_lr', -1), ('camber_rr', -1)]:
        cur_c = _current(corner, -2.5)
        # Reduce magnitude (less negative = wider contact patch)
        rec_c = _clamp(corner, cur_c + cam_reduction)
        if abs(rec_c - cur_c) > 0.05:
            overlay[corner] = {
                'current': cur_c, 'recommended': rec_c,
                'delta': round(rec_c - cur_c, 2),
                'reason': 'Reduce camber in wet — wider contact patch '
                          'more valuable than heat generation',
                'condition': condition}

    # ── Ride height — raise if available ─────────────────────────────────────
    if track_wetness >= 2:
        rh_increase = round(2.0 * wet_factor)
        for rh_param in ['rh_lf', 'rh_rf', 'rh_lr', 'rh_rr']:
            cur_rh = _current(rh_param, 65.0)
            rec_rh = _clamp(rh_param, cur_rh + rh_increase)
            if abs(rec_rh - cur_rh) > 0.5:
                overlay[rh_param] = {
                    'current': cur_rh, 'recommended': rec_rh,
                    'delta': round(rec_rh - cur_rh, 1),
                    'reason': 'Raise ride height in wet — aquaplaning margin '
                              'and allow suspension more travel for compliance',
                    'condition': condition}

    logger.info(
        'Wet overlay generated: %d changes for %s (wetness=%d factor=%.2f)',
        len(overlay), car_class, track_wetness, wet_factor)
    return overlay


# ─────────────────────────────────────────────────────────────────────────────
# DATA STRUCTURES
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CornerSignal:
    """Distilled signal from a specific corner type."""
    name: str
    speed_class: str          # 'slow' | 'medium' | 'fast'
    entry_os: float           # oversteer score at entry (+OS, -US)
    mid_os: float             # oversteer score mid-corner
    exit_os: float            # oversteer score at exit (power-on)
    min_speed_delta: float    # vs reference lap (km/h, negative = slower)
    lap_count: int            # how many laps contributed to this signal
    confidence: float         # 0–1, based on lap_count and signal consistency


@dataclass
class SignalBundle:
    """
    All telemetry signals extracted from IBT that feed into setup decisions.
    Every field has a confidence score — only signals above threshold drive changes.
    """
    # Balance signals
    balance_overall: float = 0.0      # +=OS, -=US, from analysis_engine
    balance_entry: float = 0.0
    balance_mid: float = 0.0
    balance_exit: float = 0.0
    balance_confidence: float = 0.0   # based on lap count

    # Braking signals
    brake_score: float = 0.0          # 0–100, from consistency_score
    brake_bias_direction: str = ""    # 'too_rearward' | 'too_forward' | 'ok'
    brake_bias_confidence: float = 0.0

    # Tire signals
    tire_temps: Dict[str, Dict] = field(default_factory=dict)
    # tire_temps = {'LF': {'inner': x, 'mid': x, 'outer': x, 'avg': x}, ...}
    tire_pressure_hot: Dict[str, float] = field(default_factory=dict)
    # tire_pressure_hot = {'LF': psi, 'RF': psi, ...}
    tire_confidence: float = 0.0

    # Corner-specific signals
    corners: List[CornerSignal] = field(default_factory=list)

    # Consistency signals
    consistency_score: float = 0.0    # 0–100
    lap_time_std: float = 0.0         # seconds
    laps_analyzed: int = 0

    # Suspension signals (from shock channels)
    shock_defl_avg: Dict[str, float] = field(default_factory=dict)   # avg travel mm per corner
    shock_vel_histogram: Dict[str, Dict] = field(default_factory=dict) # LS/HS split
    suspension_confidence: float = 0.0

    # Wheel slip angles (radians, averaged per corner)
    slip_angle_avg: Dict[str, float] = field(default_factory=dict)
    slip_confidence: float = 0.0

    # Traffic detection
    clean_lap_mask: list = field(default_factory=list)  # which laps were traffic-free
    contaminated_laps: int = 0

    # Brake line actual split
    brake_actual_front_pct: Optional[float] = None
    brake_dial_pct: Optional[float] = None

    # Body motion (from YawRate / PitchRate / RollRate channels)
    roll_rate_cornering: float = 0.0
    pitch_rate_braking: float = 0.0
    body_motion_confidence: float = 0.0
    # Tire wear (from LFwearL/M/R channels — ground truth for camber)
    tire_wear: dict = field(default_factory=dict)
    has_wear_data: bool = False
    # Throttle exit understeer
    exit_us_pct: float = 0.0
    has_throttle_data: bool = False
    # Actual ride heights (from LFrideHeight channels)
    ride_heights_mm: dict = field(default_factory=dict)
    has_ride_height_data: bool = False
    # Brake hydraulic actual split vs dial
    hydraulic_front_pct: float = 0.0
    has_brake_hydraulics: bool = False
    brake_hydraulic_discrepancy: float = 0.0
    # Steering torque (understeer load confirmation)
    steering_torque_ratio: float = 0.0
    steering_torque_peak: float = 0.0
    has_steering_torque: bool = False
    # Yaw balance ratio (rotation efficiency)
    yaw_balance_ratio: float = 0.0
    has_yaw_data: bool = False
    # Spring deflection vs shock deflection (bump stop detection)
    spring_defl_avg: dict = field(default_factory=dict)
    bump_stop_engaged: dict = field(default_factory=dict)
    has_spring_defl: bool = False
    fuel_correction_applied: float = 0.0  # OS bias added for fuel load
    # Speed sector analysis (aero rules)
    top_speed_kph: float = 0.0
    slow_corner_pct: float = 0.0
    fast_corner_pct: float = 0.0
    sector_max_speeds: list = field(default_factory=list)
    has_speed_sectors: bool = False

    # Track character
    track_name: str = ""
    track_type: str = "road"          # 'road' | 'oval' | 'dirt'
    has_high_speed_corners: bool = False
    has_slow_corners: bool = False

    # Raw values from current setup (for delta calculation)
    current_setup: Dict[str, Any] = field(default_factory=dict)
    car_name: str = ""
    car_class: Optional[CarClass] = None


@dataclass
class SetupDelta:
    """
    A single justified setup change.
    Contains everything needed for the driver brief and UI display.
    """
    param: str                  # internal key e.g. 'arb_rear'
    display_name: str           # e.g. 'Rear ARB'
    garage_tab: str             # e.g. 'CHASSIS'
    garage_location: str        # e.g. 'Rear section'
    current_value: float
    recommended_value: float    # already clamped to legal range
    delta: float                # recommended - current
    unit: str
    signal_source: str          # which IBT signal triggered this
    confidence: float           # 0–1
    reasoning: str              # one sentence, data-specific
    driver_feel: str            # what the driver will feel
    priority: int               # 1 = most impactful
    clamped: bool = False       # True if value was adjusted to fit legal range
    clamp_note: str = ""        # note shown if clamped


@dataclass
class SetupResult:
    """
    Final output of the setup generator.
    tech_pass is guaranteed True if you use the deltas — the assembler
    runs validate_setup() and blocks any illegal value before returning.
    """
    tech_pass: bool
    tech_issues: List[TechIssue]       # empty if tech_pass is True
    deltas: List[SetupDelta]           # ordered by priority
    final_setup: Dict[str, float]      # full setup dict, safe to write to .sto
    baseline_setup: Dict[str, Any]     # original before changes
    car_name: str
    track_name: str
    car_class: Optional[CarClass]
    laps_analyzed: int
    confidence_overall: float          # 0–1
    driver_brief: str = ""             # populated by BriefGenerator
    changes_table: List[dict] = field(default_factory=list)  # UI-ready rows
    weather_report: Optional[dict] = field(default=None)     # WeatherEngine.condition_report()


# ─────────────────────────────────────────────────────────────────────────────
# SIGNAL THRESHOLDS
# ─────────────────────────────────────────────────────────────────────────────

# Minimum laps before we trust a signal enough to recommend a change
MIN_LAPS_FOR_CHANGE = 3

# Balance score thresholds
# Balance score scale: output of analysis_engine._analyze_balance()
# Range: -1.0 (maximum understeer) to +1.0 (maximum oversteer)
# Derived from: lateral-G / steering-angle ratio, normalised against class bounds
# Calibration basis: lat-G/steer ratio maps ~linearly in iRacing physics.
# 0.15 = ratio 15% beyond the neutral window → detectable, marginal action
# 0.40 = ratio 40% beyond neutral → clear imbalance, confident recommendation
# 0.70 = ratio 70% beyond → severe, high priority
# These values are consistent with iRacing telemetry observations but have
# not been back-tested against a lap time improvement dataset. The Setup
# Learning DB will refine them as outcome data accumulates.
BALANCE_OS_STRONG   =  0.40   # clear oversteer — act with full delta
BALANCE_OS_MILD     =  0.15   # marginal oversteer — small delta, flag for monitoring
BALANCE_US_MILD     = -0.15   # marginal understeer
BALANCE_US_STRONG   = -0.40   # clear understeer
BALANCE_SEVERE      =  0.70   # severe imbalance — flag as critical issue
BALANCE_US_MILD     = -0.15   # mild understeer
BALANCE_US_STRONG   = -0.40   # strong understeer — act on it

# Brake bias indicators
ENTRY_OS_BRAKE_THRESHOLD = 0.50   # entry OS this high → brake bias too rearward
ENTRY_US_BRAKE_THRESHOLD = -0.35  # entry US this high → brake bias too forward

# Tire temp imbalance threshold (°C inner vs outer — indicates camber issue)
TIRE_TEMP_IMBALANCE_C = 15.0

# Minimum confidence to include a delta in the output
MIN_CONFIDENCE = 0.40


# ─────────────────────────────────────────────────────────────────────────────
# GARAGE LOCATION MAP
# ─────────────────────────────────────────────────────────────────────────────

PARAM_GARAGE_INFO: Dict[str, Tuple[str, str]] = {
    # param_key: (tab, location_description)
    "brake_bias":       ("CHASSIS",   "In-Car Adjustments → Brake Pressure Bias"),
    "brake_pressure":   ("CHASSIS",   "In-Car Adjustments → Max Brake Pressure"),
    "arb_front":        ("CHASSIS",   "Front section → Front ARB Setting"),
    "arb_rear":         ("CHASSIS",   "Rear section → Rear ARB Setting"),
    "spring_lf":        ("CHASSIS",   "Left Front corner → Spring Rate"),
    "spring_rf":        ("CHASSIS",   "Right Front corner → Spring Rate"),
    "spring_lr":        ("CHASSIS",   "Left Rear corner → Spring Rate"),
    "spring_rr":        ("CHASSIS",   "Right Rear corner → Spring Rate"),
    "rh_lf":            ("CHASSIS",   "Left Front corner → Ride Height"),
    "rh_rf":            ("CHASSIS",   "Right Front corner → Ride Height"),
    "rh_lr":            ("CHASSIS",   "Left Rear corner → Ride Height"),
    "rh_rr":            ("CHASSIS",   "Right Rear corner → Ride Height"),
    "bump_slow_lf":     ("DAMPERS",   "Left Front → Slow Bump"),
    "bump_slow_rf":     ("DAMPERS",   "Right Front → Slow Bump"),
    "bump_slow_lr":     ("DAMPERS",   "Left Rear → Slow Bump"),
    "bump_slow_rr":     ("DAMPERS",   "Right Rear → Slow Bump"),
    "rebound_slow_lf":  ("DAMPERS",   "Left Front → Slow Rebound"),
    "rebound_slow_rf":  ("DAMPERS",   "Right Front → Slow Rebound"),
    "rebound_slow_lr":  ("DAMPERS",   "Left Rear → Slow Rebound"),
    "rebound_slow_rr":  ("DAMPERS",   "Right Rear → Slow Rebound"),
    "bump_fast_lf":     ("DAMPERS",   "Left Front → Fast Bump"),
    "bump_fast_rf":     ("DAMPERS",   "Right Front → Fast Bump"),
    "bump_fast_lr":     ("DAMPERS",   "Left Rear → Fast Bump"),
    "bump_fast_rr":     ("DAMPERS",   "Right Rear → Fast Bump"),
    "rebound_fast_lf":  ("DAMPERS",   "Left Front → Fast Rebound"),
    "rebound_fast_rf":  ("DAMPERS",   "Right Front → Fast Rebound"),
    "rebound_fast_lr":  ("DAMPERS",   "Left Rear → Fast Rebound"),
    "rebound_fast_rr":  ("DAMPERS",   "Right Rear → Fast Rebound"),
    "camber_lf":        ("TIRES/AERO","Left Front → Camber"),
    "camber_rf":        ("TIRES/AERO","Right Front → Camber"),
    "camber_lr":        ("TIRES/AERO","Left Rear → Camber"),
    "camber_rr":        ("TIRES/AERO","Right Rear → Camber"),
    "toe_front":        ("TIRES/AERO","Front → Toe"),
    "toe_rear":         ("TIRES/AERO","Rear → Toe"),
    "pressure_lf":      ("TIRES/AERO","Left Front tire → Cold Pressure"),
    "pressure_rf":      ("TIRES/AERO","Right Front tire → Cold Pressure"),
    "pressure_lr":      ("TIRES/AERO","Left Rear tire → Cold Pressure"),
    "pressure_rr":      ("TIRES/AERO","Right Rear tire → Cold Pressure"),
    "wing_front":       ("TIRES/AERO","Aero → Front Wing"),
    "wing_rear":        ("TIRES/AERO","Aero → Rear Wing"),
    "diff_preload":     ("CHASSIS",   "Differential → Preload"),
    "diff_power":       ("CHASSIS",   "Differential → Power Ramp"),
    "diff_coast":       ("CHASSIS",   "Differential → Coast Ramp"),
    "tc_1":             ("CHASSIS",   "In-Car Adjustments → TC"),
    "tc_2":             ("CHASSIS",   "In-Car Adjustments → TC2"),
    "abs":              ("CHASSIS",   "In-Car Adjustments → ABS"),
}

TAB_ORDER = ["TIRES/AERO", "CHASSIS", "DAMPERS"]


# ─────────────────────────────────────────────────────────────────────────────
# 1. IBT SIGNAL EXTRACTOR
# ─────────────────────────────────────────────────────────────────────────────

class IBTSignalExtractor:
    """
    Reads AnalysisReport, CornerAnalysisReport, DrivingStyleReport, and
    ConsistencyBreakdown into a SignalBundle.

    None-safe — every field gracefully handles missing report data.
    """

    def extract(
        self,
        analysis=None,           # AnalysisReport
        corner_report=None,      # CornerAnalysisReport
        style_report=None,       # DriverStyleReport
        consistency=None,        # ConsistencyBreakdown
        car_name: str = "",
        track_name: str = "",
        car_class=None,
        baseline_setup: Dict = None,
    ) -> SignalBundle:

        bundle = SignalBundle(
            car_name=car_name,
            track_name=track_name,
            car_class=car_class,
            current_setup=baseline_setup or {},
        )

        self._extract_balance(bundle, analysis)
        self._extract_tire(bundle, analysis)
        self._extract_braking(bundle, analysis, style_report)
        self._extract_corners(bundle, corner_report)
        self._extract_consistency(bundle, analysis, consistency)
        self._classify_track(bundle, corner_report)
        self._extract_suspension(bundle, analysis)
        self._extract_slip_angles(bundle, analysis)
        self._extract_traffic(bundle, analysis)
        self._extract_body_motion(bundle, analysis)
        self._extract_tire_wear(bundle, analysis)
        self._extract_throttle_exit(bundle, analysis)
        self._extract_actual_ride_heights(bundle, analysis)
        self._extract_brake_hydraulics(bundle, analysis)
        self._extract_steering_torque(bundle, analysis)
        self._extract_yaw_balance(bundle, analysis)
        self._extract_spring_deflection(bundle, analysis)
        self._extract_speed_sectors(bundle, analysis)

        return bundle

    def _extract_balance(self, bundle: SignalBundle, analysis):
        if not analysis:
            return
        laps = getattr(analysis, 'lap_count', 0) or 0
        bundle.laps_analyzed = laps
        bundle.balance_confidence = min(1.0, laps / 10.0)

        bundle.balance_overall = getattr(analysis, 'balance_score', 0.0) or 0.0
        bundle.balance_entry   = getattr(analysis, 'balance_entry', 0.0) or 0.0
        bundle.balance_mid     = getattr(analysis, 'balance_mid',   0.0) or 0.0
        bundle.balance_exit    = getattr(analysis, 'balance_exit',  0.0) or 0.0

        # ── Fuel load correction ──────────────────────────────────────────────
        # High fuel weight biases CoG rearward, making the car look more
        # understeery than the setup actually is at race weight.
        # Correction: add small OS bias proportional to early-session fuel level.
        # Formula: each 10L above 5L adds ~0.02 balance units toward OS.
        # Max: +0.08 at full tank (~40L GT3). Calibrated from CoG shift estimation.
        try:
            channels = (getattr(analysis, '_channels', None) or
                        getattr(analysis, 'channels', None))
            if channels is not None:
                import numpy as _np_fuel
                fuel_ch = channels.get('FuelLevel')
                if fuel_ch is not None and len(fuel_ch) > 100:
                    early_n = max(1, len(fuel_ch) // 10)
                    avg_fuel_l = float(_np_fuel.mean(fuel_ch[:early_n]))
                    if avg_fuel_l > 5.0:
                        corr = min(0.08, (avg_fuel_l - 5.0) * 0.002)
                        bundle.balance_entry   += corr
                        bundle.balance_mid     += corr * 0.7
                        bundle.balance_exit    += corr * 0.5
                        bundle.balance_overall += corr * 0.6
                        bundle.fuel_correction_applied = corr
                        logger.debug('Fuel correction: +%.3f OS bias (%.0fL)', corr, avg_fuel_l)
        except Exception:
            pass

    def _extract_tire(self, bundle: SignalBundle, analysis):
        if not analysis:
            return
        tire_summary = getattr(analysis, 'tire_summary', None)
        if tire_summary:
            bundle.tire_temps = tire_summary
            bundle.tire_confidence = min(1.0, bundle.laps_analyzed / 5.0)
            if bundle.car_name:
                try:
                    from core.car_profiles import get_tire_temp_range
                    bundle._temp_min_c, bundle._temp_max_c = get_tire_temp_range(bundle.car_name)
                except Exception:
                    pass

        # Hot tire pressures
        tire_pressure = getattr(analysis, 'tire_pressure_hot', None)
        if tire_pressure:
            bundle.tire_pressure_hot = tire_pressure

    def _extract_tire_wear(self, bundle: SignalBundle, analysis):
        """
        Extract per-corner, per-zone tire wear from LFwearL/M/R channels.
        Wear pattern is ground truth for camber: outer zone wearing faster
        than inner = insufficient negative camber. More reliable than temps
        because it's cumulative and not affected by ambient temp or driving style.
        """
        if not analysis:
            return
        channels = getattr(analysis, '_channels', None) or getattr(analysis, 'channels', None)
        if channels is None:
            return
        try:
            import numpy as np
            corners = [('LF','LF'), ('RF','RF'), ('LR','LR'), ('RR','RR')]
            any_data = False
            for corner, key in corners:
                wL = channels.get(f'{key}wearL')
                wM = channels.get(f'{key}wearM')
                wR = channels.get(f'{key}wearR')
                if wL is None:
                    continue
                any_data = True
                # Take end-of-session values (last 100 samples, averaged)
                # wear is cumulative — higher = more worn
                end = -100
                wl = float(np.mean(wL[end:])) if len(wL) > 100 else float(np.mean(wL))
                wm = float(np.mean(wM[end:])) if wM is not None and len(wM) > 100 else 0.0
                wr = float(np.mean(wR[end:])) if wR is not None and len(wR) > 100 else 0.0
                if not hasattr(bundle, 'tire_wear'):
                    bundle.tire_wear = {}
                bundle.tire_wear[corner] = {'L': wl, 'M': wm, 'R': wr,
                                             'outer_inner_ratio': wr / max(wl, 0.001)}
            if any_data:
                bundle.has_wear_data = True
        except Exception as e:
            logger.debug('tire wear extraction failed: %s', e)

    def _extract_throttle_exit(self, bundle: SignalBundle, analysis):
        """
        Detect throttle-induced exit understeer.
        Reads Throttle + LatAccel to find corners where full throttle
        application coincides with declining lateral G — the signature of
        understeer loading the front on exit.
        """
        if not analysis:
            return
        channels = getattr(analysis, '_channels', None) or getattr(analysis, 'channels', None)
        if channels is None:
            return
        try:
            import numpy as np
            throttle = channels.get('Throttle')
            lat      = channels.get('LatAccel')
            dist     = channels.get('LapDistPct')
            if throttle is None or lat is None or dist is None:
                return

            G = 9.80665
            lat_g = lat / G

            # Exit phase: throttle ramping up (gradient > 0.1/s) while in corner (|lat| > 0.5G)
            thr_grad   = np.gradient(throttle)
            in_corner  = np.abs(lat_g) > 0.5
            throttle_ramp = thr_grad > 0.05          # throttle increasing
            full_power    = throttle > 0.7            # at least 70% throttle

            # Exit understeer: lat_g is DECREASING while throttle is increasing
            lat_grad = np.gradient(lat_g)
            exit_us_signal = (
                in_corner & throttle_ramp & full_power &
                (lat_grad * np.sign(lat_g) < -0.02)   # lat G dropping = understeer
            )

            bundle.exit_us_pct = float(np.mean(exit_us_signal)) * 100
            bundle.has_throttle_data = True
            logger.debug('Exit understeer signal: %.1f%% of laps', bundle.exit_us_pct)
        except Exception as e:
            logger.debug('throttle exit extraction failed: %s', e)

    def _extract_brake_hydraulics(self, bundle: SignalBundle, analysis):
        """
        Extract actual brake line pressures per corner from
        LFbrakeLinePress/RFbrakeLinePress/LRbrakeLinePress/RRbrakeLinePress.

        Computes the actual hydraulic front/rear split and compares to
        the dial setting (dcBrakeBias). A significant discrepancy indicates
        the hydraulic system isn't delivering the dialled split — worn
        balance bar, air in lines, or a pad/calliper issue.

        Also computes per-corner peak braking G to weight the balance score.
        """
        if not analysis:
            return
        channels = getattr(analysis, '_channels', None) or getattr(analysis, 'channels', None)
        if channels is None:
            return
        try:
            import numpy as np
            lf = channels.get('LFbrakeLinePress')
            rf = channels.get('RFbrakeLinePress')
            lr = channels.get('LRbrakeLinePress')
            rr = channels.get('RRbrakeLinePress')
            brake_ch = channels.get('Brake')

            if lf is None or rf is None or lr is None or rr is None:
                return

            # Only sample during heavy braking (>60% pedal)
            if brake_ch is not None:
                heavy = brake_ch > 0.60
                if heavy.sum() < 200:
                    return
                lf_h = lf[heavy]; rf_h = rf[heavy]
                lr_h = lr[heavy]; rr_h = rr[heavy]
            else:
                lf_h, rf_h, lr_h, rr_h = lf, rf, lr, rr

            # Pressure averages during heavy braking
            front_avg = float(np.mean(lf_h) + np.mean(rf_h)) / 2
            rear_avg  = float(np.mean(lr_h) + np.mean(rr_h)) / 2
            total_avg = front_avg + rear_avg
            if total_avg < 1e4:  # < 10 kPa = no meaningful data
                return

            hydraulic_front_pct = front_avg / total_avg * 100

            bundle.hydraulic_front_pct   = hydraulic_front_pct
            bundle.has_brake_hydraulics  = True

            # Compare to dial setting
            dial_pct = bundle.current_setup.get('brake_bias', None)
            if dial_pct is not None:
                try:
                    dial_f  = float(dial_pct)
                    discrepancy = hydraulic_front_pct - dial_f
                    bundle.brake_hydraulic_discrepancy = discrepancy
                    logger.debug(
                        'Brake hydraulics: dial=%.1f%% hydraulic=%.1f%% '
                        'discrepancy=%+.1f%%',
                        dial_f, hydraulic_front_pct, discrepancy)
                except (TypeError, ValueError):
                    pass
        except Exception as e:
            logger.debug('brake hydraulics extraction failed: %s', e)

    def _extract_steering_torque(self, bundle: SignalBundle, analysis):
        """
        Extract SteeringWheelTorque as a confirmation signal for understeer.

        High torque/lateral-G ratio during cornering = front is overloaded
        (understeer). Used to CONFIRM slip-angle-based US diagnosis, not
        replace it. Avoids false positives from driver technique alone.
        """
        if not analysis:
            return
        channels = getattr(analysis, '_channels', None) or getattr(analysis, 'channels', None)
        if channels is None:
            return
        try:
            import numpy as np
            torque = channels.get('SteeringWheelTorque')
            lat    = channels.get('LatAccel')
            if torque is None or lat is None:
                return

            G = 9.80665
            lat_g = np.abs(lat) / G
            in_corner = lat_g > 0.4  # > 0.4G lateral

            if in_corner.sum() < 500:
                return

            torque_cornering = np.abs(torque[in_corner])
            lat_g_cornering  = lat_g[in_corner]

            # Torque-per-G ratio: high = front working harder than it should
            ratio = torque_cornering / np.maximum(lat_g_cornering, 0.1)
            bundle.steering_torque_ratio = float(np.mean(ratio))
            bundle.steering_torque_peak  = float(np.percentile(torque_cornering, 95))
            bundle.has_steering_torque   = True

            logger.debug(
                'Steering torque: ratio=%.2f Nm/G  peak=%.1f Nm',
                bundle.steering_torque_ratio, bundle.steering_torque_peak)
        except Exception as e:
            logger.debug('steering torque extraction failed: %s', e)

    def _extract_yaw_balance(self, bundle: SignalBundle, analysis):
        """
        Use YawRate to compute rotation efficiency during cornering.

        yaw_rate / (lateral_G × speed) = normalised rotation — a measure
        of how much the car yaws relative to how hard it's cornering.
        Low = understeer (not rotating enough). High = oversteer tendency.
        This is used as a confirmation signal alongside slip angles.
        """
        if not analysis:
            return
        channels = getattr(analysis, '_channels', None) or getattr(analysis, 'channels', None)
        if channels is None:
            return
        try:
            import numpy as np
            yaw  = channels.get('YawRate')
            lat  = channels.get('LatAccel')
            spd  = channels.get('Speed')
            if yaw is None or lat is None or spd is None:
                return

            G = 9.80665
            lat_g = np.abs(lat) / G
            in_corner = (lat_g > 0.5) & (spd > 10.0)  # > 0.5G, > 36 km/h

            if in_corner.sum() < 500:
                return

            yaw_c = np.abs(yaw[in_corner])
            lat_c = lat_g[in_corner]
            spd_c = spd[in_corner]

            # Normalise: yaw_rate / (lat_G) gives rotation per unit lateral load
            # Higher = more rotation = more oversteer tendency
            norm_yaw = yaw_c / np.maximum(lat_c, 0.1)
            bundle.yaw_balance_ratio = float(np.mean(norm_yaw))
            bundle.has_yaw_data      = True

            logger.debug(
                'Yaw balance ratio: %.3f rad/s per G (>0.8 = OS tendency)',
                bundle.yaw_balance_ratio)
        except Exception as e:
            logger.debug('yaw balance extraction failed: %s', e)

    def _extract_spring_deflection(self, bundle: SignalBundle, analysis):
        """
        Extract LFspringDefl/RFspringDefl/LRspringDefl/RRspringDefl.

        Spring deflection separate from shock deflection reveals bump stop
        engagement: if shock travels but spring barely moves, the bump
        rubber is absorbing — car is riding on bump stops, not springs.
        This is a critical setup problem that makes the car unpredictable.
        """
        if not analysis:
            return
        channels = getattr(analysis, '_channels', None) or getattr(analysis, 'channels', None)
        if channels is None:
            return
        try:
            import numpy as np
            bundle.spring_defl_avg = {}
            bundle.bump_stop_engaged = {}
            any_data = False

            for corner in ['LF', 'RF', 'LR', 'RR']:
                sd = channels.get(f'{corner}springDefl')
                shd = channels.get(f'{corner}shockDefl')
                if sd is None:
                    continue
                any_data = True
                valid_sd  = sd[sd > 0.001]
                if len(valid_sd) < 100:
                    continue
                sd_mm = float(np.mean(valid_sd)) * 1000

                bundle.spring_defl_avg[corner] = sd_mm

                # Compare spring vs shock deflection — large ratio = bump stop
                if shd is not None:
                    valid_shd = shd[shd > 0.001]
                    if len(valid_shd) > 100:
                        shd_mm = float(np.mean(valid_shd)) * 1000
                        if shd_mm > 0:
                            ratio = sd_mm / shd_mm
                            # ratio < 0.7 = spring barely moving vs shock = bump stop
                            bundle.bump_stop_engaged[corner] = (ratio < 0.70)

            if any_data:
                bundle.has_spring_defl = True
        except Exception as e:
            logger.debug('spring deflection extraction failed: %s', e)

    def _extract_speed_sectors(self, bundle: SignalBundle, analysis):
        """
        Use Speed + LapDistPct to classify the track into high/low speed zones.

        Computes:
        - top_speed_kph: peak speed in session (straight-line)
        - slow_corner_pct: % of lap below 80 km/h (slow corner dominance)
        - fast_corner_pct: % of lap above 160 km/h in cornering
        - sector_max_speeds: per-decile max speed

        Used by _aero_rules() to differentiate:
        - High-DF track: many slow corners → more wing
        - Low-DF track: mostly fast → less wing, lower drag
        """
        if not analysis:
            return
        channels = getattr(analysis, '_channels', None) or getattr(analysis, 'channels', None)
        if channels is None:
            return
        try:
            import numpy as np
            spd  = channels.get('Speed')
            dist = channels.get('LapDistPct')
            lat  = channels.get('LatAccel')
            if spd is None or dist is None:
                return

            spd_kph = spd * 3.6
            G       = 9.80665

            bundle.top_speed_kph     = float(np.percentile(spd_kph, 99))
            bundle.slow_corner_pct   = float(np.mean(spd_kph < 80.0) * 100)

            if lat is not None:
                lat_g        = np.abs(lat) / G
                fast_corner  = (spd_kph > 160.0) & (lat_g > 0.5)
                bundle.fast_corner_pct = float(np.mean(fast_corner) * 100)
            else:
                bundle.fast_corner_pct = 0.0

            # Per-decile max speeds (10 sectors of 10% each)
            bundle.sector_max_speeds = []
            for i in range(10):
                lo, hi = i * 0.1, (i + 1) * 0.1
                mask = (dist >= lo) & (dist < hi)
                if mask.sum() > 10:
                    bundle.sector_max_speeds.append(
                        float(np.max(spd_kph[mask])))
                else:
                    bundle.sector_max_speeds.append(0.0)

            bundle.has_speed_sectors = True
            logger.debug(
                'Speed sectors: top=%.0f km/h slow=%.0f%% fast_corner=%.0f%%',
                bundle.top_speed_kph,
                bundle.slow_corner_pct,
                bundle.fast_corner_pct)
        except Exception as e:
            logger.debug('speed sector extraction failed: %s', e)

    def _extract_actual_ride_heights(self, bundle: SignalBundle, analysis):
        """
        Read actual ride height channels (LFrideHeight etc) as ground truth.
        More reliable than estimating from shock deflection.
        Already partially done in suspension rules but we track the actual
        values separately for use in camber and spring rules.
        """
        if not analysis:
            return
        channels = getattr(analysis, '_channels', None) or getattr(analysis, 'channels', None)
        if channels is None:
            return
        try:
            import numpy as np
            corners = [('LF','LF'), ('RF','RF'), ('LR','LR'), ('RR','RR')]
            if not hasattr(bundle, 'ride_heights_mm'):
                bundle.ride_heights_mm = {}
            any_data = False
            for corner, key in corners:
                rh = channels.get(f'{key}rideHeight')
                if rh is None:
                    continue
                valid = rh[rh > 0.001]
                if len(valid) < 50:
                    continue
                any_data = True
                bundle.ride_heights_mm[corner] = float(np.mean(valid)) * 1000  # m→mm
            if any_data:
                bundle.has_ride_height_data = True
        except Exception as e:
            logger.debug('ride height extraction failed: %s', e)

    def _extract_suspension(self, bundle: SignalBundle, analysis):
        """Extract suspension travel and damper velocity signals."""
        if not analysis:
            return
        channels = getattr(analysis, '_channels', None) or getattr(analysis, 'channels', None)
        if channels is None:
            return
        try:
            import numpy as np
            corners = ['LF', 'RF', 'LR', 'RR']
            any_data = False
            for corner in corners:
                defl = channels.get(f'{corner}shockDefl')
                vel  = channels.get(f'{corner}shockVel')
                if defl is None:
                    continue
                any_data = True
                valid = defl[defl > 0.001]  # filter parked/zero
                if len(valid) > 100:
                    bundle.shock_defl_avg[corner] = float(np.mean(valid)) * 1000  # m → mm
                if vel is not None:
                    vel_valid = vel[np.abs(vel) > 0.001]
                    if len(vel_valid) > 100:
                        abs_vel = np.abs(vel_valid)
                        bundle.shock_vel_histogram[corner] = {
                            'low_speed_pct': float(np.mean(abs_vel < 0.05)),   # <50mm/s
                            'high_speed_pct': float(np.mean(abs_vel >= 0.05)),
                            'peak_vel': float(np.max(abs_vel)),
                            'mean_vel': float(np.mean(abs_vel)),
                        }
            if any_data:
                bundle.suspension_confidence = min(1.0, bundle.laps_analyzed / 5.0)
        except Exception as e:
            logger.debug("suspension extraction failed: %s", e)

        # Read current ARB dial settings — actual baseline for delta computation
        # dcAntiRollFront/Rear give the current dial position so "+1 step" is
        # computed from where the driver actually is, not the class midpoint.
        try:
            import numpy as _np_arb
            _ch = getattr(analysis, '_channels', None) or getattr(analysis, 'channels', None)
            if _ch:
                _af = _ch.get('dcAntiRollFront')
                _ar = _ch.get('dcAntiRollRear')
                if _af is not None and len(_af) > 0:
                    bundle.current_setup['arb_front'] = float(
                        _np_arb.mean(_af[-min(100, len(_af)):]))
                if _ar is not None and len(_ar) > 0:
                    bundle.current_setup['arb_rear']  = float(
                        _np_arb.mean(_ar[-min(100, len(_ar)):]))
        except Exception:
            pass

    def _extract_slip_angles(self, bundle: SignalBundle, analysis):
        """Extract wheel slip angles for direct OS/US detection."""
        if not analysis:
            return
        channels = getattr(analysis, '_channels', None) or getattr(analysis, 'channels', None)
        if channels is None:
            return
        try:
            import numpy as np
            corners = ['LF', 'RF', 'LR', 'RR']
            any_data = False
            for corner in corners:
                slip = channels.get(f'WheelSlipAngle_{corner}')
                if slip is None:
                    continue
                any_data = True
                lat = channels.get('LatAccel')
                if lat is not None:
                    cornering = np.abs(lat) > 2.0  # only read slip during cornering
                    slip_corner = slip[cornering]
                else:
                    slip_corner = slip
                if len(slip_corner) > 100:
                    import math
                    bundle.slip_angle_avg[corner] = float(np.mean(np.abs(slip_corner)))
            if any_data:
                bundle.slip_confidence = min(1.0, bundle.laps_analyzed / 5.0)
        except Exception as e:
            logger.debug("slip angle extraction failed: %s", e)

    def _extract_traffic(self, bundle: SignalBundle, analysis):
        """Detect contaminated laps using CarIdxLapDistPct proximity."""
        if not analysis:
            return
        channels = getattr(analysis, '_channels', None) or getattr(analysis, 'channels', None)
        if channels is None:
            return
        try:
            import numpy as np
            lap_ch   = channels.get('Lap')
            dist_ch  = channels.get('LapDistPct')
            if lap_ch is None or dist_ch is None:
                return
            lap_i = lap_ch.astype(np.int32)
            laps  = sorted(set(lap_i.tolist()))
            bundle.clean_lap_mask = []
            contaminated = 0
            # Check for any CarIdx distance within 0.02 (about 2 car lengths)
            all_idx_channels = [channels.get(f'CarIdxLapDistPct')]
            # Only first available array
            car_idx_dist = all_idx_channels[0]
            for lap in laps[1:-1]:  # skip in/out laps
                lm = lap_i == lap
                if lm.sum() < 50:
                    continue
                clean = True
                if car_idx_dist is not None and hasattr(car_idx_dist[0], '__iter__'):
                    my_dist = dist_ch[lm]
                    for sample_i in range(0, int(lm.sum()), 30):
                        my_pos = float(my_dist[min(sample_i, len(my_dist)-1)])
                        try:
                            for other_pos in car_idx_dist[lm][sample_i]:
                                if other_pos and 0 < abs(my_pos - float(other_pos)) < 0.02:
                                    clean = False
                                    break
                        except Exception:
                            pass
                    if not clean:
                        contaminated += 1
                bundle.clean_lap_mask.append({'lap': lap, 'clean': clean})
            bundle.contaminated_laps = contaminated
        except Exception as e:
            logger.debug("traffic detection failed: %s", e)

    def _extract_braking(self, bundle: SignalBundle, analysis, style_report):
        if not analysis:
            return

        # Brake score from consistency
        brake_score = getattr(analysis, 'brake_score', None)
        if brake_score is not None:
            bundle.brake_score = float(brake_score)

        # Entry balance drives brake bias signal
        if abs(bundle.balance_entry) > 0.1 and bundle.laps_analyzed >= MIN_LAPS_FOR_CHANGE:
            if bundle.balance_entry > ENTRY_OS_BRAKE_THRESHOLD:
                bundle.brake_bias_direction = 'too_rearward'
                bundle.brake_bias_confidence = min(
                    1.0, (bundle.balance_entry - ENTRY_OS_BRAKE_THRESHOLD) * 3
                )
            elif bundle.balance_entry < ENTRY_US_BRAKE_THRESHOLD:
                bundle.brake_bias_direction = 'too_forward'
                bundle.brake_bias_confidence = min(
                    1.0, abs(bundle.balance_entry - ENTRY_US_BRAKE_THRESHOLD) * 3
                )
            else:
                bundle.brake_bias_direction = 'ok'

    def _extract_corners(self, bundle: SignalBundle, corner_report):
        if not corner_report:
            return

        corners = getattr(corner_report, 'corners', []) or []
        for c in corners:
            speed = getattr(c, 'avg_entry_speed_kph', 0) or 0
            if speed < 80:
                speed_class = 'slow'
            elif speed < 150:
                speed_class = 'medium'
            else:
                speed_class = 'fast'

            laps = getattr(c, 'lap_count', 0) or 0
            confidence = min(1.0, laps / 8.0)

            cs = CornerSignal(
                name=getattr(c, 'name', f'Corner {getattr(c, "corner_id", "?")}'),
                speed_class=speed_class,
                entry_os=getattr(c, 'entry_oversteer', 0.0) or 0.0,
                mid_os=getattr(c, 'mid_oversteer', 0.0) or 0.0,
                exit_os=getattr(c, 'exit_oversteer', 0.0) or 0.0,
                min_speed_delta=getattr(c, 'min_speed_delta_kph', 0.0) or 0.0,
                lap_count=laps,
                confidence=confidence,
            )
            bundle.corners.append(cs)

        if bundle.corners:
            speeds = [c.speed_class for c in bundle.corners]
            bundle.has_fast_corners = 'fast' in speeds
            bundle.has_slow_corners = 'slow' in speeds

    def _extract_consistency(self, bundle: SignalBundle, analysis, consistency):
        if consistency:
            bundle.consistency_score = getattr(consistency, 'overall_score', 0) or 0
            bundle.lap_time_std = getattr(consistency, 'lap_time_std', 0) or 0
        elif analysis:
            bundle.consistency_score = getattr(analysis, 'consistency_score', 0) or 0

    def _extract_body_motion(self, bundle: SignalBundle, analysis):
        """
        Extract body motion rates (roll/pitch) from YawRate/PitchRate/RollRate channels.
        High roll rate during cornering = ARB too soft.
        High pitch rate during braking = spring rate imbalance front/rear.
        """
        if not analysis:
            return
        channels = getattr(analysis, '_channels', None) or getattr(analysis, 'channels', None)
        if channels is None:
            return
        try:
            import numpy as np
            roll_ch  = channels.get('RollRate')
            pitch_ch = channels.get('PitchRate')
            lat_ch   = channels.get('LatAccel')
            brk_ch   = channels.get('Brake')
            any_data = False
            if roll_ch is not None and lat_ch is not None:
                any_data = True
                cornering = np.abs(lat_ch) > 3.0
                if cornering.sum() > 200:
                    bundle.roll_rate_cornering = float(np.mean(np.abs(roll_ch[cornering])))
            if pitch_ch is not None and brk_ch is not None:
                any_data = True
                braking = brk_ch > 0.3
                if braking.sum() > 200:
                    bundle.pitch_rate_braking = float(np.mean(np.abs(pitch_ch[braking])))
            if any_data:
                bundle.body_motion_confidence = min(1.0, bundle.laps_analyzed / 5.0)
        except Exception as e:
            logger.debug("body motion extraction failed: %s", e)

    def _classify_track(self, bundle: SignalBundle, corner_report):
        name = bundle.track_name.lower()
        if any(w in name for w in ('oval', 'daytona', 'talladega', 'bristol',
                                    'richmond', 'charlotte', 'pocono')):
            bundle.track_type = 'oval'
        elif any(w in name for w in ('dirt', 'knoxville', 'eldora', 'williams grove')):
            bundle.track_type = 'dirt'
        else:
            bundle.track_type = 'road'


# ─────────────────────────────────────────────────────────────────────────────
# 2. SETUP DELTA ENGINE
# ─────────────────────────────────────────────────────────────────────────────

class SetupDeltaEngine:
    """
    Maps a SignalBundle to a list of SetupDelta objects.

    Rules:
    - Only recommend a change if confidence >= MIN_CONFIDENCE
    - Only recommend ONE change per parameter
    - Deltas are expressed in the parameter's native unit and step
    - Never compute the final absolute value here — that's the assembler's job
    """

    def _car_thresholds(self, car_class: CarClass) -> dict:
        """
        Per-car-class threshold calibration for rule sensitivity.
        Prevents generic GT3 thresholds from misfiring on Cup or open-wheel cars.
        """
        base = {
            'os_mild':           BALANCE_OS_MILD,
            'os_strong':         BALANCE_OS_STRONG,
            'us_mild':           BALANCE_US_MILD,
            'us_strong':         BALANCE_US_STRONG,
            'roll_rate_arb':     0.8,   # rad/s — ARB adjustment trigger
            'pitch_rate_spring': 1.0,   # rad/s — spring rate trigger
            'shock_bottom_mm':   5.0,   # mm — bottoming warning
        }
        if car_class in (CarClass.PORSCHE_CUP, CarClass.GR86_CUP):
            # Cup cars: tight aero, more sensitive to small imbalances
            base.update({'os_mild': 0.12, 'us_mild': -0.12,
                         'roll_rate_arb': 0.6})
        elif car_class in (CarClass.DALLARA_F3, CarClass.FORMULA_RENAULT,
                           CarClass.SKIP_BARBER):
            # Open-wheel: very direct, small threshold margins
            base.update({'os_mild': 0.10, 'us_mild': -0.10,
                         'roll_rate_arb': 0.5, 'pitch_rate_spring': 0.7})
        elif car_class in (CarClass.GTP, CarClass.LMP2):
            # High-downforce prototypes: stiffer baseline, tighter bottoming
            base.update({'os_mild': 0.18, 'us_mild': -0.18,
                         'roll_rate_arb': 1.0, 'shock_bottom_mm': 3.0})
        return base

    def compute_deltas(self, bundle: SignalBundle,
                       car_class: CarClass = None) -> List[SetupDelta]:
        deltas: List[SetupDelta] = []

        if bundle.laps_analyzed < MIN_LAPS_FOR_CHANGE:
            logger.info("setup_generator: only %d laps — skipping delta generation",
                        bundle.laps_analyzed)
            return deltas

        effective_class = car_class or bundle.car_class or CarClass.DEFAULT

        # Run all rule groups
        deltas += self._brake_bias_rules(bundle, effective_class)
        deltas += self._brake_hydraulic_rules(bundle, effective_class)  # hydraulic confirmation
        deltas += self._arb_rules(bundle, effective_class)
        self._steering_torque_confirmation(bundle, effective_class)   # boosts slip confidence
        deltas += self._slip_angle_rules(bundle, effective_class)   # Tier 1: direct OS/US
        deltas += self._suspension_rules(bundle, effective_class)    # Tier 1: shock travel
        deltas += self._bump_stop_rules(bundle, effective_class)     # spring defl detection
        deltas += self._body_motion_rules(bundle, effective_class)   # body roll/pitch rates
        deltas += self._exit_understeer_rules(bundle, effective_class)  # throttle-induced US
        deltas += self._spring_rules(bundle, effective_class)
        deltas += self._aero_speed_rules(bundle, effective_class)   # speed-sector aero
        deltas += self._wear_camber_rules(bundle, effective_class)  # ground truth camber
        deltas += self._camber_rules(bundle, effective_class)       # temp-based camber fallback
        deltas += self._tire_pressure_rules(bundle, effective_class)
        deltas += self._diff_rules(bundle, effective_class)
        deltas += self._damper_rules(bundle, effective_class)
        deltas += self._aero_rules(bundle, effective_class)

        # Filter below confidence threshold
        deltas = [d for d in deltas if d.confidence >= MIN_CONFIDENCE]

        # Apply learned magnitude scaling per param + car class
        try:
            from core.setup_learning_db import get_learning_db
            _ldb = get_learning_db()
            _cls_str = (effective_class.value
                        if hasattr(effective_class, 'value')
                        else str(effective_class))
            for d in deltas:
                _scale = _ldb.get_magnitude_scale(_cls_str, d.param)
                if abs(_scale - 1.0) > 0.05 and d.delta != 0:
                    d.delta = round(d.delta * _scale, 3)
                    d.recommended_value = d.current_value + d.delta
                    logger.debug('Learning scale %s %s: ×%.2f → %.3f',
                                 _cls_str, d.param, _scale, d.delta)
        except Exception:
            pass  # Learning DB unavailable — raw recommendations unchanged

        # Deduplicate — keep highest confidence per param
        seen: Dict[str, SetupDelta] = {}
        for d in deltas:
            if d.param not in seen or d.confidence > seen[d.param].confidence:
                seen[d.param] = d
        deltas = list(seen.values())

        # Assign priorities
        deltas = self._prioritise(deltas, bundle)

        return sorted(deltas, key=lambda d: d.priority)

    # ── BRAKE BIAS ──────────────────────────────────────────────────────────

    def _brake_bias_rules(self, bundle: SignalBundle,
                           car_class: CarClass) -> List[SetupDelta]:
        results = []
        if bundle.brake_bias_confidence < MIN_CONFIDENCE:
            return results

        bounds = get_bounds(car_class)
        b = bounds.get('brake_bias')
        if not b:
            return results

        current = self._current(bundle, 'brake_bias', (b.min_val + b.max_val) / 2)

        if bundle.brake_bias_direction == 'too_rearward':
            # Entry OS — move bias forward (increase front bias %)
            magnitude = min(2.0, bundle.balance_entry * 2.0)
            delta = round(magnitude / b.step) * b.step
            delta = max(b.step, delta)
            results.append(SetupDelta(
                param='brake_bias',
                display_name='Brake Bias',
                garage_tab='CHASSIS',
                garage_location=PARAM_GARAGE_INFO['brake_bias'][1],
                current_value=current,
                recommended_value=current,   # assembler fills this
                delta=+delta,
                unit='%',
                signal_source=f'Entry oversteer = {bundle.balance_entry:+.2f} '
                              f'across {bundle.laps_analyzed} laps',
                confidence=bundle.brake_bias_confidence,
                reasoning=(
                    f'Your entry oversteer score of {bundle.balance_entry:+.2f} '
                    f'shows the rear is locking under trail-braking. Moving bias '
                    f'forward by {delta:.1f}% loads the front axle more during '
                    f'braking and reduces rear lock tendency.'
                ),
                driver_feel=(
                    'Initial pedal will feel heavier. The rear will feel more '
                    'planted on entry. Trail-brake oversteer should reduce '
                    'significantly within 2–3 laps.'
                ),
                priority=0,
            ))

        elif bundle.brake_bias_direction == 'too_forward':
            magnitude = min(2.0, abs(bundle.balance_entry) * 2.0)
            delta = round(magnitude / b.step) * b.step
            delta = max(b.step, delta)
            results.append(SetupDelta(
                param='brake_bias',
                display_name='Brake Bias',
                garage_tab='CHASSIS',
                garage_location=PARAM_GARAGE_INFO['brake_bias'][1],
                current_value=current,
                recommended_value=current,
                delta=-delta,
                unit='%',
                signal_source=f'Entry understeer = {bundle.balance_entry:+.2f}',
                confidence=bundle.brake_bias_confidence,
                reasoning=(
                    f'Entry understeer of {bundle.balance_entry:+.2f} suggests '
                    f'the front is locking before the rear. Reducing front bias '
                    f'by {delta:.1f}% allows the front to roll more freely on '
                    f'entry and improves rotation.'
                ),
                driver_feel=(
                    'Car will rotate more on entry. Be progressive with the '
                    'pedal initially — the rear will be more active.'
                ),
                priority=0,
            ))

        return results

    # ── ARB ─────────────────────────────────────────────────────────────────

    def _brake_hydraulic_rules(self, bundle: SignalBundle,
                                car_class: CarClass) -> List[SetupDelta]:
        """
        Detect discrepancy between the brake bias dial and actual hydraulic
        front/rear split. A discrepancy > 3% indicates a hydraulic system
        issue — worn balance bar, air in lines, or calliper problem.
        Also validates the balance score interpretation using actual pressures.
        """
        results = []
        if not getattr(bundle, 'has_brake_hydraulics', False):
            return results

        disc = getattr(bundle, 'brake_hydraulic_discrepancy', 0.0)
        hyd  = getattr(bundle, 'hydraulic_front_pct', 0.0)
        if hyd < 1.0:
            return results

        # Large discrepancy from dial setting — flag as hardware issue
        if abs(disc) > 4.0:
            results.append(SetupDelta(
                param='brake_bias',
                display_name='Brake Balance Bar (hardware)',
                garage_tab='CHASSIS',
                garage_location=PARAM_GARAGE_INFO.get('brake_bias', ('CHASSIS',''))[1],
                current_value=hyd,
                recommended_value=hyd - disc,  # what dial says it should be
                delta=0.0,
                unit='%',
                signal_source=(f'Hydraulic actual={hyd:.1f}% vs '
                               f'dial={hyd - disc:.1f}% — '
                               f'{abs(disc):.1f}% discrepancy'),
                confidence=min(0.85, 0.5 + abs(disc) / 20),
                reasoning=(
                    f'The brake system is delivering {hyd:.1f}% front bias '
                    f'hydraulically, but your dial is set to {hyd-disc:.1f}%. '
                    f'A {abs(disc):.1f}% discrepancy suggests a hardware issue: '
                    f'{"worn balance bar" if abs(disc) < 8 else "air in brake lines or calliper problem"}. '
                    f'Check and service the brake system before adjusting the dial further.'),
                driver_feel='Unpredictable brake feel. May improve with hardware service.',
                priority=0,
            ))

        # Hydraulic data confirms brake bias direction from entry balance
        # Use to boost confidence of brake bias recommendation
        if (bundle.brake_bias_direction == 'too_rearward' and hyd < 51.0) or            (bundle.brake_bias_direction == 'too_forward'  and hyd > 54.0):
            # Hydraulic data and balance score agree — boost confidence
            bundle.brake_bias_confidence = min(
                1.0, bundle.brake_bias_confidence * 1.3)
            logger.debug(
                'Brake hydraulics confirm brake bias direction — '
                'confidence boosted to %.2f', bundle.brake_bias_confidence)

        return results

    def _body_motion_rules(self, bundle: SignalBundle,
                            car_class: CarClass) -> List[SetupDelta]:
        """ARB and spring recommendations from body roll/pitch rates."""
        results = []
        if bundle.body_motion_confidence < 0.5:
            return results
        # Per-car-class thresholds
        try:
            from core.car_profiles import get_class_thresholds
            _thresholds = get_class_thresholds(car_class.value if hasattr(car_class, 'value') else str(car_class))
            _roll_thresh  = _thresholds.get('roll_rate_threshold_rads', 0.80)
            _pitch_thresh = _thresholds.get('pitch_rate_threshold_rads', 1.00)
        except Exception:
            _roll_thresh, _pitch_thresh = 0.80, 1.00
        bounds = get_bounds(car_class)
        # High roll rate → ARBs too soft
        if bundle.roll_rate_cornering > _roll_thresh:
            side = 'rear' if (bundle.balance_score or 0) > 0.3 else 'front'
            param = f'arb_{side}'
            b = bounds.get(param)
            if b:
                cur = self._current(bundle, param, (b.min_val + b.max_val) / 2)
                results.append(SetupDelta(
                    param=param,
                    display_name=f'{side.title()} ARB',
                    garage_tab='CHASSIS',
                    garage_location=PARAM_GARAGE_INFO.get(param, ('CHASSIS',''))[1],
                    current_value=cur, recommended_value=cur, delta=+1, unit='step',
                    signal_source=f'Roll rate: {bundle.roll_rate_cornering:.2f} rad/s (threshold {_roll_thresh:.2f})',
                    confidence=bundle.body_motion_confidence * 0.75,
                    reasoning=(f'Body roll rate {bundle.roll_rate_cornering:.2f} rad/s during '
                                f'cornering indicates excessive roll. Stiffening {side} ARB '
                                f'by 1 step improves tire contact patch consistency.'),
                    driver_feel='Sharper roll response. Slightly more mechanical understeer on turn-in.',
                    priority=1,
                ))
        # High pitch → front springs too soft
        if bundle.pitch_rate_braking > _pitch_thresh:
            b = bounds.get('spring_lf') or bounds.get('spring_rf')
            if b:
                cur = self._current(bundle, 'spring_lf', (b.min_val + b.max_val) / 2)
                results.append(SetupDelta(
                    param='spring_lf',
                    display_name='Front Spring Rate',
                    garage_tab='CHASSIS',
                    garage_location=PARAM_GARAGE_INFO.get('spring_lf', ('CHASSIS',''))[1],
                    current_value=cur, recommended_value=cur, delta=+b.step, unit=b.unit,
                    signal_source=f'Pitch rate braking: {bundle.pitch_rate_braking:.2f} rad/s (threshold {_pitch_thresh:.2f})',
                    confidence=bundle.body_motion_confidence * 0.65,
                    reasoning=(f'Pitch rate {bundle.pitch_rate_braking:.2f} rad/s under braking '
                                f'indicates nose-dive. Increasing front spring rate by '
                                f'{b.step:.0f} {b.unit} reduces dive and stabilises brake balance.'),
                    driver_feel='Less front dive under braking. More consistent brake pedal feel.',
                    priority=1,
                ))
        return results

    def _bump_stop_rules(self, bundle: SignalBundle,
                          car_class: CarClass) -> List[SetupDelta]:
        """
        Detect bump stop engagement from spring vs shock deflection ratio.
        When shock travels but spring barely moves, the car is riding on
        bump rubbers — makes handling unpredictable and untunable.
        Fix: raise ride height or soften spring rate.
        """
        results = []
        if not getattr(bundle, 'has_spring_defl', False):
            return results

        bounds = get_bounds(car_class)

        for corner, engaged in bundle.bump_stop_engaged.items():
            if not engaged:
                continue

            sd_mm  = bundle.spring_defl_avg.get(corner, 0.0)
            shd_mm = bundle.shock_defl_avg.get(corner, 0.0)

            if sd_mm < 0.1 or shd_mm < 0.1:
                continue

            # Primary fix: increase ride height at this corner
            rh_param = {
                'LF': 'ride_height_lf', 'RF': 'ride_height_rf',
                'LR': 'ride_height_lr', 'RR': 'ride_height_rr',
            }.get(corner)
            if rh_param:
                b = bounds.get(rh_param)
                if b:
                    cur = self._current(bundle, rh_param,
                                         (b.min_val + b.max_val) / 2)
                    results.append(SetupDelta(
                        param=rh_param,
                        display_name=f'{corner} Ride Height',
                        garage_tab='CHASSIS',
                        garage_location=PARAM_GARAGE_INFO.get(
                            rh_param, ('CHASSIS',''))[1],
                        current_value=cur,
                        recommended_value=cur,
                        delta=+b.step * 2,
                        unit=b.unit,
                        signal_source=(
                            f'{corner} spring={sd_mm:.1f}mm '
                            f'shock={shd_mm:.1f}mm '
                            f'ratio={sd_mm/max(shd_mm,0.1):.2f} '
                            f'(threshold 0.70)'),
                        confidence=0.80,
                        reasoning=(
                            f'{corner} spring deflects only {sd_mm:.1f}mm '
                            f'while shock travels {shd_mm:.1f}mm '
                            f'(ratio {sd_mm/max(shd_mm,0.1):.2f}) — the bump '
                            f'rubber is absorbing the stroke instead of the spring. '
                            f'Raising ride height gives the suspension more free travel '
                            f'before hitting the bump stop.'),
                        driver_feel='More predictable handling. Spring rate changes '
                                    'become effective again.',
                        priority=0,
                    ))

        return results

    def _steering_torque_confirmation(self, bundle: SignalBundle,
                                       car_class: CarClass) -> List[SetupDelta]:
        """
        Use SteeringWheelTorque to confirm and adjust confidence of
        understeer recommendations from slip angle rules.
        High torque/G ratio = front heavily loaded = confirms US diagnosis.
        Does not produce standalone deltas — modifies existing confidence.
        """
        if not getattr(bundle, 'has_steering_torque', False):
            return []
        if not getattr(bundle, 'has_yaw_data', False):
            return []

        torque_ratio = bundle.steering_torque_ratio
        yaw_ratio    = bundle.yaw_balance_ratio

        # High steering torque + low yaw rotation = understeer confirmed
        # Typical GT3: torque_ratio > 4.0 Nm/G = loaded, yaw < 0.5 = not rotating
        us_confirmed = torque_ratio > 4.0 and yaw_ratio < 0.55
        os_confirmed = torque_ratio < 2.5 and yaw_ratio > 0.75

        if us_confirmed:
            logger.debug(
                'Understeer confirmed by steering torque (%.1f Nm/G) '
                'and yaw ratio (%.2f)', torque_ratio, yaw_ratio)
            # Boost slip_confidence to reflect corroboration
            bundle.slip_confidence = min(1.0, bundle.slip_confidence * 1.2)
        elif os_confirmed:
            logger.debug(
                'Oversteer confirmed by steering torque (%.1f Nm/G) '
                'and yaw ratio (%.2f)', torque_ratio, yaw_ratio)
            bundle.slip_confidence = min(1.0, bundle.slip_confidence * 1.2)

        return []  # Confidence modifier only — rules handled by slip_angle_rules

    def _aero_speed_rules(self, bundle: SignalBundle,
                           car_class: CarClass) -> List[SetupDelta]:
        """
        Upgrade _aero_rules with speed-sector data from _extract_speed_sectors().
        Differentiates between:
        - High-DF track (>40% of lap below 80km/h) → add wing
        - Low-DF track (<15% slow corners, >20% fast corner time) → reduce wing
        """
        results = []
        if not getattr(bundle, 'has_speed_sectors', False):
            return results

        bounds = get_bounds(car_class)
        b_rear = bounds.get('wing_rear')
        b_front = bounds.get('wing_front')

        if not b_rear or b_rear.max_val <= 3:
            return results  # Fixed aero car

        slow_pct  = bundle.slow_corner_pct
        fast_pct  = bundle.fast_corner_pct
        top_spd   = bundle.top_speed_kph
        conf = min(bundle.balance_confidence, 0.75)

        # High-DF track: >35% of lap at sub-80km/h
        if slow_pct > 35.0 and top_spd > 180.0:
            cur_rear = self._current(bundle, 'wing_rear',
                                      (b_rear.min_val + b_rear.max_val) / 2)
            # Only recommend if balance shows OS tendency at high speed
            if bundle.balance_mid > 0.1:
                results.append(SetupDelta(
                    param='wing_rear',
                    display_name='Rear Wing',
                    garage_tab='TIRES/AERO',
                    garage_location=PARAM_GARAGE_INFO.get(
                        'wing_rear', ('TIRES/AERO',''))[1],
                    current_value=cur_rear,
                    recommended_value=cur_rear,
                    delta=+1,
                    unit='step',
                    signal_source=(
                        f'Slow corners: {slow_pct:.0f}% of lap below 80km/h '
                        f'| Mid-corner OS: {bundle.balance_mid:+.2f}'),
                    confidence=conf,
                    reasoning=(
                        f'{slow_pct:.0f}% of this lap is spent below 80 km/h '
                        f'(high mechanical-grip track). Combined with mid-corner '
                        f'oversteer ({bundle.balance_mid:+.2f}), adding 1 rear '
                        f'wing step improves balance in slow corners where '
                        f'aerodynamic stability matters most.'),
                    driver_feel='More rear stability in slow corners. '
                                'Negligible drag penalty at this track.',
                    priority=1,
                ))

        # Low-DF track: <15% slow corners, >20% fast corner time
        elif slow_pct < 15.0 and fast_pct > 20.0 and top_spd > 220.0:
            cur_rear = self._current(bundle, 'wing_rear',
                                      (b_rear.min_val + b_rear.max_val) / 2)
            if bundle.balance_mid < -0.1:  # understeer at high speed
                results.append(SetupDelta(
                    param='wing_rear',
                    display_name='Rear Wing',
                    garage_tab='TIRES/AERO',
                    garage_location=PARAM_GARAGE_INFO.get(
                        'wing_rear', ('TIRES/AERO',''))[1],
                    current_value=cur_rear,
                    recommended_value=cur_rear,
                    delta=-1,
                    unit='step',
                    signal_source=(
                        f'Fast corners: {fast_pct:.0f}% above 160km/h '
                        f'| Top speed: {top_spd:.0f}km/h '
                        f'| Mid-corner US: {bundle.balance_mid:+.2f}'),
                    confidence=conf,
                    reasoning=(
                        f'High-speed track ({fast_pct:.0f}% fast corner time, '
                        f'{top_spd:.0f} km/h peak). Mid-corner understeer '
                        f'({bundle.balance_mid:+.2f}) on a low-DF track suggests '
                        f'too much rear wing creating aero understeer. -1 rear '
                        f'wing step reduces drag and rebalances aero load forward.'),
                    driver_feel='Faster on straights. More neutral mid-corner balance.',
                    priority=1,
                ))

        return results

    def _arb_rules(self, bundle: SignalBundle,
                    car_class: CarClass) -> List[SetupDelta]:
        results = []
        bounds = get_bounds(car_class)
        conf = bundle.balance_confidence

        if conf < MIN_CONFIDENCE:
            return results

        b_front = bounds.get('arb_front')
        b_rear  = bounds.get('arb_rear')

        cur_front = self._current(bundle, 'arb_front',
                                   (b_front.min_val + b_front.max_val) / 2
                                   if b_front else 4)
        cur_rear  = self._current(bundle, 'arb_rear',
                                   (b_rear.min_val + b_rear.max_val) / 2
                                   if b_rear else 4)

        # Per-class sensitivity: scale delta so mechanical effect is consistent.
        # Formula needs 1 step where GT4 needs 2 for the same balance change.
        try:
            from core.tech_inspector import get_arb_sensitivity
            _fs = get_arb_sensitivity(car_class, 'front')
            _rs = get_arb_sensitivity(car_class, 'rear')
            # Convert sensitivity to step multiplier: high sensitivity = fewer steps
            _front_mult = round(max(0.5, 1.0 / _fs))
            _rear_mult  = round(max(0.5, 1.0 / _rs))
        except Exception:
            _front_mult = _rear_mult = 1

        mid_os  = bundle.balance_mid
        exit_os = bundle.balance_exit

        # Mid-corner oversteer: soften rear ARB
        if mid_os > BALANCE_OS_MILD and b_rear:
            strength = _rear_mult if mid_os < BALANCE_OS_STRONG else _rear_mult * 2
            results.append(SetupDelta(
                param='arb_rear',
                display_name='Rear ARB',
                garage_tab='CHASSIS',
                garage_location=PARAM_GARAGE_INFO['arb_rear'][1],
                current_value=cur_rear,
                recommended_value=cur_rear,
                delta=-strength,
                unit='step',
                signal_source=f'Mid-corner oversteer = {mid_os:+.2f}',
                confidence=conf,
                reasoning=(
                    f'Mid-corner oversteer of {mid_os:+.2f} indicates the rear '
                    f'ARB is transferring too much lateral load to the outside '
                    f'rear tire. Softening by {strength} step(s) allows more '
                    f'rear body roll, distributing load across both rear tires '
                    f'and reducing the snap tendency.'
                ),
                driver_feel=(
                    'More rear roll mid-corner. Car will feel more planted and '
                    'predictable at the limit. Apex rotation will be smoother.'
                ),
                priority=0,
            ))

        # Mid-corner understeer: soften front ARB
        elif mid_os < BALANCE_US_MILD and b_front:
            strength = 1 if mid_os > BALANCE_US_STRONG else 2
            results.append(SetupDelta(
                param='arb_front',
                display_name='Front ARB',
                garage_tab='CHASSIS',
                garage_location=PARAM_GARAGE_INFO['arb_front'][1],
                current_value=cur_front,
                recommended_value=cur_front,
                delta=-strength,
                unit='step',
                signal_source=f'Mid-corner understeer = {mid_os:+.2f}',
                confidence=conf,
                reasoning=(
                    f'Mid-corner understeer of {mid_os:+.2f} suggests the front '
                    f'ARB is too stiff, limiting front body roll and reducing '
                    f'contact patch loading. Softening by {strength} step(s) '
                    f'increases front grip and improves rotation toward the apex.'
                ),
                driver_feel=(
                    'More front movement through corner entry. The nose will '
                    'respond more eagerly to steering input.'
                ),
                priority=0,
            ))

        # Exit oversteer with stiff rear ARB — independent of mid signal
        if (exit_os > BALANCE_OS_STRONG and
                mid_os < BALANCE_OS_STRONG and b_rear):
            # Pure exit oversteer without mid issue = diff problem primarily,
            # but ARB softening helps if rear is very stiff
            if cur_rear >= (b_rear.max_val - b_rear.step):
                results.append(SetupDelta(
                    param='arb_rear',
                    display_name='Rear ARB',
                    garage_tab='CHASSIS',
                    garage_location=PARAM_GARAGE_INFO['arb_rear'][1],
                    current_value=cur_rear,
                    recommended_value=cur_rear,
                    delta=-1,
                    unit='step',
                    signal_source=f'Exit oversteer = {exit_os:+.2f}, rear ARB at max',
                    confidence=conf * 0.7,
                    reasoning=(
                        f'Power-on exit oversteer ({exit_os:+.2f}) with rear '
                        f'ARB at or near maximum. Softening by 1 step reduces '
                        f'rear lateral load sensitivity under acceleration.'
                    ),
                    driver_feel=(
                        'More progressive throttle application window on exit. '
                        'Combine with diff adjustment for full fix.'
                    ),
                    priority=0,
                ))

        return results

    # ── SUSPENSION TRAVEL (shock_defl) ──────────────────────────────────────

    def _suspension_rules(self, bundle: SignalBundle,
                           car_class: CarClass) -> List[SetupDelta]:
        """
        Ride height and spring recommendations from actual shock travel data.
        Requires suspension_confidence >= 0.5.
        """
        results = []
        if bundle.suspension_confidence < 0.5 or not bundle.shock_defl_avg:
            return results

        bounds  = get_bounds(car_class)
        corners = ['LF', 'RF', 'LR', 'RR']

        # Bottom-out detection: if avg travel > 80% of available range, car is too low
        rh_params = {'LF': 'rh_lf', 'RF': 'rh_rf', 'LR': 'rh_lr', 'RR': 'rh_rr'}
        for corner in corners:
            travel_mm = bundle.shock_defl_avg.get(corner, 0.0)
            if travel_mm < 1.0:
                continue
            b_rh = bounds.get(rh_params[corner])
            if not b_rh:
                continue
            # Available travel = ride_height - min_legal_ride_height
            cur_rh = self._current(bundle, rh_params[corner],
                                    (b_rh.min_val + b_rh.max_val) / 2)
            available = cur_rh - b_rh.min_val
            if available > 0 and travel_mm > available * 0.82:
                results.append(SetupDelta(
                    param=rh_params[corner],
                    display_name=f'{corner} Ride Height',
                    garage_tab='CHASSIS',
                    garage_location=PARAM_GARAGE_INFO.get(rh_params[corner],
                                    ('CHASSIS',''))[1],
                    current_value=cur_rh,
                    recommended_value=cur_rh,
                    delta=+3.0,
                    unit='mm',
                    signal_source=(f'{corner} avg shock travel {travel_mm:.1f}mm '
                                   f'= {travel_mm/available*100:.0f}% of available range'),
                    confidence=bundle.suspension_confidence * 0.85,
                    reasoning=(
                        f'{corner} suspension is using {travel_mm:.1f}mm of '
                        f'{available:.0f}mm available travel — near bottoming. '
                        f'Raising ride height by 3mm reduces risk of grounding '
                        f'and improves aero consistency.'),
                    driver_feel='Less bottoming over kerbs. Slightly higher centre of gravity.',
                    priority=0,
                ))

        # Damper HS/LS imbalance — if high-speed events dominate, springs too soft
        for corner in corners:
            hist = bundle.shock_vel_histogram.get(corner)
            if not hist:
                continue
            if hist.get('high_speed_pct', 0) > 0.35:
                # More than 35% of damper events are high-speed → spring rate issue
                spring_param = {'LF':'spring_lf','RF':'spring_rf',
                                'LR':'spring_lr','RR':'spring_rr'}.get(corner)
                if not spring_param:
                    continue
                b_sp = bounds.get(spring_param)
                if not b_sp:
                    continue
                cur_sp = self._current(bundle, spring_param,
                                        (b_sp.min_val + b_sp.max_val) / 2)
                results.append(SetupDelta(
                    param=spring_param,
                    display_name=f'{corner} Spring Rate',
                    garage_tab='CHASSIS',
                    garage_location=PARAM_GARAGE_INFO.get(spring_param,
                                    ('CHASSIS',''))[1],
                    current_value=cur_sp,
                    recommended_value=cur_sp,
                    delta=+b_sp.step,
                    unit=b_sp.unit,
                    signal_source=(f'{corner} HS damper events: '
                                   f'{hist["high_speed_pct"]*100:.0f}% of stroke'),
                    confidence=bundle.suspension_confidence * 0.7,
                    reasoning=(
                        f'{corner} damper is operating in high-speed territory '
                        f'{hist["high_speed_pct"]*100:.0f}% of the time, indicating '
                        f'the spring is too soft to support the body motion. '
                        f'Increasing spring rate by {b_sp.step:.0f} {b_sp.unit} '
                        f'shifts load from damper to spring.'),
                    driver_feel='Less body movement. Firmer initial response over bumps.',
                    priority=0,
                ))
        return results

    # ── SLIP ANGLE RULES ─────────────────────────────────────────────────────

    def _slip_angle_rules(self, bundle: SignalBundle,
                           car_class: CarClass) -> List[SetupDelta]:
        """
        Direct understeer/oversteer diagnosis from wheel slip angles.
        More precise than balance score alone.
        """
        results = []
        if bundle.slip_confidence < 0.5 or not bundle.slip_angle_avg:
            return results

        bounds = get_bounds(car_class)
        front_avg = (bundle.slip_angle_avg.get('LF', 0) +
                     bundle.slip_angle_avg.get('RF', 0)) / 2
        rear_avg  = (bundle.slip_angle_avg.get('LR', 0) +
                     bundle.slip_angle_avg.get('RR', 0)) / 2

        if front_avg < 0.001 and rear_avg < 0.001:
            return results

        # Oversteer: rear slip >> front slip
        if rear_avg > front_avg * 1.4 and rear_avg > 0.02:
            b = bounds.get('arb_rear')
            if b:
                cur = self._current(bundle, 'arb_rear',
                                     (b.min_val + b.max_val) / 2)
                results.append(SetupDelta(
                    param='arb_rear',
                    display_name='Rear ARB',
                    garage_tab='CHASSIS',
                    garage_location=PARAM_GARAGE_INFO.get('arb_rear',('CHASSIS',''))[1],
                    current_value=cur,
                    recommended_value=cur,
                    delta=-1,
                    unit='step',
                    signal_source=(f'Rear slip {rear_avg:.3f}rad vs '
                                   f'front {front_avg:.3f}rad '
                                   f'({rear_avg/max(front_avg,0.001):.1f}x ratio)'),
                    confidence=bundle.slip_confidence,
                    reasoning=(
                        f'Rear wheel slip angle ({rear_avg:.3f} rad) is '
                        f'{rear_avg/max(front_avg,0.001):.1f}x the front '
                        f'({front_avg:.3f} rad) — direct evidence of rear-end '
                        f'breakaway. Softening rear ARB by 1 step distributes '
                        f'load more evenly across both rear tires.'),
                    driver_feel='More predictable rear. Reduced snap oversteer tendency.',
                    priority=0,
                ))

        # Understeer: front slip >> rear slip
        elif front_avg > rear_avg * 1.4 and front_avg > 0.02:
            b = bounds.get('arb_front')
            if b:
                cur = self._current(bundle, 'arb_front',
                                     (b.min_val + b.max_val) / 2)
                results.append(SetupDelta(
                    param='arb_front',
                    display_name='Front ARB',
                    garage_tab='CHASSIS',
                    garage_location=PARAM_GARAGE_INFO.get('arb_front',('CHASSIS',''))[1],
                    current_value=cur,
                    recommended_value=cur,
                    delta=-1,
                    unit='step',
                    signal_source=(f'Front slip {front_avg:.3f}rad vs '
                                   f'rear {rear_avg:.3f}rad '
                                   f'({front_avg/max(rear_avg,0.001):.1f}x ratio)'),
                    confidence=bundle.slip_confidence,
                    reasoning=(
                        f'Front wheel slip angle ({front_avg:.3f} rad) is '
                        f'{front_avg/max(rear_avg,0.001):.1f}x the rear — '
                        f'direct evidence of front understeer. Softening front '
                        f'ARB increases front grip by allowing more front body roll.'),
                    driver_feel='More front response to steering input. Sharper turn-in.',
                    priority=0,
                ))
        return results

    # ── SPRINGS ─────────────────────────────────────────────────────────────

    def _spring_rules(self, bundle: SignalBundle,
                       car_class: CarClass) -> List[SetupDelta]:
        results = []
        # Springs are high-consequence changes — require strong signal + confidence
        if bundle.balance_confidence < 0.6:
            return results

        bounds = get_bounds(car_class)
        # Per-class spring sensitivity: Formula needs smaller deltas than GT4
        try:
            from core.tech_inspector import get_spring_sensitivity
            _sf = get_spring_sensitivity(car_class, 'front')
            _sr = get_spring_sensitivity(car_class, 'rear')
            _spr_front_mult = max(0.25, 1.0 / _sf)
            _spr_rear_mult  = max(0.25, 1.0 / _sr)
        except Exception:
            _spr_front_mult = _spr_rear_mult = 1.0

        mid_os = bundle.balance_mid

        # Persistent mid-corner understeer after ARB at minimum →
        # front springs may be too stiff
        b_front_spring = bounds.get('spring_lf')
        if (mid_os < BALANCE_US_STRONG and b_front_spring
                and bundle.balance_confidence >= 0.7):
            arb_front_current = self._current(
                bundle, 'arb_front',
                (bounds['arb_front'].min_val if 'arb_front' in bounds else 1)
            )
            arb_min = bounds['arb_front'].min_val if 'arb_front' in bounds else 1
            if arb_front_current <= arb_min + 1:
                # ARB already soft — spring is the next lever
                step = b_front_spring.step
                cur_lf = self._current(bundle, 'spring_lf',
                                        (b_front_spring.min_val + b_front_spring.max_val) / 2)
                results.append(SetupDelta(
                    param='spring_lf',
                    display_name='LF Spring Rate',
                    garage_tab='CHASSIS',
                    garage_location=PARAM_GARAGE_INFO['spring_lf'][1],
                    current_value=cur_lf,
                    recommended_value=cur_lf,
                    delta=-step,
                    unit=b_front_spring.unit,
                    signal_source=f'Strong mid understeer {mid_os:+.2f}, front ARB at/near min',
                    confidence=bundle.balance_confidence * 0.8,
                    reasoning=(
                        f'Persistent mid-corner understeer ({mid_os:+.2f}) with '
                        f'front ARB already at minimum. Reducing front spring rate '
                        f'by {step:.0f} {b_front_spring.unit} increases front compliance '
                        f'and contact patch loading through the corner.'
                    ),
                    driver_feel=(
                        'Car will feel more planted over kerbs. Front will '
                        'respond more progressively to steering.'
                    ),
                    priority=0,
                ))
                # Mirror RF
                cur_rf = self._current(bundle, 'spring_rf', cur_lf)
                lf_delta = results[-1]
                rf_delta = SetupDelta(**{**lf_delta.__dict__,
                                         'param': 'spring_rf',
                                         'display_name': 'RF Spring Rate',
                                         'garage_location': PARAM_GARAGE_INFO['spring_rf'][1],
                                         'current_value': cur_rf,
                                         })
                results.append(rf_delta)

        return results

    # ── CAMBER ──────────────────────────────────────────────────────────────

    def _wear_camber_rules(self, bundle: SignalBundle,
                            car_class: CarClass) -> List[SetupDelta]:
        """
        Camber recommendations from tire wear pattern — ground truth signal.
        Outer zone wearing faster than inner = need more negative camber.
        More reliable than temperature spread because wear is cumulative
        and unaffected by ambient temp or driving technique variations.
        Requires has_wear_data flag from _extract_tire_wear().
        """
        results = []
        if not getattr(bundle, 'has_wear_data', False):
            return results

        bounds = get_bounds(car_class)

        for corner in ['LF', 'RF', 'LR', 'RR']:
            wear = getattr(bundle, 'tire_wear', {}).get(corner)
            if not wear:
                continue
            outer_inner = wear.get('outer_inner_ratio', 1.0)
            wL = wear.get('L', 0)
            wR = wear.get('R', 0)  # R = outer edge

            # Outer wearing >20% faster than inner = too little negative camber
            if outer_inner > 1.20 and wR > 0.05:
                camber_param = {
                    'LF': 'camber_lf', 'RF': 'camber_rf',
                    'LR': 'camber_lr', 'RR': 'camber_rr'
                }.get(corner)
                if not camber_param:
                    continue
                b = bounds.get(camber_param)
                if not b:
                    continue
                cur = self._current(bundle, camber_param,
                                     (b.min_val + b.max_val) / 2)
                adj = min(b.step * 2, (outer_inner - 1.0) * 0.5)
                results.append(SetupDelta(
                    param=camber_param,
                    display_name=f'{corner} Camber',
                    garage_tab='TIRES',
                    garage_location=PARAM_GARAGE_INFO.get(
                        camber_param, ('TIRES',''))[1],
                    current_value=cur,
                    recommended_value=cur,
                    delta=-adj,  # more negative camber
                    unit='°',
                    signal_source=(f'{corner} wear ratio outer/inner: '
                                   f'{outer_inner:.2f}x (threshold 1.20x)'),
                    confidence=min(0.9, bundle.tire_confidence * 1.1),
                    reasoning=(
                        f'{corner} outer tread wearing {outer_inner:.1f}x faster '
                        f'than inner (L:{wL:.3f} vs R:{wR:.3f}). '
                        f'This is the direct indicator of insufficient negative camber — '
                        f'the tire is rolling onto its outside edge under cornering load. '
                        f'Adding {adj:.2f}° negative camber distributes load across the '
                        f'full tread width.'),
                    driver_feel='Slightly more initial grip on turn-in. '
                                'Marginal increase in tire temps at first.',
                    priority=0,
                ))

            # Inner wearing >20% faster = too MUCH negative camber
            elif outer_inner < 0.80 and wL > 0.05:
                camber_param = {
                    'LF': 'camber_lf', 'RF': 'camber_rf',
                    'LR': 'camber_lr', 'RR': 'camber_rr'
                }.get(corner)
                if not camber_param:
                    continue
                b = bounds.get(camber_param)
                if not b:
                    continue
                cur = self._current(bundle, camber_param,
                                     (b.min_val + b.max_val) / 2)
                adj = min(b.step * 2, (1.0 - outer_inner) * 0.5)
                results.append(SetupDelta(
                    param=camber_param,
                    display_name=f'{corner} Camber',
                    garage_tab='TIRES',
                    garage_location=PARAM_GARAGE_INFO.get(
                        camber_param, ('TIRES',''))[1],
                    current_value=cur,
                    recommended_value=cur,
                    delta=+adj,  # less negative camber
                    unit='°',
                    signal_source=(f'{corner} wear ratio outer/inner: '
                                   f'{outer_inner:.2f}x (threshold 0.80x)'),
                    confidence=min(0.9, bundle.tire_confidence * 1.1),
                    reasoning=(
                        f'{corner} inner tread wearing {1/outer_inner:.1f}x faster '
                        f'than outer (L:{wL:.3f} vs R:{wR:.3f}). '
                        f'Indicates excessive negative camber — tire loading heavily '
                        f'on the inner shoulder. Reducing camber by {adj:.2f}° '
                        f'spreads load more evenly.'),
                    driver_feel='Slightly less turn-in sharpness. '
                                'Better straight-line stability and tire longevity.',
                    priority=0,
                ))
        return results

    def _exit_understeer_rules(self, bundle: SignalBundle,
                                car_class: CarClass) -> List[SetupDelta]:
        """
        Detect and address throttle-induced exit understeer.
        Threshold is per-car-class (FWD TCR has higher natural exit push).
        """
        results = []
        if not getattr(bundle, 'has_throttle_data', False):
            return results
        exit_us = getattr(bundle, 'exit_us_pct', 0.0)
        try:
            from core.car_profiles import get_class_thresholds
            _t = get_class_thresholds(car_class.value if hasattr(car_class, 'value') else str(car_class))
            _exit_thresh = _t.get('exit_us_threshold_pct', 15.0)
            _exit_severe = _exit_thresh * 1.7
        except Exception:
            _exit_thresh, _exit_severe = 15.0, 25.0
        if exit_us < _exit_thresh:
            return results

        bounds = get_bounds(car_class)

        # Primary fix: soften rear ARB — allows rear to rotate on exit
        b = bounds.get('arb_rear')
        if b:
            cur = self._current(bundle, 'arb_rear',
                                 (b.min_val + b.max_val) / 2)
            results.append(SetupDelta(
                param='arb_rear',
                display_name='Rear ARB',
                garage_tab='CHASSIS',
                garage_location=PARAM_GARAGE_INFO.get('arb_rear',('CHASSIS',''))[1],
                current_value=cur,
                recommended_value=cur,
                delta=-1,
                unit='step',
                signal_source=(f'Exit understeer in {exit_us:.0f}% of corner exits '
                               f'— throttle ramp with declining lateral G'),
                confidence=min(0.8, bundle.balance_confidence * 0.9),
                reasoning=(
                    f'Detected exit understeer in {exit_us:.0f}% of measured corner '
                    f'exits — throttle application causes lateral G to drop rather '
                    f'than hold. This indicates the rear ARB is too stiff, preventing '
                    f'the rear from rotating and loading the front on exit. '
                    f'Softening rear ARB by 1 step allows the rear to settle on '
                    f'power, restoring front grip on exit.'),
                driver_feel='Car rotates more willingly on exit. '
                            'Throttle feels more connected to rear traction.',
                priority=0,
            ))

        # Secondary: check if front toe-out would help
        b_toe = bounds.get('toe_front')
        if b_toe and exit_us > _exit_severe:
            cur = self._current(bundle, 'toe_front',
                                 (b_toe.min_val + b_toe.max_val) / 2)
            results.append(SetupDelta(
                param='toe_front',
                display_name='Front Toe',
                garage_tab='CHASSIS',
                garage_location=PARAM_GARAGE_INFO.get('toe_front',('CHASSIS',''))[1],
                current_value=cur,
                recommended_value=cur,
                delta=-b_toe.step,
                unit=b_toe.unit,
                signal_source=f'Severe exit understeer: {exit_us:.0f}% of exits',
                confidence=min(0.7, bundle.balance_confidence * 0.8),
                reasoning=(
                    f'Severe exit understeer ({exit_us:.0f}%) — secondary fix. '
                    f'Increasing front toe-out by {b_toe.step:.3g}{b_toe.unit} '
                    f'improves initial front response on corner exit, helping the '
                    f'front find grip as the rear settles under power.'),
                driver_feel='Sharper front response. May feel slightly nervous '
                            'on initial turn-in.',
                priority=1,
            ))
        return results

    def _camber_rules(self, bundle: SignalBundle,
                       car_class: CarClass) -> List[SetupDelta]:
        results = []
        if bundle.tire_confidence < 0.4 or not bundle.tire_temps:
            return results

        bounds = get_bounds(car_class)

        corner_map = {
            'LF': ('camber_lf', 'LF Camber'),
            'RF': ('camber_rf', 'RF Camber'),
            'LR': ('camber_lr', 'LR Camber'),
            'RR': ('camber_rr', 'RR Camber'),
        }
        for corner, (param, name) in corner_map.items():
            temps = bundle.tire_temps.get(corner)
            if not temps:
                continue
            inner = temps.get('inner', 0)
            outer = temps.get('outer', 0)
            imbalance = inner - outer   # positive = inner hotter = needs more negative camber
            b = bounds.get(param)
            if not b:
                continue
            current = self._current(bundle, param, (b.min_val + b.max_val) / 2)

            if abs(imbalance) >= TIRE_TEMP_IMBALANCE_C:
                direction = -0.1 if imbalance > 0 else +0.1  # more/less negative camber
                results.append(SetupDelta(
                    param=param,
                    display_name=name,
                    garage_tab='TIRES/AERO',
                    garage_location=PARAM_GARAGE_INFO[param][1],
                    current_value=current,
                    recommended_value=current,
                    delta=direction,
                    unit='deg',
                    signal_source=(
                        f'{corner} tire: inner {inner:.0f}°C, '
                        f'outer {outer:.0f}°C, imbalance {imbalance:+.0f}°C'
                    ),
                    confidence=bundle.tire_confidence,
                    reasoning=(
                        f'{corner} tire inner is {abs(imbalance):.0f}°C '
                        f'{"hotter" if imbalance > 0 else "cooler"} than outer. '
                        f'{"Adding" if direction < 0 else "Reducing"} camber by '
                        f'0.1° improves contact patch uniformity and tire life.'
                    ),
                    driver_feel=(
                        'More even tire wear. No immediate feel change — '
                        'effect builds over a stint.'
                    ),
                    priority=0,
                ))

        return results

    # ── TIRE PRESSURE ────────────────────────────────────────────────────────

    def _tire_pressure_rules(self, bundle: SignalBundle,
                               car_class: CarClass) -> List[SetupDelta]:
        results = []
        if not bundle.tire_pressure_hot or bundle.tire_confidence < 0.4:
            return results

        bounds = get_bounds(car_class)

        # Target hot pressure — use per-car profile if available,
        # fall back to class-level defaults
        from core.car_profiles import get_target_hot_psi, get_car_profile
        _car_psi = get_target_hot_psi(bundle.car_name) if bundle.car_name else {}
        _class_defaults = {
            CarClass.GT3:         (28.0, 31.0),
            CarClass.GT4:         (28.5, 31.5),
            CarClass.PORSCHE_CUP: (29.5, 32.0),
            CarClass.GTP:         (22.0, 25.0),
            CarClass.FORMULA:     (20.0, 23.0),
            CarClass.TCR:         (32.0, 35.0),
        }
        _default_low, _default_high = _class_defaults.get(car_class, (28.0, 32.0))

        corner_map = {
            'LF': 'pressure_lf',
            'RF': 'pressure_rf',
            'LR': 'pressure_lr',
            'RR': 'pressure_rr',
        }
        pressure_rise_est = 4.0  # typical hot−cold psi rise

        for corner, param in corner_map.items():
            hot_psi = bundle.tire_pressure_hot.get(corner)
            if hot_psi is None:
                continue
            b = bounds.get(param)
            if not b:
                continue
            current_cold = self._current(bundle, param,
                                          (b.min_val + b.max_val) / 2)

            # Use per-corner car profile target if available
            _corner_target = _car_psi.get(corner)
            if _corner_target is not None:
                target_low  = max(_default_low,  _corner_target - 1.5)
                target_high = min(_default_high, _corner_target + 1.5)
            else:
                target_low, target_high = _default_low, _default_high

            if hot_psi < target_low:
                # Under-inflated hot — raise cold pressure
                adjustment = round((target_low - hot_psi) / b.step) * b.step
                adjustment = max(b.step, min(2.0, adjustment))
                results.append(SetupDelta(
                    param=param,
                    display_name=f'{corner} Cold Pressure',
                    garage_tab='TIRES/AERO',
                    garage_location=PARAM_GARAGE_INFO[param][1],
                    current_value=current_cold,
                    recommended_value=current_cold,
                    delta=+adjustment,
                    unit='psi',
                    signal_source=f'{corner} hot pressure = {hot_psi:.1f} psi '
                                  f'(target {target_low:.0f}–{target_high:.0f})',
                    confidence=bundle.tire_confidence,
                    reasoning=(
                        f'{corner} tire running {hot_psi:.1f} psi hot — '
                        f'{target_low - hot_psi:.1f} psi below target window. '
                        f'Increasing cold pressure by {adjustment:.1f} psi '
                        f'brings hot pressure into the target range.'
                    ),
                    driver_feel=(
                        'Slightly firmer initial feel. Tire response sharpens '
                        'as it reaches operating temperature.'
                    ),
                    priority=0,
                ))

            elif hot_psi > target_high:
                adjustment = round((hot_psi - target_high) / b.step) * b.step
                adjustment = max(b.step, min(2.0, adjustment))
                results.append(SetupDelta(
                    param=param,
                    display_name=f'{corner} Cold Pressure',
                    garage_tab='TIRES/AERO',
                    garage_location=PARAM_GARAGE_INFO[param][1],
                    current_value=current_cold,
                    recommended_value=current_cold,
                    delta=-adjustment,
                    unit='psi',
                    signal_source=f'{corner} hot pressure = {hot_psi:.1f} psi '
                                  f'(target {target_low:.0f}–{target_high:.0f})',
                    confidence=bundle.tire_confidence,
                    reasoning=(
                        f'{corner} tire running {hot_psi:.1f} psi hot — '
                        f'{hot_psi - target_high:.1f} psi above target window. '
                        f'Reducing cold pressure by {adjustment:.1f} psi '
                        f'prevents overheating and contact patch reduction.'
                    ),
                    driver_feel=(
                        'Slightly softer initial feel. Tire will maintain '
                        'grip better over longer stints.'
                    ),
                    priority=0,
                ))

        return results

    # ── DIFFERENTIAL ─────────────────────────────────────────────────────────

    def _diff_rules(self, bundle: SignalBundle,
                     car_class: CarClass) -> List[SetupDelta]:
        results = []
        bounds = get_bounds(car_class)
        exit_os = bundle.balance_exit
        conf = bundle.balance_confidence

        if conf < MIN_CONFIDENCE or not bounds.get('diff_power'):
            return results

        b = bounds['diff_power']
        current = self._current(bundle, 'diff_power',
                                 (b.min_val + b.max_val) / 2)

        if exit_os > BALANCE_OS_STRONG:
            # Power-on exit oversteer — loosen diff (increase ramp angle)
            delta = b.step * 2
            results.append(SetupDelta(
                param='diff_power',
                display_name='Diff Power Ramp',
                garage_tab='CHASSIS',
                garage_location=PARAM_GARAGE_INFO['diff_power'][1],
                current_value=current,
                recommended_value=current,
                delta=+delta,
                unit=b.unit,
                signal_source=f'Exit oversteer = {exit_os:+.2f}',
                confidence=conf * 0.85,
                reasoning=(
                    f'Power-on exit oversteer of {exit_os:+.2f} indicates the '
                    f'diff is locking too aggressively under acceleration, '
                    f'overloading the inside rear. Increasing power ramp angle '
                    f'by {delta:.0f}° reduces locking force and allows more '
                    f'wheelspin management.'
                ),
                driver_feel=(
                    'Throttle application on exit will feel more forgiving. '
                    'The car will be less "sharp" on power but more stable.'
                ),
                priority=0,
            ))

        elif exit_os < BALANCE_US_MILD:
            # Exit understeer — tighten diff
            delta = b.step
            results.append(SetupDelta(
                param='diff_power',
                display_name='Diff Power Ramp',
                garage_tab='CHASSIS',
                garage_location=PARAM_GARAGE_INFO['diff_power'][1],
                current_value=current,
                recommended_value=current,
                delta=-delta,
                unit=b.unit,
                signal_source=f'Exit understeer = {exit_os:+.2f}',
                confidence=conf * 0.7,
                reasoning=(
                    f'Exit understeer of {exit_os:+.2f} — reducing power ramp '
                    f'angle tightens the diff under acceleration, pushing both '
                    f'rear tires together and improving traction out of slow corners.'
                ),
                driver_feel=(
                    'More forward drive on corner exit. Car will feel '
                    'more planted on throttle application.'
                ),
                priority=0,
            ))

        return results

    # ── DAMPERS ──────────────────────────────────────────────────────────────

    def _damper_rules(self, bundle: SignalBundle,
                       car_class: CarClass) -> List[SetupDelta]:
        """
        Damper recommendations only when there's a clear mechanical signal.
        Require higher confidence than ARB/brake changes.
        """
        results = []
        if bundle.balance_confidence < 0.65:
            return results

        bounds = get_bounds(car_class)

        # If entry oversteer persists after brake bias change suggestion,
        # rear damper rebound may be releasing too fast
        if (bundle.balance_entry > BALANCE_OS_STRONG and
                bundle.brake_bias_direction == 'too_rearward'):
            b = bounds.get('rebound_slow_lr')
            if b:
                cur_lr = self._current(bundle, 'rebound_slow_lr',
                                        (b.min_val + b.max_val) / 2)
                cur_rr = self._current(bundle, 'rebound_slow_rr', cur_lr)
                for param, cur, name in [
                    ('rebound_slow_lr', cur_lr, 'LR Slow Rebound'),
                    ('rebound_slow_rr', cur_rr, 'RR Slow Rebound'),
                ]:
                    results.append(SetupDelta(
                        param=param,
                        display_name=name,
                        garage_tab='DAMPERS',
                        garage_location=PARAM_GARAGE_INFO[param][1],
                        current_value=cur,
                        recommended_value=cur,
                        delta=+1,
                        unit='clicks',
                        signal_source=f'Entry oversteer {bundle.balance_entry:+.2f} '
                                      f'with rearward brake bias',
                        confidence=bundle.balance_confidence * 0.65,
                        reasoning=(
                            f'Combined entry oversteer and rearward brake bias '
                            f'signal suggests the rear is also recovering from '
                            f'weight transfer too quickly. +1 click slow rebound '
                            f'slows rear body return, keeping rear tires loaded '
                            f'longer through the braking phase.'
                        ),
                        driver_feel=(
                            'More settled rear under braking. Address brake '
                            'bias first — this is a secondary refinement.'
                        ),
                        priority=0,
                    ))

        return results

    # ── AERO ─────────────────────────────────────────────────────────────────

    def _aero_rules(self, bundle: SignalBundle,
                     car_class: CarClass) -> List[SetupDelta]:
        results = []
        bounds = get_bounds(car_class)
        conf = bundle.balance_confidence

        if conf < 0.6:
            return results

        b_rear = bounds.get('wing_rear')
        if not b_rear or b_rear.max_val <= 3:
            # Cup cars / fixed aero — skip
            return results

        has_fast = getattr(bundle, 'has_fast_corners', False)
        has_slow = getattr(bundle, 'has_slow_corners', False)

        # High-speed OS + low-speed neutral → aero balance too loose at rear
        fast_os = [c.mid_os for c in bundle.corners
                   if c.speed_class == 'fast' and c.confidence >= 0.4]
        slow_os = [c.mid_os for c in bundle.corners
                   if c.speed_class == 'slow' and c.confidence >= 0.4]

        if fast_os and slow_os:
            avg_fast = sum(fast_os) / len(fast_os)
            avg_slow = sum(slow_os) / len(slow_os)

            if avg_fast > BALANCE_OS_MILD and avg_slow < BALANCE_OS_MILD:
                cur = self._current(bundle, 'wing_rear',
                                     (b_rear.min_val + b_rear.max_val) / 2)
                results.append(SetupDelta(
                    param='wing_rear',
                    display_name='Rear Wing',
                    garage_tab='TIRES/AERO',
                    garage_location=PARAM_GARAGE_INFO['wing_rear'][1],
                    current_value=cur,
                    recommended_value=cur,
                    delta=+1,
                    unit='step',
                    signal_source=(
                        f'Fast corner OS avg={avg_fast:+.2f}, '
                        f'slow corner OS avg={avg_slow:+.2f}'
                    ),
                    confidence=conf * 0.75,
                    reasoning=(
                        f'Oversteer at high-speed corners ({avg_fast:+.2f}) '
                        f'but neutral at slow corners ({avg_slow:+.2f}) indicates '
                        f'an aero balance issue. +1 rear wing step adds rear '
                        f'downforce specifically at speed where it is needed.'
                    ),
                    driver_feel=(
                        'More stable at high speed. Slight drag increase on '
                        'straights. No feel change in slow corners.'
                    ),
                    priority=0,
                ))

        return results

    # ── HELPERS ─────────────────────────────────────────────────────────────

    def _current(self, bundle: SignalBundle, param: str,
                  default: float) -> float:
        """Get current value from setup, fallback to default."""
        val = bundle.current_setup.get(param)
        if val is None:
            # Try display name variants from setup flat dict
            # (IBT setups use human-readable keys like 'Front ARB Setting')
            return default
        try:
            return float(val)
        except (TypeError, ValueError):
            return default

    def _prioritise(self, deltas: List[SetupDelta],
                     bundle: SignalBundle) -> List[SetupDelta]:
        """Assign priority 1–N based on expected impact."""
        # Priority ordering logic:
        # 1. Safety-critical (large entry oversteer → brake bias)
        # 2. Biggest balance issue (mid OS/US → ARB)
        # 3. Tire compound issues (pressures, camber)
        # 4. Exit behavior (diff, rear dampers)
        # 5. Aero refinement

        priority_order = {
            'brake_bias':       10,
            'arb_rear':         20,
            'arb_front':        20,
            'diff_power':       30,
            'diff_coast':       35,
            'spring_lf':        40,
            'spring_rf':        40,
            'spring_lr':        45,
            'spring_rr':        45,
            'pressure_lf':      50,
            'pressure_rf':      50,
            'pressure_lr':      55,
            'pressure_rr':      55,
            'camber_lf':        60,
            'camber_rf':        60,
            'camber_lr':        65,
            'camber_rr':        65,
            'rebound_slow_lr':  70,
            'rebound_slow_rr':  70,
            'bump_slow_lf':     75,
            'bump_slow_rf':     75,
            'wing_rear':        80,
            'wing_front':       85,
            'toe_front':        90,
            'toe_rear':         90,
        }

        for d in deltas:
            d.priority = priority_order.get(d.param, 99)

        return sorted(deltas, key=lambda d: d.priority)


# ─────────────────────────────────────────────────────────────────────────────
# 3. SETUP ASSEMBLER
# ─────────────────────────────────────────────────────────────────────────────

class SetupAssembler:
    """
    Takes a list of SetupDelta + baseline setup dict and:
    1. Applies each delta to compute final absolute values
    2. Clamps every value through tech_inspector.clamp_to_legal()
    3. Notes any clamping that occurred
    4. Runs validate_setup() and returns with tech_pass=True guarantee
    """

    def assemble(
        self,
        baseline: Dict[str, Any],
        deltas: List[SetupDelta],
        car_class: CarClass,
        car_name: str,
        track_name: str,
        laps_analyzed: int,
        confidence: float,
    ) -> SetupResult:

        bounds = get_bounds(car_class)

        # Start from baseline (convert all to float where possible)
        working: Dict[str, float] = {}
        for k, v in baseline.items():
            try:
                working[k] = float(v)
            except (TypeError, ValueError):
                pass

        finalized_deltas: List[SetupDelta] = []

        for delta in deltas:
            b = bounds.get(delta.param)
            if b is None:
                logger.debug("setup_generator: no bounds for %s — skipping", delta.param)
                continue

            # Determine baseline value
            baseline_val = working.get(delta.param)
            if baseline_val is None:
                # Use midpoint of legal range as safe default
                baseline_val = (b.min_val + b.max_val) / 2
                baseline_val = b.clamp(baseline_val)

            # Apply delta
            raw_recommended = baseline_val + delta.delta

            # Snap to step
            snapped = round(round(raw_recommended / b.step) * b.step, 6)

            # Clamp to legal range
            clamped = b.clamp(snapped)
            was_clamped = abs(clamped - snapped) > 1e-6

            clamp_note = ""
            if was_clamped:
                clamp_note = (
                    f"Value adjusted from {snapped:.3g} to {clamped:.3g} "
                    f"{b.unit} to stay within legal range "
                    f"({b.min_val:.3g}–{b.max_val:.3g} {b.unit})."
                )
                logger.info("setup_generator: %s clamped %s → %s",
                             delta.param, snapped, clamped)

            # Skip if delta is effectively zero after clamping
            effective_delta = clamped - baseline_val
            if abs(effective_delta) < 1e-9:
                logger.debug("setup_generator: %s delta zeroed out after clamp",
                              delta.param)
                continue

            # Update working setup
            working[delta.param] = clamped

            finalized_deltas.append(SetupDelta(
                param=delta.param,
                display_name=delta.display_name,
                garage_tab=delta.garage_tab,
                garage_location=delta.garage_location,
                current_value=baseline_val,
                recommended_value=clamped,
                delta=effective_delta,
                unit=delta.unit,
                signal_source=delta.signal_source,
                confidence=delta.confidence,
                reasoning=delta.reasoning,
                driver_feel=delta.driver_feel,
                priority=delta.priority,
                clamped=was_clamped,
                clamp_note=clamp_note,
            ))

        # ── TECH INSPECTION ──────────────────────────────────────────────────
        issues = validate_setup(working, car_class, car_name=car_name)
        tech_pass = len(issues) == 0

        if not tech_pass:
            # Force-clamp any remaining violations — should never happen
            # but this is the absolute safety net
            working = clamp_to_legal(working, car_class)
            issues = validate_setup(working, car_class, car_name=car_name)
            tech_pass = len(issues) == 0
            logger.warning(
                "setup_generator: had to force-clamp %d issue(s). "
                "Final tech_pass=%s", len(issues) if not tech_pass else 0,
                tech_pass
            )

        # ── BUILD CHANGES TABLE ──────────────────────────────────────────────
        changes_table = self._build_changes_table(finalized_deltas)

        return SetupResult(
            tech_pass=tech_pass,
            tech_issues=issues,
            deltas=finalized_deltas,
            final_setup=working,
            baseline_setup=dict(baseline),
            car_name=car_name,
            track_name=track_name,
            car_class=car_class,
            laps_analyzed=laps_analyzed,
            confidence_overall=confidence,
            changes_table=changes_table,
        )

    def _build_changes_table(self,
                              deltas: List[SetupDelta]) -> List[dict]:
        """Build UI-ready rows ordered by garage tab + priority."""
        rows = []
        # Group by tab
        tab_groups: Dict[str, List[SetupDelta]] = {}
        for d in deltas:
            tab_groups.setdefault(d.garage_tab, []).append(d)

        for tab in TAB_ORDER:
            group = tab_groups.get(tab, [])
            for d in sorted(group, key=lambda x: x.priority):
                sign = '+' if d.delta > 0 else ''
                rows.append({
                    'tab':         tab,
                    'location':    d.garage_location,
                    'param':       d.display_name,
                    'current':     f"{d.current_value:.3g} {d.unit}",
                    'recommended': f"{d.recommended_value:.3g} {d.unit}",
                    'delta':       f"{sign}{d.delta:.3g} {d.unit}",
                    'clamped':     d.clamped,
                    'clamp_note':  d.clamp_note,
                    'priority':    d.priority,
                    'reasoning':   d.reasoning,
                    'driver_feel': d.driver_feel,
                })
        return rows


# ─────────────────────────────────────────────────────────────────────────────
# 4. BRIEF GENERATOR PROMPT BUILDER
# ─────────────────────────────────────────────────────────────────────────────

def build_brief_prompt(result: SetupResult) -> str:
    """
    Build the AI prompt that generates the driver brief.
    This is called from ai_advisor.py — the AI call itself lives there.
    The prompt is deterministic and data-specific.
    """
    if not result.deltas:
        return (
            f"Car: {result.car_name}, Track: {result.track_name}. "
            f"Telemetry analysis of {result.laps_analyzed} laps shows "
            f"no significant setup changes are needed — the car is well-balanced. "
            f"Write a short driver brief (3–4 sentences) confirming this and "
            f"noting the strongest performance areas."
        )

    changes_block = "\n".join([
        f"  {i+1}. {d.display_name}: "
        f"{d.current_value:.3g} → {d.recommended_value:.3g} {d.unit} "
        f"({'+' if d.delta > 0 else ''}{d.delta:.3g}) | "
        f"Signal: {d.signal_source}"
        for i, d in enumerate(result.deltas)
    ])

    top = result.deltas[0]

    return f"""You are a professional race engineer writing a setup brief for a sim driver.

Car: {result.car_name}
Track: {result.track_name}
Laps analyzed: {result.laps_analyzed}
Overall confidence: {result.confidence_overall:.0%}
Tech inspection: {"PASS ✓" if result.tech_pass else "FAIL — do not use"}

Setup changes (all values pass tech inspection):
{changes_block}

Write a driver brief with these exact sections — no markdown headers, no bullet points:

OPENING: One sentence naming the biggest issue the data found and what was changed.

CHANGES: For each change, one sentence explaining what the data showed and what the setup change does. Reference actual numbers from the signal source. Maximum 2 sentences per change. Order by priority — most impactful first.

GARAGE WALKTHROUGH: One sentence telling the driver which tab to open first and what to change. Then one sentence for the next tab. Match the iRacing garage tab names exactly (TIRES/AERO, CHASSIS, DAMPERS).

DRIVER NOTE: One sentence on what they will feel differently in the first lap out, and one sentence reminding them to run 3–5 laps before judging the change.

Total length: 120–180 words. Speak directly to the driver. Use their data — not generic advice."""


# ─────────────────────────────────────────────────────────────────────────────
# 5. PUBLIC API
# ─────────────────────────────────────────────────────────────────────────────

def generate_setup(
    analysis=None,
    corner_report=None,
    style_report=None,
    consistency=None,
    baseline_setup: Dict = None,
    car_class=None,
    car_name: str = "",
    track_name: str = "",
    session_info: dict = None,
) -> SetupResult:
    """
    Main entry point. Takes all available analysis objects and returns a
    SetupResult with tech_pass=True guaranteed.

    Parameters
    ----------
    analysis        : AnalysisReport from analysis_engine
    corner_report   : CornerAnalysisReport from corner_analysis
    style_report    : DriverStyleReport from driving_style
    consistency     : ConsistencyBreakdown from consistency_score
    baseline_setup  : dict — current setup values
    car_class       : CarClass enum or string
    car_name        : str
    track_name      : str
    session_info    : dict — IBT session YAML fields (air_temp_c, track_temp_c,
                      wind_speed_ms, wind_direction_deg, skies, etc.)
                      Used by WeatherEngine to condition-adjust all deltas.
    """
    # Resolve car class
    if car_class is None:
        car_class = CarClass.DEFAULT
    elif not isinstance(car_class, CarClass):
        from core.tech_inspector import _resolve_car_class
        car_class = _resolve_car_class(car_class)

    baseline = baseline_setup or {}
    laps = getattr(analysis, 'lap_count', 0) or 0
    conf = min(1.0, laps / 10.0)

    # 1. Extract signals
    extractor = IBTSignalExtractor()
    bundle = extractor.extract(
        analysis=analysis,
        corner_report=corner_report,
        style_report=style_report,
        consistency=consistency,
        car_name=car_name,
        track_name=track_name,
        car_class=car_class,
        baseline_setup=baseline,
    )

    # 2. Compute deltas
    engine = SetupDeltaEngine()
    deltas = engine.compute_deltas(bundle, car_class)

    # 2b. Weather-condition adjustments (post-processing pass)
    weather_report = None
    weather_adjustments = []
    try:
        from core.weather_engine import WeatherConditions, WeatherEngine
        si = session_info or (getattr(analysis, 'session_info', None) if analysis else None) or {}
        conditions = WeatherConditions.from_session_info(si)
        w_engine = WeatherEngine(conditions)
        # Adjust existing deltas for conditions
        deltas = w_engine.adjust_deltas(
            deltas,
            car_class_str=car_class.value if hasattr(car_class, 'value') else str(car_class),
            car_name=car_name,
        )
        # Get standalone weather-only adjustments
        weather_adjustments = w_engine.get_weather_adjustments(
            car_class_str=car_class.value if hasattr(car_class, 'value') else str(car_class))
        weather_report = w_engine.condition_report()
        logger.info(
            'WeatherEngine: condition=%s track=%.0f°C air=%.0f°C '
            'grip=%.2f pressure_corr=%+.2f psi',
            weather_report['condition'],
            conditions.track_temp_c,
            conditions.air_temp_c,
            weather_report['grip_factor'],
            weather_report['pressure_correction_avg_psi'],
        )
    except Exception as _we:
        logger.debug('WeatherEngine failed: %s', _we)

    logger.info(
        "setup_generator: %d deltas computed from %d laps "
        "(car=%s, track=%s)",
        len(deltas), laps, car_name, track_name
    )

    # 3. Assemble + validate
    assembler = SetupAssembler()
    result = assembler.assemble(
        baseline=baseline,
        deltas=deltas,
        car_class=car_class,
        car_name=car_name,
        track_name=track_name,
        laps_analyzed=laps,
        confidence=conf,
    )

    # 4. Build brief prompt (stored on result — AI call is caller's job)
    result.driver_brief   = build_brief_prompt(result)
    result.weather_report = weather_report

    logger.info(
        "setup_generator: result tech_pass=%s, %d changes, "
        "%d tech issues",
        result.tech_pass, len(result.deltas), len(result.tech_issues)
    )

    return result
