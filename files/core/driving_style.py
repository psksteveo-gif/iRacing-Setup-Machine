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
                report.findings.append(
                    f"Full throttle while cornering: {pct:.0f}% of driving time — applying maximum throttle while the wheel is turned significantly. "
                    "This puts the rear tires near their combined grip limit, risking snap oversteer especially in mid-speed corners.")
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
                            description=f"Snap oversteer at {pos*100:.0f}% track position — "
                                        "rear lost grip suddenly and required counter-steer. "
                                        "If recurring at the same position, likely a setup issue (rear ARB too stiff or rear tires overheating). "
                                        "If random positions, more likely driver-induced (throttle or steering input spike).",
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
                f"Coasting (no throttle or brake) {report.coast_time_pct:.1f}% of the time — during coasting the tires are generating neither driving nor braking force, leaving the friction circle almost empty.")
            report.recommendations.append(
                "Reduce dead time between brake release and throttle application. "
                "The ideal transition is a smooth handoff: as you progressively release the brake, simultaneously begin squeezing the throttle — this is the 'overlapping inputs' technique. "
                "In slow corners, a small amount of coasting is normal, but in medium-speed corners it should be near zero. "
                "Use the Telemetry tab to overlay Brake and Throttle traces and look for gaps — every gap is a place to find time.")

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
            f.append(f"Inconsistent brake points (std: {report.brake_point_std:.4f}) — braking at different distances each lap, causing variable corner entry speeds.")
            r.append(
                "Pick a fixed physical reference for every significant brake zone — a marshal's post, advertising board, or track curb edge. "
                "Commit to the same marker every lap, even if you arrive at it slightly too fast or slow. "
                "Brake point consistency is more valuable than the 'optimal' brake point — once it's repeatable, you can move it incrementally. "
                "In the Telemetry tab, overlay 3–4 laps and look at where the Brake trace rises: the scatter you see is your inconsistency zone.")

        if report.throttle_blips > 20:
            f.append(f"Erratic throttle inputs ({report.throttle_blips} spikes detected) — rapid oscillations indicate wheel spin, traction catch/release, or over-correction.")
            r.append(
                "Cause 1 — Wheel spin: reduce TC sensitivity by 1–2 clicks, or apply throttle more progressively out of slow corners (squeeze, don't stab). "
                "Cause 2 — Over-correction: if you're lifting when the car snaps, practice holding a steady partial throttle through the transition. "
                "Cause 3 — Setup: a rear ARB that's too stiff can cause twitchy exit behaviour that triggers these corrections. "
                "Smooth throttle application is almost always faster than aggressive inputs, especially on RWD cars.")

        if report.trail_braking_pct < 10:
            f.append("Minimal trail braking — releasing the brake fully before turn-in, creating a gap between braking and cornering forces.")
            r.append(
                "Trail braking keeps the front tires loaded during corner entry, which improves rotation and allows a later, deeper brake point. "
                "Start by carrying 10–20% brake pressure (not heavy) into the first 10% of the corner while beginning to steer. "
                "The brake should be fully released by the apex. "
                "Caution: trail braking requires a stable rear — if the rear is already oversteering on entry, fix that first before adding trail brake.")
        elif report.trail_braking_pct > 65:
            f.append("Excessive trail braking — carrying too much brake deep into corners, overloading the front tires and risking front lock-up.")
            r.append(
                "Heavy brake pressure deep into a corner can cause front-tire overheating and push the nose wide (heavy-throttle understeer). "
                "Aim to have the brake mostly released by the geometric apex — only a very light feather after that. "
                "If you're trail braking heavily to keep the car rotating, the underlying issue is likely a setup imbalance (rear too stable, front too understeery) — fix the root cause in setup.")

        if report.steering_reversals > 150:
            f.append("High steering reversal rate — frequent direction changes at the wheel, typical of understeer corrections or a nervous car.")
            r.append(
                "Cause 1 — Understeer: if you're adding lock mid-corner to force rotation, the front is pushing. "
                "Check front ARB, tire pressures, and camber. A car that understeers makes drivers 'saw' at the wheel to force it to turn. "
                "Cause 2 — Setup snap/nervous: a rear-happy car causes constant counter-steer corrections. Check rear ARB and rear tire temps. "
                "Cause 3 — Driver: if the car is balanced but reversals are high, practice holding a fixed steering lock through the apex instead of adjusting.")

        if report.oversteer_events > 5:
            f.append(f"{report.oversteer_events} snap oversteer events detected — car stepping out suddenly, requiring corrective counter-steer.")
            r.append(
                "Common causes in order: "
                "(1) Throttle-induced: applying full throttle too early in a slow corner — rear breaks away as torque overcomes rear grip. Delay throttle application and squeeze progressively. "
                "(2) Rear ARB too stiff: a stiff rear ARB reduces rear grip during cornering, especially on bumpy tracks. Soften by one step. "
                "(3) Rear tire overheating: check rear tire temps — if they're above the optimal window, the tires are giving up suddenly. "
                "(4) Mechanical grip: check rear tire pressures — too high reduces the rear contact patch. "
                "If events are concentrated at a specific track position, check the G-G diagram at that point.")

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


def driving_style_to_setup_hints(report: "DriverStyleReport") -> list:
    """
    Translate measured driving-style metrics into concrete, directional setup hints.

    These hints tell the AI setup builder HOW the driver's technique should
    influence setup decisions — not just what the driver does wrong, but what
    setup compensation would help or complement their style.

    Returns a list of strings, each a self-contained actionable hint.
    """
    hints = []

    # ── Braking consistency ────────────────────────────────────────────────
    if report.brake_consistency < 55:
        hints.append(
            "Brake consistency score is low — the car should be set up for FORGIVENESS on entry. "
            "Soften front ARB 1 step and increase front slow-bump damping to make the nose "
            "less sensitive to variable brake pressure; variable brake points will then produce "
            "less varying corner entry speeds."
        )
    elif report.brake_consistency > 85:
        hints.append(
            "Excellent brake consistency — setup can prioritize PEAK PERFORMANCE on entry. "
            "The driver will exploit a sharper, more responsive front end; a stiffer front ARB "
            "and slightly higher brake bias are appropriate because the consistent inputs won't "
            "cause random lock-ups."
        )

    # ── Trail braking ──────────────────────────────────────────────────────
    if report.trail_braking_pct < 12:
        hints.append(
            "Very low trail braking — driver releases brake fully before turning in. "
            "The front must SELF-LOAD through mechanical means: soften front ARB by 1–2 steps "
            "so the car rolls into the corner and naturally loads the outer front tire. "
            "Slightly softer front spring also helps. Avoid high brake bias as the driver "
            "doesn't use it to rotate the car."
        )
    elif 20 <= report.trail_braking_pct <= 55:
        hints.append(
            "Good trail braking technique — setup can support an active front end. "
            "Front ARB can be moderately stiff (the driver loads it via brake input) and "
            "brake bias slightly higher is appropriate because the driver uses it for rotation."
        )
    elif report.trail_braking_pct > 65:
        hints.append(
            "Excessive trail braking — driver carries heavy brake pressure deep into corners. "
            "Soften front slow-rebound damping so the nose doesn't over-rotate under heavy "
            "late-braking; also check front tire temperatures (overheating risk). "
            "Slightly rearward brake bias reduces the snap oversteer risk from heavy trail braking."
        )

    # ── Throttle smoothness ────────────────────────────────────────────────
    if report.throttle_smoothness < 55:
        hints.append(
            "Low throttle smoothness — erratic inputs on exit. "
            "Soften rear ARB by 1 step and increase diff coast ramp to reduce rear sensitivity "
            "to throttle snap. The rear needs to be more forgiving of imprecise applications. "
            "TC sensitivity should be higher than baseline to catch wheelspin."
        )
    elif report.throttle_smoothness > 80:
        hints.append(
            "Smooth throttle application — rear setup can be more aggressive. "
            "Rear ARB can be slightly stiffer and diff power ramp slightly lower (more locking) "
            "because the smooth inputs won't trigger snap oversteer."
        )

    # ── Coast time (dead pedal time) ──────────────────────────────────────
    if report.coast_time_pct > 12:
        hints.append(
            f"High coasting time ({report.coast_time_pct:.0f}%) — driver spends significant time "
            "with no input. Setup should be FORGIVING and STABLE during the transition phase. "
            "A slightly neutral or understeer-biased balance makes the car less reactive during "
            "these input gaps. Softer ARBs front and rear make the car roll into balance "
            "naturally rather than requiring active driver management."
        )
    elif report.coast_time_pct < 4:
        hints.append(
            "Very low coast time — driver maintains active inputs continuously. "
            "Setup can be sharper and more responsive since driver input doesn't drop out."
        )

    # ── Steering smoothness / sawing ──────────────────────────────────────
    if report.steering_reversals > 160:
        hints.append(
            f"High steering reversal rate ({report.steering_reversals}/lap) — driver is "
            "correcting understeer mid-corner. Soften front ARB 1–2 steps to reduce understeer "
            "and let the front follow the intended line without corrections. Also check front "
            "tire pressures — over-inflation reduces front grip and causes this behaviour."
        )

    # ── Oversteer events ───────────────────────────────────────────────────
    if report.oversteer_events > 5:
        hints.append(
            f"{report.oversteer_events} snap oversteer events detected — setup needs MORE REAR "
            "STABILITY. Soften rear ARB by 1 step, add 0.5–1 step of rear wing (if adjustable), "
            "and check rear tire temperatures. If the rear is overheating, the snaps are "
            "tire-driven — more downforce or pressure adjustment helps more than spring changes."
        )

    # ── Understeer events ──────────────────────────────────────────────────
    if report.understeer_events > 8:
        hints.append(
            f"{report.understeer_events} sustained understeer events detected — setup needs MORE "
            "FRONT ROTATION. Soften front ARB 1 step, consider reducing front spring rate by "
            "5–10 N/mm, and check that front tire pressures are not over-inflated (reduces "
            "contact patch). If trail braking is low, this is likely driver + setup combined."
        )

    # ── Full throttle percentage ───────────────────────────────────────────
    if report.full_throttle_pct < 40:
        hints.append(
            f"Low full-throttle time ({report.full_throttle_pct:.0f}%) — driver is not extracting "
            "full power. This may be traction-limited (wheelspin preventing full throttle) or "
            "gearing-limited. If wheelspin: soften diff power ramp and reduce TC intervention "
            "threshold. If gearing: check that top gear reaches rev limiter at end of straights."
        )

    # ── Balance verdict ────────────────────────────────────────────────────
    if 'UNDERSTEER' in report.balance_verdict.upper():
        hints.append(
            "Overall understeer tendency confirmed by balance events. "
            "Setup should systematically move balance rearward: soften front ARB, "
            "stiffen rear ARB by 0.5–1 step, or reduce front wing if applicable."
        )
    elif 'OVERSTEER' in report.balance_verdict.upper():
        hints.append(
            "Overall oversteer tendency confirmed by balance events. "
            "Setup should systematically move balance forward: stiffen front ARB, "
            "soften rear ARB, or add rear wing if applicable."
        )

    return hints
