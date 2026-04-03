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


# ─────────────────────────────────────────────────────────────────────────────
# SIGNAL THRESHOLDS
# ─────────────────────────────────────────────────────────────────────────────

# Minimum laps before we trust a signal enough to recommend a change
MIN_LAPS_FOR_CHANGE = 3

# Balance score thresholds
BALANCE_OS_STRONG   =  0.40   # strong oversteer — act on it
BALANCE_OS_MILD     =  0.15   # mild oversteer — note it, small change
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

    def _extract_tire(self, bundle: SignalBundle, analysis):
        if not analysis:
            return
        tire_summary = getattr(analysis, 'tire_summary', None)
        if tire_summary:
            bundle.tire_temps = tire_summary
            bundle.tire_confidence = min(1.0, bundle.laps_analyzed / 5.0)

        # Hot tire pressures
        tire_pressure = getattr(analysis, 'tire_pressure_hot', None)
        if tire_pressure:
            bundle.tire_pressure_hot = tire_pressure

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
        deltas += self._arb_rules(bundle, effective_class)
        deltas += self._spring_rules(bundle, effective_class)
        deltas += self._camber_rules(bundle, effective_class)
        deltas += self._tire_pressure_rules(bundle, effective_class)
        deltas += self._diff_rules(bundle, effective_class)
        deltas += self._damper_rules(bundle, effective_class)
        deltas += self._aero_rules(bundle, effective_class)

        # Filter below confidence threshold
        deltas = [d for d in deltas if d.confidence >= MIN_CONFIDENCE]

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

        mid_os  = bundle.balance_mid
        exit_os = bundle.balance_exit

        # Mid-corner oversteer: soften rear ARB
        if mid_os > BALANCE_OS_MILD and b_rear:
            strength = 1 if mid_os < BALANCE_OS_STRONG else 2
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

    # ── SPRINGS ─────────────────────────────────────────────────────────────

    def _spring_rules(self, bundle: SignalBundle,
                       car_class: CarClass) -> List[SetupDelta]:
        results = []
        # Springs are high-consequence changes — require strong signal + confidence
        if bundle.balance_confidence < 0.6:
            return results

        bounds = get_bounds(car_class)
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

        # Target hot pressure range (psi) — varies by car class
        target_ranges = {
            CarClass.GT3:         (30.0, 34.0),
            CarClass.GT4:         (29.0, 33.0),
            CarClass.PORSCHE_CUP: (30.0, 34.0),
            CarClass.GTP:         (26.0, 30.0),
            CarClass.FORMULA:     (22.0, 26.0),
            CarClass.TCR:         (31.0, 35.0),
        }
        target_low, target_high = target_ranges.get(
            car_class, (29.0, 34.0)
        )

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
        issues = validate_setup(working, car_class)
        tech_pass = len(issues) == 0

        if not tech_pass:
            # Force-clamp any remaining violations — should never happen
            # but this is the absolute safety net
            working = clamp_to_legal(working, car_class)
            issues = validate_setup(working, car_class)
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
    baseline_setup  : dict — current setup values (from parsed_setup.flat or
                      similar). Keys should match tech_inspector param names
                      where possible.
    car_class       : CarClass enum or string
    car_name        : str — used for display and bounds lookup
    track_name      : str — used for display and track character detection

    Returns
    -------
    SetupResult with tech_pass=True and populated deltas, final_setup,
    and driver_brief prompt (call ai_advisor to render brief text).
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
    result.driver_brief = build_brief_prompt(result)

    logger.info(
        "setup_generator: result tech_pass=%s, %d changes, "
        "%d tech issues",
        result.tech_pass, len(result.deltas), len(result.tech_issues)
    )

    return result
