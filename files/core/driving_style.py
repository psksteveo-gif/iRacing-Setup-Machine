"""
Driving Style Analyzer
Separates driver technique issues from car setup issues using telemetry.
Analyzes: brake points, throttle application, trail braking, oversteer/understeer events,
steering smoothness, corner phases.
"""

import numpy as np
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from core.ibt_parser import TelemetryData


@dataclass
class DriverEvent:
    event_type: str       # 'late_brake', 'early_throttle', 'snap_oversteer', etc.
    lap_dist_pct: float   # where on track (0-1)
    severity: float       # 0-1
    description: str
    is_driver: bool       # True = driver issue, False = car/setup issue


@dataclass
class DriverStyleReport:
    # Scores 0-100 (higher = better)
    brake_consistency: float = 0.0
    throttle_smoothness: float = 0.0
    steering_smoothness: float = 0.0
    trail_braking_score: float = 0.0
    oversteer_management: float = 0.0
    overall_score: float = 0.0

    # Detailed metrics
    avg_brake_point_pct: float = 0.0       # track position where braking starts
    brake_point_std: float = 0.0           # consistency of brake points
    avg_throttle_application_pct: float = 0.0
    throttle_blips: int = 0                # erratic throttle lifts
    steering_reversals: int = 0            # per lap
    trail_braking_pct: float = 0.0        # % of brake zones with trail braking
    oversteer_events: int = 0
    understeer_events: int = 0
    coast_time_pct: float = 0.0            # % of time with no throttle or brake
    full_throttle_pct: float = 0.0         # % of time at full throttle

    events: List[DriverEvent] = field(default_factory=list)
    findings: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)

    # Verdict strings
    balance_verdict: str = ""   # "driver-induced understeer" / "setup oversteer" etc.
    style_profile: str = ""     # e.g. "Aggressive braker, smooth on throttle"


class DrivingStyleAnalyzer:

    # Thresholds
    BRAKE_THRESHOLD = 0.05       # Brake input above this = braking
    HEAVY_BRAKE = 0.5
    THROTTLE_THRESHOLD = 0.05
    FULL_THROTTLE = 0.90
    STEER_THRESHOLD = 0.08       # rad
    LAT_OVERSTEER_G = 0.3        # lateral accel spike indicating snap
    UNDERSTEER_LAT_G = 2.0       # high lat G sustained = front pushing

    def analyze(self, data: TelemetryData) -> DriverStyleReport:
        """Analyze driving technique: braking, throttle, trail-braking, balance events, and style profile."""
        report = DriverStyleReport()

        brake = data.get_channel('Brake')
        throttle = data.get_channel('Throttle')
        steering = data.get_channel('SteeringWheelAngle')
        lat = data.get_channel('LatAccel')
        long = data.get_channel('LongAccel')
        speed = data.get_channel('Speed')
        lap_dist = data.get_channel('LapDistPct')
        gear = data.get_channel('Gear')

        if brake is None or throttle is None:
            return report

        n = len(brake)
        t = np.arange(n) / max(data.tick_rate, 1)

        # ── Brake Analysis ────────────────────────────────────────────
        report.brake_consistency = self._analyze_braking(
            brake, throttle, steering, lap_dist, speed, report, t)

        # ── Throttle Analysis ─────────────────────────────────────────
        report.throttle_smoothness = self._analyze_throttle(
            throttle, steering, lap_dist, speed, report, t)

        # ── Steering Smoothness ───────────────────────────────────────
        if steering is not None:
            report.steering_smoothness = self._analyze_steering(steering, speed, report)
        else:
            report.steering_smoothness = 70.0

        # ── Trail Braking ─────────────────────────────────────────────
        if steering is not None:
            report.trail_braking_score = self._analyze_trail_braking(
                brake, steering, speed, report)

        # ── Oversteer / Understeer Events ─────────────────────────────
        if lat is not None and long is not None:
            self._detect_balance_events(lat, long, steering, brake, lap_dist, report)

        # ── Coast / Dead Time Analysis ────────────────────────────────
        self._analyze_coast(brake, throttle, speed, report)

        # ── Overall Score ─────────────────────────────────────────────
        weights = [0.25, 0.20, 0.15, 0.20, 0.20]
        scores = [
            report.brake_consistency,
            report.throttle_smoothness,
            report.steering_smoothness,
            report.trail_braking_score,
            report.oversteer_management,
        ]
        report.overall_score = float(np.dot(weights, scores))

        self._generate_findings(report)
        self._classify_style(report)

        return report

    def _analyze_braking(self, brake, throttle, steering, lap_dist, speed, report, t) -> float:
        """Find brake zones, measure consistency and technique."""
        # Find brake zone starts (rising edge above threshold)
        braking = brake > self.BRAKE_THRESHOLD
        rising = np.diff(braking.astype(int))
        brake_starts_idx = np.where(rising > 0)[0]

        if len(brake_starts_idx) < 2:
            return 75.0

        # Brake point positions on track
        if lap_dist is not None:
            brake_positions = lap_dist[brake_starts_idx]
        else:
            brake_positions = brake_starts_idx / len(brake)

        # Filter to meaningful brake zones (ignore tiny blips)
        valid = []
        for idx in brake_starts_idx:
            end = min(idx + 30, len(brake) - 1)
            if np.max(brake[idx:end]) > self.HEAVY_BRAKE:
                if lap_dist is not None:
                    valid.append(float(lap_dist[idx]))
                else:
                    valid.append(float(idx / len(brake)))

        if len(valid) < 2:
            return 75.0

        # Cluster brake points by track position
        clusters = self._cluster_positions(valid, threshold=0.03)
        stds = [np.std(c) for c in clusters if len(c) > 1]

        if stds:
            avg_std = np.mean(stds)
            report.brake_point_std = avg_std
            # Lower std = more consistent. std 0.005 = excellent, 0.02 = poor
            consistency = float(np.clip(100 - avg_std * 2500, 30, 98))
        else:
            consistency = 80.0

        report.avg_brake_point_pct = float(np.mean(valid))
        return consistency

    def _analyze_throttle(self, throttle, steering, lap_dist, speed, report, t) -> float:
        """Measure throttle smoothness and early/late application."""
        # Detect erratic throttle (rapid oscillations while cornering)
        dt = np.diff(throttle)
        blips = np.sum((np.abs(dt[1:]) > 0.15) & (np.abs(dt[:-1]) > 0.05))
        report.throttle_blips = int(blips)

        # Smoothness: measure RMS of throttle derivative
        smooth_score = float(np.clip(100 - blips * 3, 40, 98))

        # Detect simultaneous full throttle + heavy steering (overzealous)
        if steering is not None and speed is not None:
            aggressive = (throttle > self.FULL_THROTTLE) & (np.abs(steering) > 0.25) & (speed > 20)
            pct = float(np.mean(aggressive)) * 100
            if pct > 15:
                report.findings.append(f"Aggressive throttle-while-turning: {pct:.0f}% of time — risks snap oversteer.")
                smooth_score -= 10

        return float(np.clip(smooth_score, 30, 98))

    def _analyze_steering(self, steering, speed, report) -> float:
        """Measure steering reversals and smoothness."""
        # Count steering reversals (sign changes) while moving
        if speed is not None:
            moving = speed > 10
            s = steering[moving]
        else:
            s = steering

        if len(s) < 2:
            report.steering_reversals = 0
            return 50.0

        sign_changes = np.sum(np.diff(np.sign(s)) != 0)
        per_lap = sign_changes / max(1, len(s) / (60 * 90))
        report.steering_reversals = int(per_lap)

        # Steering rate smoothness
        ds = np.diff(s)
        rms = float(np.sqrt(np.mean(ds**2)))
        smoothness = float(np.clip(100 - rms * 300, 40, 98))
        return smoothness

    def _analyze_trail_braking(self, brake, steering, speed, report) -> float:
        """Measure how well the driver trail brakes into corners."""
        if speed is None:
            return 60.0

        moving = speed > 20
        heavy_brake = brake > self.HEAVY_BRAKE
        turning = np.abs(steering) > self.STEER_THRESHOLD

        # Trail braking = braking while turning
        trail = heavy_brake & turning & moving
        all_braking = heavy_brake & moving

        total_braking_samples = np.sum(all_braking)
        if total_braking_samples < 10:
            return 60.0

        trail_pct = float(np.sum(trail) / total_braking_samples) * 100
        report.trail_braking_pct = trail_pct

        # 20-50% is ideal (some trail braking but not excessive)
        if trail_pct < 10:
            score = 50.0
        elif trail_pct < 20:
            score = 70.0
        elif trail_pct < 50:
            score = 90.0
        elif trail_pct < 70:
            score = 75.0
        else:
            score = 55.0  # Over-relying on trail braking

        return float(score)

    def _detect_balance_events(self, lat, long, steering, brake, lap_dist, report):
        """Detect snap oversteer and push understeer events from combined channels."""
        oversteer_count = 0
        understeer_count = 0

        if steering is None:
            report.oversteer_management = 70.0
            return

        # Snap oversteer: sudden large lat accel spike with corrective steering counter-steer
        lat_diff = np.diff(lat)
        snap_threshold = 3.0  # m/s^2 per sample — fast lateral change
        snaps = np.where(np.abs(lat_diff) > snap_threshold)[0]

        for idx in snaps:
            if idx + 5 < len(steering):
                # Check for counter-steer (steering reversal shortly after)
                steer_before = steering[max(0, idx-5):idx]
                steer_after = steering[idx:idx+10]
                if len(steer_before) > 0 and len(steer_after) > 0:
                    if np.sign(np.mean(steer_before)) != np.sign(np.mean(steer_after)):
                        oversteer_count += 1
                        pos = float(lap_dist[idx]) if lap_dist is not None else 0.0
                        report.events.append(DriverEvent(
                            event_type='snap_oversteer',
                            lap_dist_pct=pos,
                            severity=min(1.0, float(np.abs(lat_diff[idx])) / 8.0),
                            description=f"Snap oversteer at {pos*100:.0f}% track — likely setup or throttle-induced.",
                            is_driver=False  # often setup issue
                        ))

        # Understeer: high lat G but slow response / brake with turning
        high_lat = np.abs(lat) > self.UNDERSTEER_LAT_G
        braking_turning = (brake > 0.1) & (np.abs(steering) > 0.2)
        us_events = high_lat & braking_turning
        # Group contiguous samples into single events (60 Hz → ~10 samples per event)
        us_transitions = np.diff(us_events.astype(int))
        understeer_count = int(np.sum(us_transitions > 0))

        report.oversteer_events = oversteer_count
        report.understeer_events = understeer_count

        # Score: fewer events = better
        score = float(np.clip(95 - oversteer_count * 8 - understeer_count * 3, 30, 95))
        report.oversteer_management = score

        # Verdict
        if oversteer_count > understeer_count * 2:
            report.balance_verdict = "Setup or driver-induced OVERSTEER — car is rotating too aggressively"
        elif understeer_count > oversteer_count * 2:
            report.balance_verdict = "UNDERSTEER tendency — front tires losing grip before rear"
        else:
            report.balance_verdict = "Balanced — no dominant stability issue detected"

    def _analyze_coast(self, brake, throttle, speed, report: DriverStyleReport):
        """Measure time spent coasting (no throttle, no brake) = wasted grip potential."""
        coast = (throttle < 0.05) & (brake < 0.05)
        full_thr = throttle > self.FULL_THROTTLE

        if speed is not None:
            moving = speed > 10
            coast = coast & moving
            full_thr = full_thr & moving
            total = np.sum(moving)
        else:
            total = len(throttle)

        if total > 0:
            report.coast_time_pct = float(np.sum(coast) / total * 100)
            report.full_throttle_pct = float(np.sum(full_thr) / total * 100)

        if report.coast_time_pct > 8:
            report.findings.append(
                f"Coasting (no throttle or brake) {report.coast_time_pct:.1f}% of the time — grip potential is wasted during these moments.")
            report.recommendations.append(
                "Reduce dead time between brake release and throttle application. "
                "Overlap brake and throttle at corner transitions (trail braking into early throttle).")

    def _cluster_positions(self, positions: list, threshold: float = 0.03) -> list:
        """Group nearby track positions into clusters."""
        if not positions:
            return []
        sorted_pos = sorted(positions)
        clusters = [[sorted_pos[0]]]
        for p in sorted_pos[1:]:
            if abs(p - clusters[-1][-1]) < threshold:
                clusters[-1].append(p)
            else:
                clusters.append([p])
        return clusters

    def _generate_findings(self, report: DriverStyleReport):
        f = report.findings
        r = report.recommendations

        if report.brake_consistency < 60:
            f.append(f"Inconsistent brake points (std: {report.brake_point_std:.4f}) — braking at different points each lap.")
            r.append("Pick a fixed reference marker (marshal post, curb patch) for every brake zone. Consistency beats perfection.")

        if report.throttle_blips > 20:
            f.append(f"Erratic throttle inputs ({report.throttle_blips} spikes detected) — likely wheel spin or over-correction.")
            r.append("Reduce TC sensitivity or be smoother on throttle application. Progressive squeeze out of slow corners.")

        if report.trail_braking_pct < 10:
            f.append("Minimal trail braking — releasing brake fully before turn-in.")
            r.append("Experiment with carrying light brake pressure into corner entry — loads the front and improves turn-in.")
        elif report.trail_braking_pct > 65:
            f.append("Excessive trail braking — carrying too much brake deep into corners, overloading front tires.")
            r.append("Release brake earlier — heavy trail braking with full lock can cause front tire overheating.")

        if report.steering_reversals > 150:
            f.append("High steering reversal rate — sawing at the wheel, which suggests understeer corrections.")
            r.append("If sawing at the wheel mid-corner: likely understeer — check front ARB and tire pressures.")

        if report.oversteer_events > 5:
            f.append(f"{report.oversteer_events} snap oversteer events detected — car stepping out unexpectedly.")
            r.append("Check rear ARB stiffness, rear tire temperatures, and throttle application point in slow corners.")

    def _classify_style(self, report: DriverStyleReport):
        parts = []
        if report.brake_consistency > 80:
            parts.append("Consistent braker")
        elif report.brake_consistency < 55:
            parts.append("Inconsistent braker")

        if report.trail_braking_pct > 35:
            parts.append("aggressive trail braker")
        elif report.trail_braking_pct < 10:
            parts.append("early-braker")

        if report.throttle_smoothness > 80:
            parts.append("smooth on throttle")
        elif report.throttle_smoothness < 55:
            parts.append("rough on throttle")

        report.style_profile = ", ".join(parts) if parts else "Balanced driver style"
