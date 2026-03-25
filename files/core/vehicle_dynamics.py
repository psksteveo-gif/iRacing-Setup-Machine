"""
Vehicle Dynamics Analyzer
==========================
Analyzes roll/pitch dynamics, in-session driver aid adjustments,
shift point efficiency, and wheel slip ratios from iRacing telemetry.
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from core.ibt_parser import TelemetryData

CORNERS = ['LF', 'RF', 'LR', 'RR']
MIN_SAMPLES = 300


# ══════════════════════════════════════════════════════════════════════════════
# ROLL / PITCH
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class DynamicsReport:
    has_attitude_data: bool = False
    max_roll_deg:  float = 0.0
    max_pitch_deg: float = 0.0
    avg_roll_deg:  float = 0.0
    avg_pitch_deg: float = 0.0
    # Per-lap peak values
    lap_max_roll:  List[float] = field(default_factory=list)
    lap_max_pitch: List[float] = field(default_factory=list)
    # Attitude summary text
    roll_summary:  str = ""
    pitch_summary: str = ""


def analyze_dynamics(data: TelemetryData) -> DynamicsReport:
    report = DynamicsReport()

    pitch_ch = data.get_channel('Pitch')
    roll_ch  = data.get_channel('Roll')

    if pitch_ch is not None and len(pitch_ch) >= MIN_SAMPLES:
        pitch = np.degrees(pitch_ch.astype(float))
        roll  = np.degrees(roll_ch.astype(float)) if roll_ch is not None else None

        report.has_attitude_data = True
        report.max_pitch_deg = float(np.max(np.abs(pitch)))
        report.avg_pitch_deg = float(np.mean(np.abs(pitch)))

        if roll is not None:
            report.max_roll_deg = float(np.max(np.abs(roll)))
            report.avg_roll_deg = float(np.mean(np.abs(roll)))

        # Per-lap
        if data.lap_boundaries:
            for i in range(data.num_laps):
                b0 = data.lap_boundaries[i]
                b1 = data.lap_boundaries[i + 1] if i + 1 < len(data.lap_boundaries) else len(pitch)
                p_seg = np.abs(pitch[b0:b1])
                report.lap_max_pitch.append(float(np.max(p_seg)) if len(p_seg) > 0 else 0.0)
                if roll is not None:
                    r_seg = np.abs(roll[b0:b1])
                    report.lap_max_roll.append(float(np.max(r_seg)) if len(r_seg) > 0 else 0.0)

        # Summaries
        if report.max_roll_deg > 5.0:
            report.roll_summary = f"High body roll: {report.max_roll_deg:.1f}° peak — consider stiffer ARBs"
        elif report.max_roll_deg > 2.5:
            report.roll_summary = f"Moderate roll: {report.max_roll_deg:.1f}° peak"
        else:
            report.roll_summary = f"Low roll: {report.max_roll_deg:.1f}° peak — stiff setup"

        if report.max_pitch_deg > 4.0:
            report.pitch_summary = f"Significant pitch: {report.max_pitch_deg:.1f}° peak — check spring rates"
        else:
            report.pitch_summary = f"Pitch: {report.max_pitch_deg:.1f}° peak"

    return report


# ══════════════════════════════════════════════════════════════════════════════
# DRIVER AID ADJUSTMENT TRACKER
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class AidAdjustment:
    aid: str         # 'BrakeBias', 'TC', 'ABS'
    lap: int
    session_time_s: float
    lap_dist_pct: float
    old_value: float
    new_value: float
    delta: float


@dataclass
class AidTrackingReport:
    has_data: bool = False
    adjustments: List[AidAdjustment] = field(default_factory=list)
    # Ranges seen
    brake_bias_range: Tuple[float, float] = (0.0, 0.0)
    tc_range:         Tuple[float, float] = (0.0, 0.0)
    abs_range:        Tuple[float, float] = (0.0, 0.0)
    summary: str = ""


def analyze_aid_adjustments(data: TelemetryData) -> AidTrackingReport:
    report = AidTrackingReport()
    channels = {
        'BrakeBias': data.get_channel('dcBrakeBias'),
        'TC':        data.get_channel('dcTractionControl'),
        'ABS':       data.get_channel('dcABS'),
    }

    session_time = data.get_channel('SessionTime')
    lap_dist     = data.get_channel('LapDistPct')
    boundaries   = data.lap_boundaries

    _DEAD = 0.001   # ignore changes smaller than this

    for aid_name, ch in channels.items():
        if ch is None or len(ch) < MIN_SAMPLES:
            continue
        report.has_data = True
        arr = ch.astype(float)

        # Smooth slightly to suppress noise (3-frame median filter equivalent)
        diffs = np.diff(arr)
        change_mask = np.abs(diffs) > _DEAD
        change_indices = np.where(change_mask)[0]

        # Debounce: one event per 30 frames minimum
        prev_idx = -100
        for idx in change_indices:
            if idx - prev_idx < 30:
                continue
            prev_idx = idx
            old_v = float(arr[idx])
            new_v = float(arr[idx + 1])
            if abs(new_v - old_v) < _DEAD:
                continue
            lap_idx = _find_lap_idx(int(idx), boundaries) if boundaries else 0
            t = float(session_time[idx]) if session_time is not None else 0.0
            d = float(lap_dist[idx]) if lap_dist is not None else 0.0
            report.adjustments.append(AidAdjustment(
                aid=aid_name, lap=lap_idx + 1,
                session_time_s=round(t, 1),
                lap_dist_pct=round(d, 3),
                old_value=round(old_v, 3),
                new_value=round(new_v, 3),
                delta=round(new_v - old_v, 3),
            ))

        # Range
        mn, mx = float(np.min(arr)), float(np.max(arr))
        if aid_name == 'BrakeBias':
            report.brake_bias_range = (round(mn, 3), round(mx, 3))
        elif aid_name == 'TC':
            report.tc_range = (round(mn, 1), round(mx, 1))
        elif aid_name == 'ABS':
            report.abs_range = (round(mn, 1), round(mx, 1))

    if report.adjustments:
        n = len(report.adjustments)
        aids_used = sorted({a.aid for a in report.adjustments})
        report.summary = f"{n} adjustment{'s' if n != 1 else ''} — {', '.join(aids_used)}"
    elif report.has_data:
        report.summary = "No in-session adjustments detected"

    report.adjustments.sort(key=lambda a: a.session_time_s)
    return report


# ══════════════════════════════════════════════════════════════════════════════
# SHIFT POINT OPTIMIZER
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class ShiftAnalysis:
    has_data: bool = False
    shift_count: int = 0
    optimal_shift_rpm: float = 0.0     # estimated peak-power RPM
    avg_shift_rpm: float = 0.0
    early_shift_count: int = 0         # shifted below optimal - 200 RPM
    late_shift_count: int = 0          # shifted above optimal + 300 RPM
    missed_apex_shifts: int = 0        # downshifts inside corners
    avg_early_delta_rpm: float = 0.0
    avg_late_delta_rpm: float = 0.0
    summary: str = ""


def analyze_shifts(data: TelemetryData) -> ShiftAnalysis:
    result = ShiftAnalysis()

    rpm_ch  = data.get_channel('RPM')
    gear_ch = data.get_channel('Gear')

    if rpm_ch is None or gear_ch is None or len(rpm_ch) < MIN_SAMPLES:
        return result

    rpm  = rpm_ch.astype(float)
    gear = gear_ch.astype(float)

    # Upshift events: gear increases
    gear_diff = np.diff(gear)
    upshift_idx = np.where(gear_diff > 0.5)[0]
    if len(upshift_idx) == 0:
        return result

    result.has_data = True
    result.shift_count = len(upshift_idx)

    # RPM at each upshift (take sample just before shift)
    shift_rpms = rpm[upshift_idx]
    shift_rpms = shift_rpms[shift_rpms > 2000]  # filter idle/reset noise

    if len(shift_rpms) == 0:
        return result

    result.avg_shift_rpm = float(np.mean(shift_rpms))

    # Estimate optimal shift RPM: 95th percentile of actual shifts
    # (drivers who shift at the right time will cluster near the power peak)
    result.optimal_shift_rpm = float(np.percentile(shift_rpms, 85))

    early_threshold = result.optimal_shift_rpm - 300
    late_threshold  = result.optimal_shift_rpm + 400

    early_deltas = []
    late_deltas  = []
    for sr in shift_rpms:
        if sr < early_threshold:
            result.early_shift_count += 1
            early_deltas.append(result.optimal_shift_rpm - sr)
        elif sr > late_threshold:
            result.late_shift_count += 1
            late_deltas.append(sr - result.optimal_shift_rpm)

    if early_deltas:
        result.avg_early_delta_rpm = float(np.mean(early_deltas))
    if late_deltas:
        result.avg_late_delta_rpm = float(np.mean(late_deltas))

    total_issues = result.early_shift_count + result.late_shift_count
    pct_clean = 100 * (result.shift_count - total_issues) / max(result.shift_count, 1)
    result.summary = (
        f"{result.shift_count} upshifts — "
        f"{pct_clean:.0f}% on-target  "
        f"({result.early_shift_count} early, {result.late_shift_count} late)  "
        f"target ≈ {result.optimal_shift_rpm:,.0f} RPM"
    )
    return result


# ══════════════════════════════════════════════════════════════════════════════
# WHEEL SLIP RATIOS
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class WheelSlipReport:
    has_data: bool = False
    # Fraction of time each corner had significant slip
    lf_slip_fraction: float = 0.0
    rf_slip_fraction: float = 0.0
    lr_slip_fraction: float = 0.0
    rr_slip_fraction: float = 0.0
    # Peak slip ratios observed
    lf_peak_slip: float = 0.0
    rf_peak_slip: float = 0.0
    lr_peak_slip: float = 0.0
    rr_peak_slip: float = 0.0
    # Lockup vs wheelspin breakdown
    lockup_fraction:   float = 0.0   # wheel slower than body speed
    wheelspin_fraction: float = 0.0  # wheel faster than body speed
    summary: str = ""


_SLIP_THRESHOLD = 0.07   # 7% slip ratio = significant


def analyze_wheel_slip(data: TelemetryData) -> WheelSlipReport:
    report = WheelSlipReport()

    speed_ch = data.get_channel('Speed')  # body speed in m/s
    if speed_ch is None or len(speed_ch) < MIN_SAMPLES:
        return report

    speed = speed_ch.astype(float)
    # Only analyse above 5 m/s (~18 kph) to avoid standing-start noise
    moving = speed > 5.0

    slip_fractions = {}
    peak_slips     = {}

    for corner, ch_name in [('LF', 'LFspeed'), ('RF', 'RFspeed'),
                             ('LR', 'LRspeed'), ('RR', 'RRspeed')]:
        ch = data.get_channel(ch_name)
        if ch is None or len(ch) < MIN_SAMPLES:
            continue
        report.has_data = True
        wheel_spd = ch.astype(float)

        # Slip ratio = (wheel_speed - body_speed) / body_speed
        safe_speed = np.where(moving & (speed > 0.1), speed, np.nan)
        slip_ratio = np.where(moving, (wheel_spd - speed) / np.where(speed > 0.1, speed, 1.0), 0.0)

        significant = np.abs(slip_ratio) > _SLIP_THRESHOLD
        slip_fractions[corner] = float(np.sum(significant & moving) / max(np.sum(moving), 1))
        peak_slips[corner]     = float(np.nanmax(np.abs(np.where(moving, slip_ratio, np.nan))))

    if not report.has_data:
        return report

    report.lf_slip_fraction = slip_fractions.get('LF', 0.0)
    report.rf_slip_fraction = slip_fractions.get('RF', 0.0)
    report.lr_slip_fraction = slip_fractions.get('LR', 0.0)
    report.rr_slip_fraction = slip_fractions.get('RR', 0.0)
    report.lf_peak_slip = peak_slips.get('LF', 0.0)
    report.rf_peak_slip = peak_slips.get('RF', 0.0)
    report.lr_peak_slip = peak_slips.get('LR', 0.0)
    report.rr_peak_slip = peak_slips.get('RR', 0.0)

    # Lockup vs spin: use all rear/front averages
    all_speeds = {c: data.get_channel(f'{c}speed') for c in ['LF', 'RF', 'LR', 'RR']}
    lockup_count = 0; spin_count = 0; n_valid = 0
    for ch in all_speeds.values():
        if ch is None or len(ch) < MIN_SAMPLES:
            continue
        wheel_spd = ch.astype(float)
        sr = np.where(moving, (wheel_spd - speed) / np.where(speed > 0.1, speed, 1.0), 0.0)
        lockup_count += int(np.sum((sr < -_SLIP_THRESHOLD) & moving))
        spin_count   += int(np.sum((sr >  _SLIP_THRESHOLD) & moving))
        n_valid += int(np.sum(moving))

    if n_valid > 0:
        report.lockup_fraction    = lockup_count / n_valid
        report.wheelspin_fraction = spin_count   / n_valid

    worst = max(slip_fractions, key=slip_fractions.get) if slip_fractions else ''
    pct_lock = report.lockup_fraction * 100
    pct_spin = report.wheelspin_fraction * 100
    report.summary = (
        f"Lockup: {pct_lock:.1f}%  Wheelspin: {pct_spin:.1f}%  "
        f"Worst corner: {worst} ({slip_fractions.get(worst, 0)*100:.1f}% slip time)"
        if worst else "No wheel speed data"
    )
    return report


# ══════════════════════════════════════════════════════════════════════════════
# KERB / OFF-TRACK DETECTOR
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class OffTrackEvent:
    lap: int
    lap_dist_pct: float
    event_type: str      # 'kerb', 'off_track', 'pit_entry'
    duration_s: float
    vert_accel_g: float  # peak vertical G


@dataclass
class KerbReport:
    has_data: bool = False
    events: List[OffTrackEvent] = field(default_factory=list)
    kerb_count: int = 0
    off_track_count: int = 0
    total_off_track_s: float = 0.0
    summary: str = ""


# PlayerTrackSurface values
SURFACE_NOT_IN_WORLD = 0
SURFACE_OFF_TRACK    = 1
SURFACE_PIT_LANE     = 2
SURFACE_PIT_STALL    = 3
SURFACE_TRACK        = 5

KERB_VERT_THRESHOLD  = 15.0   # m/s² vertical accel spike = kerb


def analyze_kerbs(data: TelemetryData) -> KerbReport:
    report = KerbReport()

    vert_ch    = data.get_channel('VertAccel')
    surface_ch = data.get_channel('PlayerTrackSurface')
    lap_dist   = data.get_channel('LapDistPct')
    session_time = data.get_channel('SessionTime')
    boundaries   = data.lap_boundaries

    if vert_ch is not None and len(vert_ch) >= MIN_SAMPLES:
        report.has_data = True
        vert = vert_ch.astype(float)

        # Kerb strikes: VertAccel spikes (above threshold in absolute)
        # Subtract the average gravity baseline (~9.8 m/s²) first
        vert_zeroed = vert - np.median(vert)
        kerb_mask = np.abs(vert_zeroed) > KERB_VERT_THRESHOLD
        kerb_idx  = np.where(kerb_mask)[0]
        kerb_events = _debounce_idx(kerb_idx, gap=20)

        for idx in kerb_events[:30]:
            lap_idx = _find_lap_idx(int(idx), boundaries) if boundaries else 0
            report.events.append(OffTrackEvent(
                lap=lap_idx + 1,
                lap_dist_pct=float(lap_dist[idx]) if lap_dist is not None and idx < len(lap_dist) else 0.0,
                event_type='kerb',
                duration_s=0.0,
                vert_accel_g=round(float(abs(vert_zeroed[idx])) / 9.81, 2),
            ))
        report.kerb_count = len(kerb_events)

    if surface_ch is not None and len(surface_ch) >= MIN_SAMPLES:
        report.has_data = True
        surface = surface_ch.astype(int)
        off_mask = surface == SURFACE_OFF_TRACK
        off_idx  = np.where(off_mask)[0]

        if len(off_idx) > 0 and session_time is not None:
            # Find contiguous stretches
            stretches = _find_stretches(off_idx, gap=10)
            for start, end in stretches[:20]:
                dur = float(session_time[min(end, len(session_time)-1)] -
                            session_time[start]) if start < len(session_time) else 0.0
                if dur < 0.1:
                    continue
                lap_idx = _find_lap_idx(int(start), boundaries) if boundaries else 0
                report.events.append(OffTrackEvent(
                    lap=lap_idx + 1,
                    lap_dist_pct=float(lap_dist[start]) if lap_dist is not None else 0.0,
                    event_type='off_track',
                    duration_s=round(dur, 2),
                    vert_accel_g=0.0,
                ))
                report.total_off_track_s += dur
            report.off_track_count = len(stretches)

    if report.kerb_count or report.off_track_count:
        report.summary = (
            f"{report.kerb_count} kerb strike{'s' if report.kerb_count != 1 else ''}  |  "
            f"{report.off_track_count} off-track instance{'s' if report.off_track_count != 1 else ''}  "
            f"({report.total_off_track_s:.1f}s total off-track)"
        )
    elif report.has_data:
        report.summary = "No kerb strikes or off-track events detected"

    report.events.sort(key=lambda e: (e.lap, e.lap_dist_pct))
    return report


def _debounce_idx(indices: np.ndarray, gap: int) -> List[int]:
    if len(indices) == 0:
        return []
    result = [int(indices[0])]
    for i in indices[1:]:
        if int(i) - result[-1] >= gap:
            result.append(int(i))
    return result


def _find_stretches(indices: np.ndarray, gap: int) -> List[Tuple[int, int]]:
    """Convert index array into (start, end) tuples of contiguous runs."""
    if len(indices) == 0:
        return []
    stretches = []
    start = int(indices[0]); prev = int(indices[0])
    for idx in indices[1:]:
        i = int(idx)
        if i - prev > gap:
            stretches.append((start, prev))
            start = i
        prev = i
    stretches.append((start, prev))
    return stretches


def _find_lap_idx(sample_idx: int, boundaries: List[int]) -> int:
    for i in range(len(boundaries) - 1):
        if boundaries[i] <= sample_idx < boundaries[i + 1]:
            return i
    return max(0, len(boundaries) - 2)
