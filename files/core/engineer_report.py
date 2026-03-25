"""
Race Engineer Report — plain-English telemetry analysis.

Generates a prioritised list of EngineerFinding objects written the way
a race engineer would talk to a driver: direct, specific, and actionable.
No charts. No jargon without explanation.
"""
from __future__ import annotations

import logging
import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)

PRIORITY_LABEL = {1: "Must Address", 2: "Important", 3: "Note"}
CATEGORY_LABEL = {
    'pace': 'Pace',
    'technique': 'Technique',
    'consistency': 'Consistency',
    'setup': 'Setup',
    'fuel': 'Fuel',
    'tires': 'Tires',
    'info': 'Info',
}


@dataclass
class EngineerFinding:
    title: str
    body: str                        # 2–5 sentences of plain English
    priority: int                    # 1=must address, 2=important, 3=worth noting
    category: str                    # 'pace','technique','consistency','setup','fuel','tires','info'
    time_gain_s: float = 0.0        # estimated seconds on the table (0 = qualitative)
    corners: List[str] = field(default_factory=list)


# ── Public API ────────────────────────────────────────────────────────────────

def generate_engineer_report(
    data,
    report,
    sector_report=None,
    corner_report=None,
    style_report=None,
    best_report=None,
    torque_report=None,
    fuel_report=None,
    consistency=None,
) -> List[EngineerFinding]:
    """Return findings sorted by priority then estimated time gain."""
    findings: List[EngineerFinding] = []
    try:
        _lap_validity(findings, data, report)
        _minimum_speed_deficit(findings, corner_report, report)
        _brake_point_scatter(findings, corner_report)
        _throttle_application(findings, corner_report, style_report)
        _sector_time_trend(findings, sector_report)
        _balance_zones(findings, torque_report)
        _zone_consistency(findings, data, report)
        _fuel_lap_delta(findings, fuel_report, best_report, report)
        _coast_and_throttle_use(findings, style_report)
        _trail_braking_balance(findings, style_report, report)
    except Exception:
        logger.warning("Engineer report generation failed", exc_info=True)
    return sorted(findings, key=lambda f: (f.priority, -f.time_gain_s))


def findings_as_text(findings: List[EngineerFinding]) -> str:
    """Single-string summary for AI context injection."""
    if not findings:
        return ""
    lines = ["=== Race Engineer Analysis ==="]
    for f in findings:
        gain_str = f"  [~{f.time_gain_s:.2f}s]" if f.time_gain_s >= 0.05 else ""
        lines.append(f"\n[{PRIORITY_LABEL[f.priority]}] {f.title}{gain_str}")
        lines.append(f.body)
    return "\n".join(lines)


# ── Individual finders ────────────────────────────────────────────────────────

def _lap_validity(findings, data, report):
    """Flag incomplete laps that were excluded from analysis."""
    if not data or not report or not report.lap_times:
        return
    valid_mask = getattr(report, 'valid_lap_mask', None)
    if not valid_mask or all(valid_mask):
        return
    best_valid = min(
        (t for t, v in zip(report.lap_times, valid_mask) if v),
        default=report.best_lap
    )
    short_laps = [i + 1 for i, (t, v) in enumerate(zip(report.lap_times, valid_mask))
                  if not v and t < best_valid * 0.65]
    outlier_laps = [i + 1 for i, (t, v) in enumerate(zip(report.lap_times, valid_mask))
                    if not v and t >= best_valid * 0.65]
    clean_count = sum(valid_mask)

    parts = []
    if short_laps:
        parts.append(f"Lap{'s' if len(short_laps) > 1 else ''} "
                     f"{', '.join(map(str, short_laps))} "
                     f"{'were' if len(short_laps) > 1 else 'was'} incomplete "
                     f"(under 65% of your best lap time — likely an in or out lap).")
    if outlier_laps:
        parts.append(f"Lap{'s' if len(outlier_laps) > 1 else ''} "
                     f"{', '.join(map(str, outlier_laps))} "
                     f"{'were flagged' if len(outlier_laps) > 1 else 'was flagged'} "
                     f"as statistical outliers.")
    if not parts:
        return
    body = " ".join(parts)
    body += (f" All sector, corner, and consistency numbers are calculated from "
             f"your {clean_count} clean lap{'s' if clean_count != 1 else ''} only, "
             f"so these numbers are not distorted by the anomalies.")
    findings.append(EngineerFinding(
        title="Data Quality — Incomplete Laps Excluded",
        body=body, priority=3, category='info'
    ))


def _minimum_speed_deficit(findings, corner_report, report):
    """Corners where average apex speed is significantly below best-lap apex speed."""
    if not corner_report or not getattr(corner_report, 'corners', None):
        return

    significant = []
    for cd in corner_report.corners:
        if not cd.lap_min_speeds or len(cd.lap_min_speeds) < 3:
            continue
        best_min = max(cd.lap_min_speeds)
        avg_min = float(np.mean(cd.lap_min_speeds))
        deficit_kph = (best_min - avg_min) * 3.6
        if deficit_kph < 2.5:
            continue
        est_gain = deficit_kph * 0.035   # ~35ms per km/h of apex speed
        name = cd.corner_name or f"Corner {cd.corner_num + 1}"
        significant.append((name, deficit_kph, est_gain, avg_min * 3.6, best_min * 3.6))

    if not significant:
        return
    significant.sort(key=lambda x: -x[1])
    total_est = sum(x[2] for x in significant)

    if len(significant) == 1:
        name, deficit, gain, avg_kph, best_kph = significant[0]
        body = (f"At {name} you're averaging {avg_kph:.0f} km/h through the apex, "
                f"but on your best lap you carried {best_kph:.0f} km/h — a {deficit:.1f} km/h gap. "
                f"Your fastest lap proves you can carry that speed; the question is why "
                f"you can't replicate it every lap. This is almost always a consistency "
                f"issue with brake release timing or steering input rate — smoother and "
                f"more deliberate will beat faster and erratic every time. "
                f"Estimated gain from closing that gap consistently: ~{gain:.2f}s.")
    else:
        top4 = significant[:4]
        corner_list = ", ".join(f"{n} ({d:.0f} km/h)" for n, d, _, _, _ in top4)
        body = (f"You're carrying less apex speed than your best lap at {len(significant)} corners: "
                f"{corner_list}. "
                f"Your own best lap shows this speed is achievable — it's a repeatability "
                f"problem, not a car capability problem. The biggest single improvement you "
                f"can make is learning to replicate your best corner execution on every lap, "
                f"not just when everything falls right. "
                f"Combined estimate if brought to best-lap average: ~{total_est:.2f}s.")

    findings.append(EngineerFinding(
        title=f"Apex Speed Deficit — {len(significant)} Corner{'s' if len(significant) > 1 else ''}",
        body=body, priority=1, category='pace',
        time_gain_s=total_est,
        corners=[x[0] for x in significant]
    ))


def _brake_point_scatter(findings, corner_report):
    """Corners where brake application point varies significantly lap to lap."""
    if not corner_report or not getattr(corner_report, 'corners', None):
        return

    inconsistent = []
    for cd in corner_report.corners:
        if not cd.lap_brake_points or len(cd.lap_brake_points) < 3:
            continue
        bp_std = float(np.std(cd.lap_brake_points))
        if bp_std < 0.006:    # < 0.6% track — tight enough
            continue
        # Approximate metres: typical iRacing track ~3–5 km → 3500m * std_pct
        scatter_m = bp_std * 3500
        name = cd.corner_name or f"Corner {cd.corner_num + 1}"
        inconsistent.append((name, bp_std, scatter_m))

    if not inconsistent:
        return
    inconsistent.sort(key=lambda x: -x[1])
    total_est = len(inconsistent) * 0.04

    if len(inconsistent) == 1:
        name, _, m = inconsistent[0]
        body = (f"Your brake point at {name} is moving around by roughly {m:.0f}m between laps. "
                f"Every time you brake at a different point, the entry speed changes, "
                f"which changes the turn-in, the apex, and the exit — the whole corner "
                f"unravels from one inconsistency. Pick one fixed external reference "
                f"(a marshal post, a track marking, or the edge of a kerb) and commit "
                f"to it lap after lap. Adjust the reference only after you've hit it "
                f"three laps in a row.")
    else:
        worst = inconsistent[0]
        rest = [n for n, _, _ in inconsistent[1:4]]
        body = (f"Brake point scatter found at {len(inconsistent)} corners. "
                f"The worst is {worst[0]} (~{worst[2]:.0f}m variation); "
                f"also affected: {', '.join(rest)}. "
                f"Variable brake points create a chain reaction through the corner — "
                f"different entry speed leads to different apex, different exit, "
                f"different sector time. Fix your brake references here first; "
                f"everything downstream will stabilise as a result.")

    findings.append(EngineerFinding(
        title=f"Brake Point Consistency — {len(inconsistent)} Corner{'s' if len(inconsistent) > 1 else ''}",
        body=body, priority=2, category='consistency',
        time_gain_s=total_est,
        corners=[x[0] for x in inconsistent]
    ))


def _throttle_application(findings, corner_report, style_report):
    """Rough throttle inputs or hesitant exit throttle."""
    if not style_report:
        return

    smoothness = style_report.throttle_smoothness
    blips = getattr(style_report, 'throttle_blips', 0)
    coast_pct = getattr(style_report, 'coast_time_pct', 0.0)

    if smoothness < 45:
        body = (f"Throttle smoothness is {smoothness:.0f}/100 with {blips} abrupt throttle "
                f"inputs detected across the session. On a rear-wheel-drive car, stabbing "
                f"the throttle rather than squeezing it shifts weight rearward instantly, "
                f"which unloads the front and loads the rear at the worst possible moment — "
                f"right when you're asking the rear to handle both cornering and drive forces. "
                f"Think of the throttle as a volume dial: the transition from 0% to full "
                f"throttle should take 2–3 seconds through slow corners, more through "
                f"medium-speed ones. This alone will reduce your exit oversteer events.")
        findings.append(EngineerFinding(
            title="Throttle Application — Aggressive Inputs Causing Exit Instability",
            body=body, priority=1, category='technique', time_gain_s=0.25
        ))
    elif smoothness < 68:
        body = (f"Throttle smoothness score is {smoothness:.0f}/100 — there's room to "
                f"improve how progressively you build throttle at corner exit. "
                f"Even a small improvement in smoothness on exit will give the rear tires "
                f"more time to load up before being asked to transmit drive torque, "
                f"which means more traction and a higher exit speed. "
                f"Focus specifically on the first 10–15% of throttle application — "
                f"that initial squeeze is where most abruptness happens.")
        findings.append(EngineerFinding(
            title="Throttle Application — Moderate, Room to Improve",
            body=body, priority=2, category='technique', time_gain_s=0.10
        ))

    # Check for hesitant exit throttle at specific corners
    if corner_report and getattr(corner_report, 'corners', None):
        hesitant = []
        for cd in corner_report.corners:
            if cd.throttle_exit_avg < 38 and cd.exit_speed_ms > 15:
                name = cd.corner_name or f"Corner {cd.corner_num + 1}"
                hesitant.append((name, cd.throttle_exit_avg))
        if len(hesitant) >= 2:
            names = ", ".join(n for n, _ in hesitant[:4])
            avg_t = float(np.mean([t for _, t in hesitant]))
            body = (f"Exit throttle is low at {names} — averaging only {avg_t:.0f}% "
                    f"at the exit measurement point. If the car is unstable enough to "
                    f"warrant this caution, it's a setup problem to address. "
                    f"If the car feels stable enough but you're holding back, committing "
                    f"to a more aggressive squeeze from the apex will gain exit speed "
                    f"directly. Check whether a softer rear ARB would give you the "
                    f"confidence to apply more throttle earlier.")
            findings.append(EngineerFinding(
                title=f"Hesitant Exit Throttle — {len(hesitant)} Corners",
                body=body, priority=2, category='technique', time_gain_s=0.12,
                corners=[n for n, _ in hesitant]
            ))


def _sector_time_trend(findings, sector_report):
    """Detect sectors that degrade or improve consistently across laps."""
    if not sector_report or not sector_report.sectors:
        return

    for s in sector_report.sectors:
        if not s.lap_times or len(s.lap_times) < 4:
            continue
        times = np.array(s.lap_times, dtype=float)
        median_t = float(np.median(times))
        # Filter extreme outliers for regression
        mask = times < median_t * 1.4
        if mask.sum() < 4:
            continue
        x = np.arange(len(times))[mask]
        t_f = times[mask]
        slope = float(np.polyfit(x, t_f, 1)[0])

        s_label = f"Sector {s.sector_num + 1}"

        if slope > 0.06:      # degrading > 60ms/lap
            total = slope * len(t_f)
            body = (f"{s_label} is degrading at {slope * 1000:.0f}ms per lap — over "
                    f"your {len(t_f)} clean laps that's {total:.2f}s of accumulated "
                    f"slowdown from start to finish. This pattern typically means one of "
                    f"three things: rear tire overheating (most common in a high-downforce "
                    f"sector), fatigue causing small input errors that compound, or a "
                    f"temperature-sensitive balance issue. Check whether your rear tire "
                    f"temps are climbing through the session — if they are, consider "
                    f"dropping rear tire cold pressure by 0.3–0.5 PSI.")
            findings.append(EngineerFinding(
                title=f"{s_label} Degrading — {slope * 1000:.0f}ms/lap",
                body=body, priority=2, category='tires', time_gain_s=total * 0.4
            ))
        elif slope < -0.05:   # improving > 50ms/lap
            body = (f"{s_label} improved at {abs(slope) * 1000:.0f}ms per lap through "
                    f"the session — a clear learning curve. The pace you found here toward "
                    f"the end of the session is your real baseline for next time; "
                    f"don't use your early-session sector times as the reference. "
                    f"Next session, aim to reach that late-session level within two laps.")
            findings.append(EngineerFinding(
                title=f"{s_label} Improving — Good Learning Rate",
                body=body, priority=3, category='pace'
            ))


def _balance_zones(findings, torque_report):
    """Identify track positions where oversteer or understeer is worst."""
    if not torque_report or not getattr(torque_report, 'has_data', False):
        return

    us_map = np.array(torque_report.understeer_map, dtype=float)
    os_map = np.array(torque_report.oversteer_map, dtype=float)
    if len(us_map) == 0 or len(os_map) == 0:
        return

    us_frac = float(torque_report.us_fraction)
    os_frac = float(torque_report.os_fraction)
    worst_os = int(getattr(torque_report, 'worst_os_pct', 0) * 100)
    worst_us = int(getattr(torque_report, 'worst_us_pct', 0) * 100)

    if os_frac > 0.08:
        # Find top oversteer zones
        thresh = float(np.percentile(os_map[os_map > 0], 75)) if (os_map > 0).any() else 0
        os_zones = [int(i * 100 / len(os_map)) for i in range(len(os_map))
                    if os_map[i] >= thresh and os_map[i] > 0]
        zone_str = (", ".join(f"{z}%" for z in os_zones[:4]) + " of the lap"
                    if os_zones else f"{worst_os}% of the lap")
        body = (f"The steering data shows the rear stepping out at {os_frac:.0%} of corners, "
                f"with the worst oversteer at {zone_str}. "
                f"These are the specific track sections where the rear is losing grip "
                f"faster than the front — at corner exit if these are in the 30–70% zone, "
                f"or at mid-corner if earlier. "
                f"For exit oversteer: soften rear ARB by one click, or reduce diff "
                f"power-side locking. For mid-corner: increase rear downforce or raise "
                f"rear ride height slightly. "
                f"The underlying technique fix is always the same: smoother, later throttle.")
        findings.append(EngineerFinding(
            title=f"Oversteer Zones Identified — Worst at {worst_os}% Track",
            body=body, priority=1 if os_frac > 0.15 else 2, category='setup',
            time_gain_s=0.10
        ))

    if us_frac > 0.12 and us_frac > os_frac:
        zone_str = f"{worst_us}% of the lap"
        body = (f"Understeer is present at {us_frac:.0%} of corners, worst at {zone_str}. "
                f"The front is washing wide before you've reached the apex, which means "
                f"you're either arriving too fast, releasing the brake too quickly, "
                f"or the front suspension is not generating enough load mid-corner. "
                f"The quickest technique fix is trail braking further into the corner — "
                f"keeping some brake pressure as you steer in keeps weight on the front "
                f"and dramatically increases front grip through the initial arc. "
                f"Setup direction if technique doesn't fix it: stiffen front ARB one click "
                f"or soften front rebound damping.")
        findings.append(EngineerFinding(
            title=f"Understeer Zones Identified — Worst at {worst_us}% Track",
            body=body, priority=2, category='setup', time_gain_s=0.08
        ))


def _zone_consistency(findings, data, report):
    """Identify which 10% zone of the track has the most lap-to-lap speed variation."""
    if not data or not report or not report.lap_times:
        return
    speed = data.get_channel('Speed')
    ldp = data.get_channel('LapDistPct')
    if speed is None or ldp is None:
        return
    boundaries = getattr(data, 'lap_boundaries', [])
    if len(boundaries) < 3:
        return

    valid_mask = getattr(report, 'valid_lap_mask', [True] * len(data.lap_times))
    valid_laps = [i for i, v in enumerate(valid_mask) if v]
    if len(valid_laps) < 3:
        return

    NUM_ZONES = 10
    zone_avgs = [[] for _ in range(NUM_ZONES)]

    for li in valid_laps:
        if li + 1 >= len(boundaries):
            continue
        s_idx, e_idx = boundaries[li], boundaries[li + 1]
        lap_ldp = ldp[s_idx:e_idx]
        lap_spd = speed[s_idx:e_idx]
        if len(lap_ldp) < 50:
            continue
        for z in range(NUM_ZONES):
            mask = (lap_ldp >= z / NUM_ZONES) & (lap_ldp < (z + 1) / NUM_ZONES)
            if mask.sum() > 5:
                zone_avgs[z].append(float(np.mean(lap_spd[mask])) * 3.6)

    problem_zones = []
    for z, speeds in enumerate(zone_avgs):
        if len(speeds) < 3:
            continue
        mean_spd = float(np.mean(speeds))
        std_spd = float(np.std(speeds))
        if mean_spd > 0 and std_spd / mean_spd > 0.012:   # > 1.2% CV
            problem_zones.append((z * 10, (z + 1) * 10, std_spd))

    if not problem_zones:
        return
    problem_zones.sort(key=lambda x: -x[2])
    worst = problem_zones[0]

    body = (f"Your biggest lap-to-lap consistency gap is in the "
            f"{worst[0]}–{worst[1]}% zone of the track "
            f"(average speed varies {worst[2]:.1f} km/h between your best and worst laps). "
            f"This is the section costing you the most time spread — "
            f"your best and worst laps diverge here most dramatically. "
            f"Once you can execute this part of the track the same way every lap, "
            f"your overall lap time spread will narrow significantly. "
            f"Focus your next practice session on this zone specifically.")

    if len(problem_zones) > 1:
        second = problem_zones[1]
        body += (f" Secondary concern: {second[0]}–{second[1]}% zone "
                 f"({second[2]:.1f} km/h variation).")

    findings.append(EngineerFinding(
        title=f"Consistency Gap — Largest in {worst[0]}–{worst[1]}% Zone",
        body=body, priority=2, category='consistency',
        time_gain_s=worst[2] * 0.008
    ))


def _fuel_lap_delta(findings, fuel_report, best_report, report):
    """Estimate how much lap time the fuel load added to early laps."""
    if not fuel_report or not getattr(fuel_report, 'has_data', False):
        return
    records = getattr(fuel_report, 'lap_records', [])
    if len(records) < 4:
        return

    avg_l = fuel_report.avg_fuel_per_lap_l
    total_laps = len(records)
    # Estimate total fuel on board lap 1: all laps × avg use
    total_fuel_l = avg_l * total_laps
    # Rule of thumb: ~0.025s per litre of fuel on board (conservative for light cars)
    S_PER_LITRE = 0.025
    penalty_lap1 = total_fuel_l * S_PER_LITRE
    penalty_last = avg_l * S_PER_LITRE
    net_delta = penalty_lap1 - penalty_last

    if net_delta < 0.08:
        return

    body = (f"Lap 1 was carrying roughly {total_fuel_l:.1f}L of fuel, adding an "
            f"estimated {penalty_lap1:.2f}s of lap time penalty from fuel weight alone. "
            f"By the final lap, that penalty had dropped to ~{penalty_last:.2f}s as the "
            f"tank emptied. This means some of your apparent lap time improvement through "
            f"the session came from the car getting lighter — not just from learning the track. "
            f"When comparing your lap times to a qualifying lap or reference lap, "
            f"remember to account for this: your true pace improvement is "
            f"{net_delta:.2f}s less than the raw lap time drop suggests.")
    findings.append(EngineerFinding(
        title="Fuel Weight — Early Laps Artificially Slower",
        body=body, priority=3, category='fuel', time_gain_s=0.0
    ))


def _coast_and_throttle_use(findings, style_report):
    """Excessive coasting or low full-throttle time."""
    if not style_report:
        return

    coast_pct = float(getattr(style_report, 'coast_time_pct', 0.0))
    full_throttle_pct = float(getattr(style_report, 'full_throttle_pct', 0.0))

    if coast_pct > 0.12:
        body = (f"You're coasting — neither braking nor on throttle — for {coast_pct:.0%} of "
                f"the lap. The target for a well-driven lap is under 5–8%. Every moment "
                f"you coast, the car is slowing through aerodynamic drag and rolling "
                f"resistance without any corresponding deceleration benefit that helps "
                f"corner entry. The goal is a continuous transition: brake → trail brake → "
                f"throttle, with no dead zone between them. "
                f"Audit each corner: are you completing your braking before you need to "
                f"steer? If so, brake later. If the coasting is on straights (lifting "
                f"early for a corner), move your lift point closer to the braking zone.")
        findings.append(EngineerFinding(
            title=f"Excessive Coasting — {coast_pct:.0%} of Lap",
            body=body, priority=2, category='technique',
            time_gain_s=max(0.0, (coast_pct - 0.07) * 2.5)
        ))

    if full_throttle_pct < 0.32 and coast_pct < 0.12:
        body = (f"Full throttle time is {full_throttle_pct:.0%} of the lap — "
                f"lower than expected for a circuit with meaningful straight sections. "
                f"This suggests either late throttle application at corner exits, "
                f"hesitation before committing to full throttle on the straights, "
                f"or exit speeds low enough that full throttle is reached later. "
                f"Work backwards: if exit speed from slow corners improves, "
                f"you reach full throttle sooner and hold it longer.")
        findings.append(EngineerFinding(
            title=f"Low Full-Throttle Time — {full_throttle_pct:.0%}",
            body=body, priority=3, category='technique', time_gain_s=0.08
        ))


def _trail_braking_balance(findings, style_report, report):
    """Trail braking technique vs car balance interaction."""
    if not style_report:
        return

    tb_score = float(style_report.trail_braking_score)
    balance = float(getattr(report, 'balance_score', 0.0))

    if tb_score >= 78 and balance > 0.25:
        body = (f"Your trail braking technique is strong ({tb_score:.0f}/100), "
                f"but combined with the car's oversteer tendency, it may be working "
                f"against you at entry. Aggressive trail braking into an already "
                f"oversteery car loads the front strongly, which unloads the rear — "
                f"exactly the condition that causes snap oversteer on turn-in. "
                f"Try releasing the brake slightly earlier on the two or three corners "
                f"where you feel the most rotation, to give the rear time to stabilise "
                f"before the lateral load builds. The setup direction is the same: "
                f"soften rear rebound damping to let the rear settle faster under braking.")
        findings.append(EngineerFinding(
            title="Trail Braking — Aggressive for Current Balance",
            body=body, priority=2, category='technique', time_gain_s=0.06
        ))
    elif tb_score < 48:
        body = (f"Trail braking score is {tb_score:.0f}/100 — you're completing "
                f"your braking before you begin turning in, rather than carrying "
                f"some brake pressure into the corner. "
                f"Trail braking keeps weight on the front axle as you rotate, "
                f"which increases front grip and allows a tighter, later apex. "
                f"Start gently: carry just 15–20% brake pressure into the first "
                f"part of your steering input, then release to zero by mid-corner. "
                f"You'll feel the front bite more strongly and find you can turn in "
                f"later while still hitting the apex. This is one of the highest-value "
                f"technique improvements available to you right now.")
        findings.append(EngineerFinding(
            title="Trail Braking — Significant Time Available at Entry",
            body=body, priority=1, category='technique', time_gain_s=0.20
        ))
