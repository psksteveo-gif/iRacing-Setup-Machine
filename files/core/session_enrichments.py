"""
session_enrichments.py — Session-level data enrichments for Optimal Sector
===========================================================================

Four capabilities that improve setup accuracy and AI brief quality:

1. AmbientTempCorrector  — Adjusts cold pressure targets based on ambient
                           air temperature extracted from the IBT session YAML.
                           Piecewise correction matching real tyre heat-up physics.

2. BrakeLineSplitAnalyzer — Reads actual hydraulic brake line pressures
                             (LFbrakeLinePress etc.) to compute the real
                             front/rear split, not just the dial setting.

3. DownforceTrimAdvisor  — Recommends downforce level from peak speed.

4. AnalysisConfidenceScorer — Scores data quality 0–1 based on lap count,
                               missing channels, and signal integrity. Feeds
                               into the AI brief prompt so low-confidence
                               sessions are flagged rather than overconfidently
                               recommended.

Usage
-----
    from core.session_enrichments import (
        AmbientTempCorrector, BrakeLineSplitAnalyzer,
        DownforceTrimAdvisor, AnalysisConfidenceScorer,
        enrich_session
    )

    enrichments = enrich_session(
        session_info_str=ibt_session_info,
        channels=ibt_channels,
        car_name="Porsche 911 GT3 Cup (992.2)",
        analysis_report=report,
    )
    # enrichments.cold_pressure_corrections  -> {LF: +0.3, RF: +0.3, ...}
    # enrichments.actual_brake_split_pct     -> 56.2 (front %)
    # enrichments.downforce_rec              -> "High — peak speed 142 mph"
    # enrichments.confidence                 -> ConfidenceScore(score=0.82, ...)
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

import numpy as np

logger = logging.getLogger(__name__)

PA_TO_PSI = 1.0 / 6894.757
MS_TO_MPH = 2.23694
G = 9.80665


# ─────────────────────────────────────────────────────────────────────────────
# DATA STRUCTURES
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ConfidenceScore:
    """Data quality confidence score for an analysis session."""
    score: float                        # 0.0–1.0
    flying_laps: int                    # number of representative laps
    missing_channels: List[str] = field(default_factory=list)
    issues: List[str] = field(default_factory=list)
    signal_warnings: List[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        if self.score >= 0.85:
            return "High"
        elif self.score >= 0.60:
            return "Medium"
        elif self.score >= 0.35:
            return "Low"
        else:
            return "Very Low"

    @property
    def brief_note(self) -> str:
        """One-sentence note for inclusion in AI brief prompt."""
        if self.score >= 0.85:
            return f"Analysis confidence: HIGH — {self.flying_laps} clean laps, all key channels present."
        elif self.score >= 0.60:
            parts = []
            if self.flying_laps < 5:
                parts.append(f"only {self.flying_laps} flying laps")
            if self.missing_channels:
                parts.append(f"missing: {', '.join(self.missing_channels[:3])}")
            note = "; ".join(parts) if parts else "moderate data quality"
            return f"Analysis confidence: MEDIUM — {note}. Treat recommendations as directional."
        else:
            parts = []
            if self.flying_laps < 3:
                parts.append(f"only {self.flying_laps} usable laps")
            if self.missing_channels:
                parts.append(f"{len(self.missing_channels)} missing channels")
            note = "; ".join(parts) if parts else "limited data quality"
            return (
                f"Analysis confidence: LOW — {note}. "
                f"Load more laps before acting on these recommendations."
            )


@dataclass
class BrakeLineSplit:
    """Actual hydraulic brake line pressure split."""
    actual_front_pct: Optional[float]   # e.g. 56.2
    dial_setting_pct: Optional[float]   # from dcBrakeBias channel
    discrepancy_pct: Optional[float]    # actual - dial (positive = front heavier than dial)
    peak_pressure_psi: Optional[float]
    brake_events: int = 0
    avg_peak_pct: Optional[float] = None
    consistency_pct: Optional[float] = None  # StdDev of brake peaks

    @property
    def has_data(self) -> bool:
        return self.actual_front_pct is not None

    @property
    def recommendation(self) -> str:
        if not self.has_data:
            return ""
        if self.discrepancy_pct is not None and abs(self.discrepancy_pct) > 2.0:
            direction = "front-heavy" if self.discrepancy_pct > 0 else "rear-heavy"
            return (
                f"Actual brake split ({self.actual_front_pct:.1f}% front) is "
                f"{abs(self.discrepancy_pct):.1f}% {direction} vs dial "
                f"setting ({self.dial_setting_pct:.1f}%). "
                f"Brake bias dial may need recalibration or there is brake "
                f"system flex."
            )
        return ""


@dataclass
class DownforceTrim:
    """Downforce level recommendation from peak speed."""
    trim: str                   # "High" | "Medium" | "Low / Minimum"
    peak_speed_mph: float
    note: str


@dataclass
class SessionEnrichments:
    """All enrichments for a single session."""
    # Ambient temperature
    ambient_temp_f: Optional[float] = None
    track_temp_f: Optional[float] = None
    cold_pressure_corrections: Dict[str, float] = field(default_factory=dict)
    # {corner: delta_psi} — add this to target_hot_psi to get corrected cold target

    # Brake
    brake: Optional[BrakeLineSplit] = None

    # Downforce
    downforce: Optional[DownforceTrim] = None

    # Confidence
    confidence: Optional[ConfidenceScore] = None


# ─────────────────────────────────────────────────────────────────────────────
# 1. AMBIENT TEMPERATURE PRESSURE CORRECTOR
# ─────────────────────────────────────────────────────────────────────────────

class AmbientTempCorrector:
    """
    Computes cold pressure correction based on ambient air temperature.

    Physics basis: tyre heat-up rate (and therefore cold→hot pressure rise)
    varies with ambient temperature. Cold air suppresses heat build-up,
    meaning you need a lower cold pressure to reach the same hot target.
    Warm air accelerates heat-up, requiring higher cold pressure.

    Reference baseline: 70°F (21°C) — no correction needed.
    """

    # Correction rates (psi per 10°F deviation from 70°F baseline)
    _RATE_COLD  = 0.45   # < 40°F — cold air has bigger swing
    _RATE_MID   = 0.35   # 40–70°F — standard
    _RATE_WARM  = 0.25   # > 70°F — warm air, smaller swing

    @classmethod
    def extract_ambient_from_session(cls, session_info: str) -> tuple:
        """
        Parse AirTemp and TrackTemp from IBT session YAML string.
        Returns (ambient_f, track_f) — either may be None.
        """
        ambient_f = None
        track_f = None

        if not session_info:
            return ambient_f, track_f

        m = re.search(r'AirTemp:\s*([\d.]+)\s*C', session_info)
        if m:
            ambient_f = round(float(m.group(1)) * 9.0 / 5.0 + 32.0, 1)

        m = re.search(r'TrackTemp:\s*([\d.]+)\s*C', session_info)
        if m:
            track_f = round(float(m.group(1)) * 9.0 / 5.0 + 32.0, 1)

        return ambient_f, track_f

    @classmethod
    def from_session_info_dict(cls, session_info: dict) -> tuple:
        """
        Extract ambient and track temp directly from a parsed session_info dict
        (as produced by IBTParser._parse_session_yaml).
        Returns (ambient_f, track_f) — either may be None.
        Faster and more reliable than YAML string parsing.
        """
        ambient_f = None
        track_f = None
        at_c = session_info.get('air_temp_c')
        tt_c = session_info.get('track_temp_c')
        if at_c is not None:
            try:
                ambient_f = round(float(at_c) * 9.0 / 5.0 + 32.0, 1)
            except (TypeError, ValueError):
                pass
        if tt_c is not None:
            try:
                track_f = round(float(tt_c) * 9.0 / 5.0 + 32.0, 1)
            except (TypeError, ValueError):
                pass
        return ambient_f, track_f

    @classmethod
    def compute_correction(cls, ambient_f: float) -> float:
        """
        Return the cold pressure correction delta (psi) for a given
        ambient temperature.

        Positive = increase cold pressure (hot day, car runs hotter).
        Negative = decrease cold pressure (cold day, car runs cooler).
        """
        try:
            tf = float(ambient_f)
        except (TypeError, ValueError):
            return 0.0

        if tf < 40.0:
            # Piecewise: correction for 40→70 band + extra for <40 band
            correction = -(40.0 - 70.0) / 10.0 * cls._RATE_MID
            correction += -(tf - 40.0) / 10.0 * cls._RATE_COLD
        elif tf > 70.0:
            correction = -(tf - 70.0) / 10.0 * cls._RATE_WARM
        else:
            correction = -(tf - 70.0) / 10.0 * cls._RATE_MID

        return round(correction, 2)

    @classmethod
    def per_corner_corrections(
        cls,
        ambient_f: float,
        corners: tuple = ('LF', 'RF', 'LR', 'RR'),
    ) -> Dict[str, float]:
        """
        Return {corner: correction_delta_psi} for all four corners.
        All corners receive the same ambient correction — individual
        corner deltas come from the hot pressure analysis, not ambient.
        """
        delta = cls.compute_correction(ambient_f)
        return {c: delta for c in corners}

    @classmethod
    def corrected_cold_targets(
        cls,
        target_hot_psi: Dict[str, float],
        ambient_f: float,
        hot_to_cold_ratio: float = 0.6,
    ) -> Dict[str, float]:
        """
        Given target hot pressures and ambient temp, compute the cold
        pressures needed to reach those hot targets.

        hot_to_cold_ratio: fraction of hot→cold pressure drop that maps
        to cold pressure adjustment (empirically ~0.6 for most GT tyres).
        """
        ambient_correction = cls.compute_correction(ambient_f)
        result = {}
        for corner, hot_target in target_hot_psi.items():
            # Standard cold target assumes ~4 psi rise from cold to hot
            standard_cold = hot_target - 4.0
            # Apply ambient correction
            corrected = standard_cold + ambient_correction * hot_to_cold_ratio
            result[corner] = round(corrected, 1)
        return result


# ─────────────────────────────────────────────────────────────────────────────
# 2. BRAKE LINE SPLIT ANALYZER
# ─────────────────────────────────────────────────────────────────────────────

class BrakeLineSplitAnalyzer:
    """
    Reads actual hydraulic brake line pressures from IBT channels to compute
    the real front/rear brake split, separate from the driver's dial setting.

    Channels used:
        LFbrakeLinePress, RFbrakeLinePress (front axle)
        LRbrakeLinePress, RRbrakeLinePress (rear axle)
        dcBrakeBias or BrakeBias (dial setting, 0–1 where 1 = 100% front)
        Brake (pedal position 0–1)
    """

    @classmethod
    def analyze(cls, channels: Dict, mask: np.ndarray) -> BrakeLineSplit:
        """
        Compute brake line split from IBT channel data.

        Parameters
        ----------
        channels : dict of channel arrays (from IBT parser)
        mask     : boolean array — True on flying lap samples
        """
        def _ch(name):
            return channels.get(name)

        brake_ch = _ch('Brake')

        # ── Dial setting ───────────────────────────────────────────────
        dial_pct = None
        for bias_name in ('dcBrakeBias', 'BrakeBias'):
            bias_ch = _ch(bias_name)
            if bias_ch is not None:
                bias_m = bias_ch[mask]
                if brake_ch is not None:
                    brk_m = brake_ch[mask]
                    heavy = brk_m > 0.3
                    if heavy.sum() > 50:
                        dial_pct = round(float(np.mean(bias_m[heavy])) * 100, 1)
                        break
                dial_pct = round(float(np.mean(bias_m)) * 100, 1)
                break

        # ── Actual line pressures ──────────────────────────────────────
        lf_bp = _ch('LFbrakeLinePress')
        rf_bp = _ch('RFbrakeLinePress')
        lr_bp = _ch('LRbrakeLinePress')
        rr_bp = _ch('RRbrakeLinePress')

        actual_front_pct = None
        peak_psi = None
        discrepancy = None

        if lf_bp is not None and lr_bp is not None:
            lf_m = lf_bp[mask]
            rf_m = rf_bp[mask] if rf_bp is not None else lf_m
            lr_m = lr_bp[mask]
            rr_m = rr_bp[mask] if rr_bp is not None else lr_m

            f_press = lf_m + rf_m
            r_press = lr_m + rr_m
            tot = f_press + r_press
            mx = float(np.max(tot))

            heavy = (tot > mx * 0.25) if mx > 0 else np.zeros(len(tot), dtype=bool)
            if heavy.sum() > 100:
                actual_front_pct = round(
                    float(np.mean(f_press[heavy] / (tot[heavy] + 1e-9))) * 100, 1
                )
                peak_psi = round(mx * PA_TO_PSI, 1)

                if dial_pct is not None:
                    discrepancy = round(actual_front_pct - dial_pct, 1)

        # ── Brake event consistency ────────────────────────────────────
        brake_events = 0
        avg_peak = None
        consistency = None

        if brake_ch is not None:
            brk_m = brake_ch[mask]
            in_zone = brk_m > 0.5
            entries = np.where(np.diff(in_zone.astype(np.int8)) > 0)[0]
            peaks = []
            for idx in entries:
                end = min(idx + 300, len(brk_m))
                zone = brk_m[idx:end]
                stop = np.where(zone < 0.15)[0]
                if len(stop):
                    zone = zone[:stop[0]]
                if len(zone) >= 5:
                    peaks.append(float(np.max(zone)))
            if len(peaks) >= 3:
                brake_events = len(peaks)
                avg_peak = round(float(np.mean(peaks)) * 100, 1)
                consistency = round(float(np.std(peaks)) * 100, 1)

        return BrakeLineSplit(
            actual_front_pct=actual_front_pct,
            dial_setting_pct=dial_pct,
            discrepancy_pct=discrepancy,
            peak_pressure_psi=peak_psi,
            brake_events=brake_events,
            avg_peak_pct=avg_peak,
            consistency_pct=consistency,
        )


# ─────────────────────────────────────────────────────────────────────────────
# 3. DOWNFORCE TRIM ADVISOR
# ─────────────────────────────────────────────────────────────────────────────

class DownforceTrimAdvisor:
    """
    Recommends downforce trim level based on peak speed.
    Simple but genuinely useful — drivers frequently ask this question.
    """

    @classmethod
    def advise(cls, channels: Dict, mask: np.ndarray) -> Optional[DownforceTrim]:
        speed_ch = channels.get('Speed')
        if speed_ch is None or mask.sum() == 0:
            return None

        peak_mph = float(np.max(speed_ch[mask])) * MS_TO_MPH

        if peak_mph < 155:
            trim = "High"
            note = (
                f"Peak speed {peak_mph:.0f} mph — below 155 mph favours maximum "
                f"downforce for peak cornering speed. Prioritise front wing angle "
                f"and rear wing setting toward their maximums."
            )
        elif peak_mph < 167:
            trim = "Medium"
            note = (
                f"Peak speed {peak_mph:.0f} mph — 155–167 mph range suits medium "
                f"downforce, balancing drag vs cornering grip. Start from mid-range "
                f"wing settings and adjust based on sector times."
            )
        else:
            trim = "Low / Minimum"
            note = (
                f"Peak speed {peak_mph:.0f} mph — above 167 mph suggests low or "
                f"minimum downforce to reduce straight-line drag. Monitor high-speed "
                f"corner stability carefully with reduced wing settings."
            )

        return DownforceTrim(trim=trim, peak_speed_mph=round(peak_mph, 1), note=note)


# ─────────────────────────────────────────────────────────────────────────────
# 4. ANALYSIS CONFIDENCE SCORER
# ─────────────────────────────────────────────────────────────────────────────

class AnalysisConfidenceScorer:
    """
    Scores analysis confidence 0–1 based on:
    - Number of flying laps
    - Missing key channels
    - Signal integrity warnings
    - Ambient temperature availability

    Score feeds directly into build_brief_prompt() so the AI brief
    is calibrated to data quality.
    """

    # Channels required for full analysis confidence
    REQUIRED_CHANNELS = [
        'Speed', 'Throttle', 'Brake', 'Lap', 'LapDistPct',
        'LFtempCL', 'RFtempCL', 'LRtempCL', 'RRtempCL',
        'LFpressure', 'RFpressure', 'LRpressure', 'RRpressure',
        'LatAccel', 'LongAccel', 'SteeringWheelAngle',
    ]

    @classmethod
    def score(
        cls,
        channels: Dict,
        flying_laps: int,
        ambient_temp_available: bool = False,
    ) -> ConfidenceScore:

        missing = [c for c in cls.REQUIRED_CHANNELS if channels.get(c) is None]
        signal_warnings = cls._check_signal_integrity(channels)
        issues = []

        # Penalty: missing channels (max 50% penalty)
        channel_penalty = (len(missing) / len(cls.REQUIRED_CHANNELS)) * 0.50

        # Penalty: low lap count (max 30% penalty, scaled 0–5 laps)
        lap_penalty = max(0.0, (5 - flying_laps) / 5.0) * 0.30

        # Penalty: signal integrity warnings (5% each, max 15%)
        signal_penalty = min(0.15, len(signal_warnings) * 0.05)

        # Penalty: no ambient temp (5%)
        ambient_penalty = 0.05 if not ambient_temp_available else 0.0

        score = max(0.0, round(
            1.0 - channel_penalty - lap_penalty - signal_penalty - ambient_penalty,
            2
        ))

        # Build human-readable issues list
        if missing:
            issues.append(f"Missing channels: {', '.join(missing)}")
        if flying_laps < 3:
            issues.append(
                f"Only {flying_laps} flying lap(s) — "
                f"minimum 3 recommended for reliable recommendations"
            )
        if not ambient_temp_available:
            issues.append(
                "No ambient temperature in session data — "
                "cold pressure targets use uncorrected baseline"
            )

        return ConfidenceScore(
            score=score,
            flying_laps=flying_laps,
            missing_channels=missing,
            issues=issues,
            signal_warnings=signal_warnings,
        )

    @classmethod
    def _check_signal_integrity(cls, channels: Dict) -> List[str]:
        warnings = []

        speed = channels.get('Speed')
        if speed is not None and float(np.max(speed)) * MS_TO_MPH > 280:
            warnings.append('Speed >280 mph — possible data corruption')

        lat = channels.get('LatAccel')
        if lat is not None and float(np.max(np.abs(lat))) > 78.5:
            warnings.append('LatAccel >8G — possible data corruption')

        thr = channels.get('Throttle')
        if thr is not None and float(np.max(thr)) > 1.05:
            warnings.append('Throttle channel values outside 0–1 range')

        brk = channels.get('Brake')
        if brk is not None and float(np.max(brk)) > 1.05:
            warnings.append('Brake channel values outside 0–1 range')

        return warnings


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC API — single entry point
# ─────────────────────────────────────────────────────────────────────────────

def enrich_session(
    session_info_str = "",   # str (YAML) or dict (parsed session_info)
    channels: Dict = None,
    car_name: str = "",
    flying_laps: int = 0,
    mask: Optional[np.ndarray] = None,
) -> SessionEnrichments:
    """
    Run all enrichments for a session.

    Parameters
    ----------
    session_info_str : str — raw IBT session YAML string
    channels         : dict — IBT channel arrays
    car_name         : str — used for per-car pressure targets
    flying_laps      : int — number of representative laps
    mask             : np.ndarray — flying lap boolean mask (optional)

    Returns
    -------
    SessionEnrichments with all fields populated where data is available.
    """
    channels = channels or {}
    enrichments = SessionEnrichments()

    # ── 1. Ambient temperature ────────────────────────────────────────────
    # Accept session_info as dict (from IBTParser) or YAML string (legacy)
    ambient_f, track_f = None, None
    if isinstance(session_info_str, dict):
        ambient_f, track_f = AmbientTempCorrector.from_session_info_dict(
            session_info_str)
    else:
        ambient_f, track_f = AmbientTempCorrector.extract_ambient_from_session(
            session_info_str
        )
    enrichments.ambient_temp_f = ambient_f
    enrichments.track_temp_f = track_f

    if ambient_f is not None:
        enrichments.cold_pressure_corrections = (
            AmbientTempCorrector.per_corner_corrections(ambient_f)
        )
        logger.info(
            "session_enrichments: ambient=%.1f°F, correction=%.2f psi/corner",
            ambient_f,
            list(enrichments.cold_pressure_corrections.values())[0]
            if enrichments.cold_pressure_corrections else 0.0
        )

    # ── 2. Brake line split ───────────────────────────────────────────────
    if mask is not None and len(channels) > 0:
        try:
            enrichments.brake = BrakeLineSplitAnalyzer.analyze(channels, mask)
        except Exception as e:
            logger.warning("session_enrichments: brake analysis failed: %s", e)

    # ── 3. Downforce trim ─────────────────────────────────────────────────
    if mask is not None and channels.get('Speed') is not None:
        try:
            enrichments.downforce = DownforceTrimAdvisor.advise(channels, mask)
        except Exception as e:
            logger.warning("session_enrichments: downforce advise failed: %s", e)

    # ── 4. Confidence score ───────────────────────────────────────────────
    try:
        enrichments.confidence = AnalysisConfidenceScorer.score(
            channels=channels,
            flying_laps=flying_laps,
            ambient_temp_available=(ambient_f is not None),
        )
    except Exception as e:
        logger.warning("session_enrichments: confidence score failed: %s", e)

    return enrichments


def apply_ambient_correction_to_bundle(bundle, enrichments: SessionEnrichments):
    """
    Apply ambient temperature pressure corrections to a SignalBundle's
    tire pressure hot values, adjusting the target window accordingly.

    Call this BEFORE SetupDeltaEngine.compute_deltas() for best results.
    """
    if not enrichments.cold_pressure_corrections:
        return

    if not hasattr(bundle, 'ambient_correction_applied'):
        bundle.ambient_correction_applied = False

    if bundle.ambient_correction_applied:
        return

    correction = list(enrichments.cold_pressure_corrections.values())[0]

    # Store correction on bundle for use in pressure rules
    bundle.ambient_temp_correction_psi = correction
    bundle.ambient_temp_f = enrichments.ambient_temp_f
    bundle.ambient_correction_applied = True

    logger.info(
        "session_enrichments: applied %.2f psi ambient correction to bundle "
        "(ambient=%.1f°F)",
        correction, enrichments.ambient_temp_f or 0.0
    )
