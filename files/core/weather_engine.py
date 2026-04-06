"""
weather_engine.py — Track condition and weather-aware setup adjustments.

iRacing's physics engine is highly sensitive to environmental conditions.
This module computes condition-specific setup adjustments on top of the
base setup_generator output. It runs as a post-processing pass.

Physics modelled:
  1. Tire pressure correction (temp differential from baseline)
  2. Mechanical grip change (track temp, rubber level, wetness)
  3. Aerodynamic efficiency change (air density from temp + altitude)
  4. Spring/ARB sensitivity (cold tires behave differently at low temp)
  5. Brake bias sensitivity (cold brakes = less rear grip early = more US)
  6. Wind effects on aero balance (headwind vs tailwind per sector)
  7. Time-of-day: track temp evolution, rubber laid down through a session
  8. Wet/damp condition overrides (tire compound, setup philosophy shift)

Data sources (all from IBT session YAML):
  - AirTemp (°C)
  - TrackTempCrew (°C)
  - WindVel (m/s) + WindDir (deg)
  - Skies / WeatherType
  - SessionTimeOfDay (seconds since midnight → local time)
  - Track rubber level (inferred from track temp vs air temp delta)

Usage:
    from core.weather_engine import WeatherEngine, WeatherConditions
    conditions = WeatherConditions.from_session_info(session_info_dict)
    engine = WeatherEngine(conditions)
    adjusted = engine.adjust_deltas(deltas, car_class, car_name)
    report = engine.condition_report()
"""

from __future__ import annotations
import logging
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────
STANDARD_TRACK_TEMP_C   = 30.0   # baseline track temp all rules calibrated to
STANDARD_AIR_TEMP_C     = 20.0   # baseline air temp
STANDARD_AIR_DENSITY    = 1.225  # kg/m³ at 15°C sea level
ISA_TEMP_LAPSE          = 0.0065 # K/m (standard atmosphere)
GAS_CONSTANT_DRY_AIR    = 287.05 # J/(kg·K)
PSI_PER_DEGF_CORRECTION = 0.11   # psi per °F ambient change in tire pressure

# Track surface condition classifications
class TrackCondition(Enum):
    DRY_RUBBERED   = 'dry_rubbered'    # Optimal — race conditions
    DRY_GREEN      = 'dry_green'       # First session on fresh asphalt
    DRY_HOT        = 'dry_hot'         # >45°C track temp — tire deg risk
    DRY_COLD       = 'dry_cold'        # <15°C track temp — slow warm-up
    DAMP           = 'damp'            # Drying after rain — patchy grip
    WET            = 'wet'             # Full wet conditions
    VERY_WET       = 'very_wet'        # Standing water risk

class TimeOfDay(Enum):
    DAWN       = 'dawn'       # 05:00–08:00 — cold track, low rubber
    MORNING    = 'morning'    # 08:00–11:00 — warming, moderate rubber
    MIDDAY     = 'midday'     # 11:00–15:00 — peak temp, high rubber
    AFTERNOON  = 'afternoon'  # 15:00–18:00 — warm but falling
    EVENING    = 'evening'    # 18:00–21:00 — cooling fast
    NIGHT      = 'night'      # 21:00–05:00 — cold, low rubber, dew risk


@dataclass
class WeatherConditions:
    """Parsed weather state from IBT session_info."""
    air_temp_c:       float = STANDARD_AIR_TEMP_C
    track_temp_c:     float = STANDARD_TRACK_TEMP_C
    wind_vel_ms:      float = 0.0
    wind_dir_deg:     float = 0.0
    humidity_pct:     float = 50.0
    skies:            str   = 'Clear'
    weather_type:     str   = 'Dry'
    session_time_s:   float = 43200.0  # default: noon
    altitude_m:       float = 0.0
    track_wetness:    int   = 0        # 0=dry, 1=damp, 2=wet, 3+=very wet
    fog_level:        float = 0.0

    # Derived fields (computed in __post_init__)
    track_condition:  TrackCondition = field(default=TrackCondition.DRY_RUBBERED,
                                              init=False)
    time_of_day:      TimeOfDay      = field(default=TimeOfDay.MIDDAY, init=False)
    air_density:      float          = field(default=STANDARD_AIR_DENSITY, init=False)
    temp_delta_from_baseline: float  = field(default=0.0, init=False)

    def __post_init__(self):
        self._classify_condition()
        self._classify_time()
        self._compute_air_density()
        self.temp_delta_from_baseline = self.track_temp_c - STANDARD_TRACK_TEMP_C

    def _classify_condition(self):
        wt = (self.weather_type or '').lower()
        sky = (self.skies or '').lower()
        wet = self.track_wetness

        if wet >= 3 or 'rain' in sky or 'storm' in wt:
            self.track_condition = TrackCondition.VERY_WET
        elif wet == 2 or 'wet' in wt:
            self.track_condition = TrackCondition.WET
        elif wet == 1 or 'damp' in wt or 'mist' in sky:
            self.track_condition = TrackCondition.DAMP
        elif self.track_temp_c > 45.0:
            self.track_condition = TrackCondition.DRY_HOT
        elif self.track_temp_c < 15.0:
            self.track_condition = TrackCondition.DRY_COLD
        else:
            # Check for green track (track much colder than air = first session)
            td = self.track_temp_c - self.air_temp_c
            if td < 3.0 and self.track_temp_c < 25.0:
                self.track_condition = TrackCondition.DRY_GREEN
            else:
                self.track_condition = TrackCondition.DRY_RUBBERED

    def _classify_time(self):
        h = (self.session_time_s % 86400) / 3600
        if 5 <= h < 8:
            self.time_of_day = TimeOfDay.DAWN
        elif 8 <= h < 11:
            self.time_of_day = TimeOfDay.MORNING
        elif 11 <= h < 15:
            self.time_of_day = TimeOfDay.MIDDAY
        elif 15 <= h < 18:
            self.time_of_day = TimeOfDay.AFTERNOON
        elif 18 <= h < 21:
            self.time_of_day = TimeOfDay.EVENING
        else:
            self.time_of_day = TimeOfDay.NIGHT

    def _compute_air_density(self):
        """ISA air density from temperature + altitude."""
        T_K = self.air_temp_c + 273.15
        # Pressure at altitude using barometric formula
        P_pa = 101325.0 * (1 - (ISA_TEMP_LAPSE * self.altitude_m / 288.15)) ** 5.2561
        # Density: ρ = P / (R_specific × T)
        self.air_density = P_pa / (GAS_CONSTANT_DRY_AIR * T_K)

    @classmethod
    def from_session_info(cls, si: dict) -> 'WeatherConditions':
        """Parse from IBT session_info dict."""
        if si is None:
            return cls()
        def _g(key, default=0.0):
            val = si.get(key)
            if val is None:
                return default
            try:
                return float(val)
            except (TypeError, ValueError):
                return default

        return cls(
            air_temp_c     = _g('air_temp_c', STANDARD_AIR_TEMP_C),
            track_temp_c   = _g('track_temp_c', STANDARD_TRACK_TEMP_C),
            wind_vel_ms    = _g('wind_speed_ms', 0.0),
            wind_dir_deg   = _g('wind_direction_deg', 0.0),
            humidity_pct   = _g('relative_humidity', 50.0),
            skies          = str(si.get('skies') or si.get('Skies') or 'Clear'),
            weather_type   = str(si.get('weather_type') or si.get('WeatherType') or 'Dry'),
            session_time_s = _g('session_time_of_day', 43200.0),
            altitude_m     = _g('track_altitude_m', 0.0),
            track_wetness  = int(_g('track_wetness', 0)),
            fog_level      = _g('fog_level', 0.0),
        )

    @property
    def is_wet(self) -> bool:
        return self.track_condition in (
            TrackCondition.WET, TrackCondition.VERY_WET, TrackCondition.DAMP)

    @property
    def is_cold(self) -> bool:
        return self.track_temp_c < 20.0

    @property
    def is_hot(self) -> bool:
        return self.track_temp_c > 42.0

    @property
    def air_density_ratio(self) -> float:
        """Air density relative to standard (1.225 kg/m³). <1 = thinner air."""
        return self.air_density / STANDARD_AIR_DENSITY


@dataclass
class WeatherAdjustment:
    """One weather-driven setup adjustment."""
    param:        str
    display_name: str
    delta:        float
    unit:         str
    reason:       str
    condition:    str
    confidence:   float
    priority:     int = 1


class WeatherEngine:
    """
    Computes weather-aware setup adjustments.

    All adjustments are ADDITIVE on top of the base setup_generator deltas.
    They represent the additional change needed because conditions differ
    from the calibration baseline (30°C track, 20°C air, dry, noon).

    Call adjust_deltas() to modify existing deltas.
    Call get_weather_adjustments() for standalone weather deltas.
    Call condition_report() for human-readable context.
    """

    def __init__(self, conditions: WeatherConditions):
        self.c = conditions

    # ── 1. TIRE PRESSURE ─────────────────────────────────────────────────────

    def tire_pressure_corrections(self) -> dict[str, float]:
        """
        Compute cold pressure adjustments per corner from track + air temp.

        Physics:
          - Each 10°F (5.6°C) of ambient temp change = ~0.11 psi cold pressure change
          - Track temp affects heat input, air temp affects starting temp
          - Wet conditions: reduce by 1-2 psi (less heat = less pressure build-up)
          - Cold green track: increase by 0.5-1.0 psi (slow warmup, lower peak pressures)
          - Hot conditions: reduce by 0.5-1.5 psi (higher heat input)
        """
        corrections: dict[str, float] = {}

        # Base correction from air temp delta vs standard 20°C
        air_delta_c = self.c.air_temp_c - STANDARD_AIR_TEMP_C
        air_delta_f = air_delta_c * 9 / 5
        base_corr = -(air_delta_f * PSI_PER_DEGF_CORRECTION)  # warm air = less cold pressure needed

        # Track temp modifier — hot track = more heat input = less cold pressure needed
        track_delta_c = self.c.track_temp_c - STANDARD_TRACK_TEMP_C
        if track_delta_c > 0:
            track_corr = -(track_delta_c * 0.025)   # ~0.025 psi per °C above baseline
        else:
            track_corr = -(track_delta_c * 0.035)   # slightly more sensitive below baseline

        total_corr = round(base_corr + track_corr, 2)

        # Wet: pressure builds up less (lower heat) → start lower
        if self.c.track_condition == TrackCondition.WET:
            total_corr -= 1.5
        elif self.c.track_condition == TrackCondition.DAMP:
            total_corr -= 0.75
        elif self.c.track_condition == TrackCondition.VERY_WET:
            total_corr -= 2.0

        # Cold/green: slow warmup → need more pressure to hit target
        if self.c.track_condition == TrackCondition.DRY_COLD:
            total_corr += 0.5
        elif self.c.track_condition == TrackCondition.DRY_GREEN:
            total_corr += 0.75

        # Hot: aggressive heat input → start lower to avoid overpressure
        if self.c.track_condition == TrackCondition.DRY_HOT:
            total_corr -= 0.75

        # Apply to all four corners (can differentiate L/R for wind later)
        for corner in ['LF', 'RF', 'LR', 'RR']:
            corrections[corner] = total_corr

        # Wind correction: downwind corners get more load → more heat → less cold pressure
        if self.c.wind_vel_ms > 4.0:  # >14 km/h significant
            wind_effect = min(0.3, self.c.wind_vel_ms * 0.03)
            # Right side correction for westerly wind (simplified)
            corrections['RF'] = round(corrections['RF'] - wind_effect, 2)
            corrections['RR'] = round(corrections['RR'] - wind_effect, 2)

        return corrections

    # ── 2. MECHANICAL GRIP ────────────────────────────────────────────────────

    def mechanical_grip_factor(self) -> float:
        """
        Grip factor 0.0–1.0 relative to baseline (1.0 = fully rubbered dry).
        Affects how aggressive setup changes should be — low grip = softer setup.
        """
        if self.c.track_condition == TrackCondition.VERY_WET:
            return 0.35
        if self.c.track_condition == TrackCondition.WET:
            return 0.50
        if self.c.track_condition == TrackCondition.DAMP:
            return 0.75
        if self.c.track_condition == TrackCondition.DRY_GREEN:
            return 0.82  # unrubbered = less peak grip
        if self.c.track_condition == TrackCondition.DRY_COLD:
            return 0.88  # cold tires take longer to come in
        if self.c.track_condition == TrackCondition.DRY_HOT:
            return 0.92  # hot = more initial grip but faster deg
        return 1.0  # DRY_RUBBERED baseline

    # ── 3. AERO EFFICIENCY ────────────────────────────────────────────────────

    def aero_downforce_factor(self) -> float:
        """
        Downforce factor relative to standard air density.
        Downforce ∝ ρ × v². Thinner air = less downforce.
        Hot/high-altitude tracks need more wing to compensate.
        """
        return self.c.air_density_ratio  # e.g. 0.95 at 40°C = 5% less downforce

    def wing_adjustment_steps(self) -> int:
        """
        Recommended wing adjustment from air density change.
        Every 3% density reduction ≈ 1 wing step more for same downforce.
        """
        density_loss_pct = (1.0 - self.aero_downforce_factor()) * 100
        steps = round(density_loss_pct / 3.0)
        return max(-2, min(2, steps))  # cap at ±2 steps

    # ── 4. SPRING/ARB SENSITIVITY ─────────────────────────────────────────────

    def spring_stiffness_modifier(self) -> float:
        """
        In cold/wet conditions, tire sidewalls are stiffer and provide
        less compliance. Reducing mechanical spring stiffness compensates
        for the reduced tire contribution to compliance.
        Returns multiplier on spring rate delta: <1.0 means soften further.
        """
        if self.c.is_wet:
            return 0.80   # wet = soften springs further (less tire compliance)
        if self.c.track_temp_c < 15.0:
            return 0.85   # cold = softer springs to help tire warm-up
        if self.c.track_temp_c < 20.0:
            return 0.92
        if self.c.is_hot:
            return 1.10   # hot = slightly stiffer to manage tire contact patch
        return 1.0

    def arb_stiffness_modifier(self) -> float:
        """
        In wet/cold conditions, ARBs should be softer to allow the
        tire to find grip rather than fighting body roll mechanically.
        """
        if self.c.track_condition == TrackCondition.VERY_WET:
            return 0.65
        if self.c.track_condition == TrackCondition.WET:
            return 0.75
        if self.c.track_condition == TrackCondition.DAMP:
            return 0.88
        if self.c.is_cold:
            return 0.90
        return 1.0

    # ── 5. BRAKE BIAS SENSITIVITY ─────────────────────────────────────────────

    def brake_bias_adjustment(self) -> float:
        """
        Cold/wet conditions reduce rear grip. In wet, move bias rearward
        slightly less aggressively (more front bias to avoid rear lock).
        In cold green track conditions, bias should be slightly more forward
        until tires come in.
        Cold air also affects brake fluid — slightly less pressure needed.
        Returns delta in % to apply to brake_bias recommendations.
        """
        if self.c.track_condition == TrackCondition.WET:
            return +1.5   # more front bias in wet (rear locks easily)
        if self.c.track_condition == TrackCondition.VERY_WET:
            return +2.0
        if self.c.track_condition == TrackCondition.DAMP:
            return +0.75
        if self.c.track_condition == TrackCondition.DRY_GREEN:
            return +0.5   # green track = less rear bite
        if self.c.track_condition == TrackCondition.DRY_COLD:
            return +0.5
        return 0.0

    # ── 6. CAMBER SENSITIVITY ─────────────────────────────────────────────────

    def camber_temperature_modifier(self) -> float:
        """
        Cold conditions: tires run cooler overall, inner shoulders benefit
        from more camber to help heat generation.
        Hot conditions: reduce camber slightly (already plenty of heat).
        Returns delta degrees to add to camber recommendation magnitude.
        """
        if self.c.track_temp_c < 15.0:
            return -0.2   # more negative camber to generate heat faster
        if self.c.track_temp_c < 22.0:
            return -0.1
        if self.c.track_temp_c > 45.0:
            return +0.15  # reduce camber — already getting plenty of heat
        if self.c.track_temp_c > 38.0:
            return +0.08
        return 0.0

    # ── 7. TIME-OF-DAY ────────────────────────────────────────────────────────

    def time_of_day_context(self) -> list[str]:
        """
        Return context strings about time-of-day effects for AI prompt.
        """
        notes = []
        tod = self.c.time_of_day

        if tod == TimeOfDay.DAWN:
            notes.append('DAWN session: track temperature still rising — expect +3-6°C track temp during session. Setup built for start of session may be too soft by end.')
        elif tod == TimeOfDay.MORNING:
            notes.append('MORNING session: track warming rapidly. Tire pressures will build more than usual. Consider starting 0.5 psi lower than normal target.')
        elif tod == TimeOfDay.MIDDAY:
            notes.append('MIDDAY: peak track temperature. Tire pressure targets as-calibrated.')
        elif tod == TimeOfDay.AFTERNOON:
            notes.append('AFTERNOON: track temp stable or slightly falling. Rubber level at maximum — best grip of the day.')
        elif tod == TimeOfDay.EVENING:
            notes.append('EVENING: track cooling fast — expect 5-10°C drop during session. Grip will decrease progressively. Slightly more tire warm-up time needed.')
        elif tod == TimeOfDay.NIGHT:
            notes.append('NIGHT: cold track, low rubber level. Expect slow tire warm-up — first 3 laps are not representative. Dew risk on certain track surfaces reduces grip further.')

        # Rubber level inference
        if self.c.track_temp_c - self.c.air_temp_c > 15:
            notes.append('Track temp significantly above air temp — suggests high rubber level from prior sessions. Maximum mechanical grip available.')
        elif self.c.track_temp_c - self.c.air_temp_c < 4:
            notes.append('Track temp close to air temp — low rubber level or early in day. Grip will build through session as rubber is laid down.')

        return notes

    # ── 8. WIND EFFECTS ───────────────────────────────────────────────────────

    def wind_context(self) -> str:
        """Wind speed and direction context for AI prompt."""
        if self.c.wind_vel_ms < 2.0:
            return ''
        kmh = self.c.wind_vel_ms * 3.6
        if kmh < 15:
            severity = 'light'
        elif kmh < 30:
            severity = 'moderate'
        elif kmh < 50:
            severity = 'strong'
        else:
            severity = 'very strong'

        return (f'{severity.title()} wind ({kmh:.0f} km/h @ {self.c.wind_dir_deg:.0f}°). '
                f'High-speed corners into the wind will feel more stable (more downforce); '
                f'downwind sections will feel looser. Consider +1 rear wing step if '
                f'wind is consistently into slow corners.')

    # ── MAIN INTERFACE ────────────────────────────────────────────────────────

    def adjust_deltas(self, deltas: list, car_class_str: str = '',
                      car_name: str = '') -> list:
        """
        Apply weather-driven modifiers to existing setup deltas.
        Modifies delta values in place. Returns the modified list.
        """
        if not deltas:
            return deltas

        grip_factor = self.mechanical_grip_factor()
        spring_mod  = self.spring_stiffness_modifier()
        arb_mod     = self.arb_stiffness_modifier()
        brake_adj   = self.brake_bias_adjustment()
        camber_adj  = self.camber_temperature_modifier()
        psi_corr    = self.tire_pressure_corrections()
        wing_adj    = self.wing_adjustment_steps()

        for d in deltas:
            p = d.param.lower()

            # Tire pressure — add temperature correction
            if 'pressure' in p or 'cold_press' in p:
                corner_key = None
                for k in ['lf', 'rf', 'lr', 'rr']:
                    if k in p:
                        corner_key = k.upper()
                        break
                if corner_key and corner_key in psi_corr:
                    corr = psi_corr[corner_key]
                    if abs(corr) > 0.05:
                        d.delta = round(d.delta + corr, 2)
                        d.recommended_value = d.current_value + d.delta
                        d.signal_source = (d.signal_source or '') + \
                            f' | Weather Δ: {corr:+.2f} psi ({self.c.track_temp_c:.0f}°C track)'
                        logger.debug('Weather: %s pressure %+.2f psi', corner_key, corr)

            # Spring rate — scale by stiffness modifier
            elif 'spring' in p:
                if spring_mod != 1.0 and d.delta != 0:
                    d.delta = round(d.delta * spring_mod, 3)
                    d.recommended_value = d.current_value + d.delta
                    d.signal_source = (d.signal_source or '') + \
                        f' | Weather: spring ×{spring_mod:.2f} ({self.c.track_condition.value})'

            # ARB — scale by condition modifier
            elif 'arb' in p:
                if arb_mod != 1.0 and d.delta != 0:
                    orig = d.delta
                    d.delta = round(d.delta * arb_mod, 3)
                    d.recommended_value = d.current_value + d.delta
                    if abs(d.delta - orig) > 0.05:
                        d.signal_source = (d.signal_source or '') + \
                            f' | Weather: ARB ×{arb_mod:.2f} ({self.c.track_condition.value})'

            # Brake bias — add condition offset
            elif 'brake_bias' in p or 'brake bias' in p:
                if abs(brake_adj) > 0.1:
                    d.delta = round(d.delta + brake_adj, 2)
                    d.recommended_value = d.current_value + d.delta
                    d.signal_source = (d.signal_source or '') + \
                        f' | Weather: bias {brake_adj:+.1f}% ({self.c.track_condition.value})'

            # Camber — add temperature modifier to magnitude
            elif 'camber' in p:
                if abs(camber_adj) > 0.05 and d.delta != 0:
                    sign = 1 if d.delta < 0 else -1
                    d.delta = round(d.delta + sign * camber_adj, 3)
                    d.recommended_value = d.current_value + d.delta
                    d.signal_source = (d.signal_source or '') + \
                        f' | Weather: camber {sign * camber_adj:+.2f}° ({self.c.track_temp_c:.0f}°C)'

            # Wing — add air density adjustment
            elif 'wing' in p or 'aero' in p:
                if wing_adj != 0:
                    d.delta = d.delta + wing_adj
                    d.recommended_value = d.current_value + d.delta
                    d.signal_source = (d.signal_source or '') + \
                        f' | Air density: {self.c.air_density:.3f} kg/m³ ({wing_adj:+d} step)'

        # Low-grip conditions: reduce confidence on all aggressive deltas
        if grip_factor < 0.85:
            for d in deltas:
                d.confidence = min(d.confidence, d.confidence * (0.7 + grip_factor * 0.35))

        return deltas

    def get_weather_adjustments(self, car_class_str: str = '') -> list[WeatherAdjustment]:
        """
        Return standalone weather-only adjustments not tied to existing deltas.
        These fire even when the main setup_generator finds no issues.
        """
        adjustments: list[WeatherAdjustment] = []
        c = self.c

        # 1. Cold track: recommend tire blanket strategy (verbal note)
        if c.track_condition == TrackCondition.DRY_COLD:
            adjustments.append(WeatherAdjustment(
                param='tire_pressure_lf',
                display_name='Cold Track Pressure Start',
                delta=+0.5,
                unit='psi',
                reason=(f'Track temp {c.track_temp_c:.0f}°C — cold conditions. '
                        f'Start 0.5 psi higher than target to compensate for '
                        f'slow heat build-up on first 2-3 laps.'),
                condition=c.track_condition.value,
                confidence=0.85,
                priority=0,
            ))

        # 2. Hot track: reduce cold start pressures
        if c.track_condition == TrackCondition.DRY_HOT:
            adjustments.append(WeatherAdjustment(
                param='tire_pressure_lf',
                display_name='Hot Track Pressure Reduction',
                delta=-0.75,
                unit='psi',
                reason=(f'Track temp {c.track_temp_c:.0f}°C — high heat input. '
                        f'Reduce cold start pressure by 0.75 psi across all corners '
                        f'to avoid overheating and excessive pressure build-up.'),
                condition=c.track_condition.value,
                confidence=0.88,
                priority=0,
            ))

        # 3. Wet: global ARB softening note
        if c.is_wet:
            wetness = {
                TrackCondition.DAMP: 'Damp',
                TrackCondition.WET: 'Wet',
                TrackCondition.VERY_WET: 'Very Wet',
            }.get(c.track_condition, 'Wet')
            adjustments.append(WeatherAdjustment(
                param='arb_front',
                display_name=f'Wet Condition ARB',
                delta=-1,
                unit='step',
                reason=(f'{wetness} track ({c.track_wetness} wetness level). '
                        f'Soften both ARBs 1 step — wet surfaces reward mechanical '
                        f'compliance over stiffness. Allows tires to find grip '
                        f'rather than skipping over the wet surface.'),
                condition=c.track_condition.value,
                confidence=0.82,
                priority=0,
            ))

        # 4. Low air density: additional wing recommendation
        density_pct_loss = (1.0 - c.air_density_ratio) * 100
        if density_pct_loss > 5.0:
            adjustments.append(WeatherAdjustment(
                param='wing_rear',
                display_name='Low Air Density Wing Compensation',
                delta=+self.wing_adjustment_steps(),
                unit='step',
                reason=(f'Air density {c.air_density:.3f} kg/m³ '
                        f'({density_pct_loss:.0f}% below standard at '
                        f'{c.air_temp_c:.0f}°C and {c.altitude_m:.0f}m altitude). '
                        f'Downforce is proportional to air density — add wing '
                        f'to maintain target downforce levels.'),
                condition='low_air_density',
                confidence=0.78,
                priority=1,
            ))

        # 5. Green/low-rubber track
        if c.track_condition == TrackCondition.DRY_GREEN:
            adjustments.append(WeatherAdjustment(
                param='arb_rear',
                display_name='Green Track Balance',
                delta=-1,
                unit='step',
                reason=(f'Low rubber level (track temp {c.track_temp_c:.0f}°C only '
                        f'{c.track_temp_c - c.air_temp_c:.0f}°C above air). '
                        f'Unrubbered surface has lower peak grip — soften rear ARB '
                        f'to avoid snap oversteer on initial laps as the track evolves.'),
                condition=c.track_condition.value,
                confidence=0.75,
                priority=1,
            ))

        return adjustments

    def condition_report(self) -> dict:
        """
        Structured report for UI display and AI prompt injection.
        """
        c = self.c
        psi_corr = self.tire_pressure_corrections()
        avg_corr = sum(psi_corr.values()) / 4

        return {
            'condition':            c.track_condition.value,
            'time_of_day':          c.time_of_day.value,
            'track_temp_c':         c.track_temp_c,
            'air_temp_c':           c.air_temp_c,
            'wind_vel_kmh':         c.wind_vel_ms * 3.6,
            'wind_dir_deg':         c.wind_dir_deg,
            'grip_factor':          round(self.mechanical_grip_factor(), 2),
            'air_density':          round(c.air_density, 4),
            'air_density_ratio':    round(c.air_density_ratio, 3),
            'aero_delta_steps':     self.wing_adjustment_steps(),
            'pressure_correction_avg_psi': round(avg_corr, 2),
            'spring_modifier':      round(self.spring_stiffness_modifier(), 2),
            'arb_modifier':         round(self.arb_stiffness_modifier(), 2),
            'brake_bias_adj':       round(self.brake_bias_adjustment(), 2),
            'camber_adj_deg':       round(self.camber_temperature_modifier(), 2),
            'tod_notes':            self.time_of_day_context(),
            'wind_context':         self.wind_context(),
            'is_wet':               c.is_wet,
            'is_cold':              c.is_cold,
            'is_hot':               c.is_hot,
        }

    def prompt_section(self) -> str:
        """
        Format weather conditions as a section for the AI prompt.
        Used by ai_advisor._build_prompt() and session enrichments.
        """
        r = self.condition_report()
        c = self.c

        lines = [
            '## TRACK & WEATHER CONDITIONS',
            f'  Condition:    {r["condition"].replace("_"," ").title()}',
            f'  Track Temp:   {c.track_temp_c:.1f}°C  (baseline: {STANDARD_TRACK_TEMP_C:.0f}°C, delta: {c.temp_delta_from_baseline:+.1f}°C)',
            f'  Air Temp:     {c.air_temp_c:.1f}°C',
            f'  Time of Day:  {r["time_of_day"].replace("_"," ").title()}',
            f'  Grip Factor:  {r["grip_factor"]:.2f}  (1.0 = optimal dry rubbered)',
            f'  Air Density:  {r["air_density"]:.4f} kg/m³  ({r["air_density_ratio"]:.1%} of standard)',
        ]

        if c.wind_vel_ms > 2.0:
            lines.append(f'  Wind:         {c.wind_vel_ms*3.6:.0f} km/h @ {c.wind_dir_deg:.0f}°')

        if c.is_wet:
            lines.append(f'  Wetness:      Level {c.track_wetness} — {c.track_condition.value.replace("_"," ")}')

        lines.append('')
        lines.append('## WEATHER-DRIVEN SETUP ADJUSTMENTS')
        lines.append(f'  Tire pressures:  {r["pressure_correction_avg_psi"]:+.2f} psi from standard')
        lines.append(f'  Spring modifier: ×{r["spring_modifier"]:.2f}')
        lines.append(f'  ARB modifier:    ×{r["arb_modifier"]:.2f}')

        if abs(r["brake_bias_adj"]) > 0.1:
            lines.append(f'  Brake bias:      {r["brake_bias_adj"]:+.1f}% from base recommendation')
        if abs(r["camber_adj_deg"]) > 0.05:
            lines.append(f'  Camber adj:      {r["camber_adj_deg"]:+.2f}° to all camber recommendations')
        if r["aero_delta_steps"] != 0:
            lines.append(f'  Wing steps:      {r["aero_delta_steps"]:+d} for air density compensation')

        lines.append('')
        for note in r['tod_notes']:
            lines.append(f'  ⏱  {note}')
        if r['wind_context']:
            lines.append(f'  💨  {r["wind_context"]}')

        lines.append('')
        lines.append('CRITICAL: All recommendations below have already been adjusted for these conditions.')
        lines.append('Do not apply additional weather corrections on top of the pre-adjusted values.')

        return '\n'.join(lines)
