"""
Lap Consistency Score
Computes a single 0-100 driver consistency rating by combining
lap time variance, sector consistency, corner repeatability,
and brake-point precision.
"""

import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ConsistencyBreakdown:
    """Detailed breakdown of each consistency sub-score."""
    # Sub-scores (0-100, higher = more consistent)
    lap_time_score: float = 0.0
    sector_score: float = 0.0
    corner_score: float = 0.0
    brake_point_score: float = 0.0
    speed_score: float = 0.0

    # Overall composite
    overall: float = 0.0

    # Raw metrics for display
    lap_time_std_s: float = 0.0
    worst_sector: int = 0
    worst_corner: int = 0
    best_corner: int = 0
    brake_point_std_avg: float = 0.0

    # Per-component notes
    notes: List[str] = field(default_factory=list)

    @property
    def grade(self) -> str:
        """Letter grade: A+ through F."""
        if self.overall >= 95:
            return "A+"
        elif self.overall >= 90:
            return "A"
        elif self.overall >= 85:
            return "A-"
        elif self.overall >= 80:
            return "B+"
        elif self.overall >= 75:
            return "B"
        elif self.overall >= 70:
            return "B-"
        elif self.overall >= 65:
            return "C+"
        elif self.overall >= 60:
            return "C"
        elif self.overall >= 50:
            return "D"
        else:
            return "F"

    @property
    def color_hint(self) -> str:
        """Return a color category for UI rendering."""
        if self.overall >= 85:
            return "green"
        elif self.overall >= 70:
            return "yellow"
        else:
            return "red"


# ── Weights ───────────────────────────────────────────────────────────────
W_LAP_TIME = 0.30       # Lap time consistency (most important)
W_SECTOR = 0.20         # Sector-to-sector consistency
W_CORNER = 0.20         # Corner time repeatability
W_BRAKE = 0.15          # Brake point precision
W_SPEED = 0.15          # Entry/exit speed consistency


def compute_consistency(lap_times: List[float],
                        valid_mask: Optional[List[bool]] = None,
                        sector_report=None,
                        corner_report=None,
                        style_report=None) -> ConsistencyBreakdown:
    """
    Compute the composite consistency score from available session data.

    Parameters
    ----------
    lap_times : list of float — raw lap times in seconds
    valid_mask : optional list of bool — True for valid laps (excludes outliers)
    sector_report : SectorAnalysisReport or None
    corner_report : CornerAnalysisReport or None
    style_report : DriverStyleReport or None

    Returns
    -------
    ConsistencyBreakdown with overall score and sub-scores.
    """
    result = ConsistencyBreakdown()

    # ── Filter to valid laps ──────────────────────────────────────────
    times = list(lap_times) if lap_times else []
    if valid_mask and len(valid_mask) == len(times):
        times = [t for t, v in zip(times, valid_mask) if v]

    if len(times) < 2:
        result.overall = 50.0  # not enough data to judge
        result.notes.append("Need at least 2 valid laps for a meaningful score.")
        return result

    # ══════════════════════════════════════════════════════════════════
    # 1. LAP TIME CONSISTENCY (30%)
    # ══════════════════════════════════════════════════════════════════
    std = float(np.std(times))
    mean = float(np.mean(times))
    result.lap_time_std_s = std

    # Scale: 0.0s std = 100, 0.3s std = 90, 1.0s std = 60, 2.0s std = 30, 3.0s+ = 10
    if std <= 0.3:
        lt_score = 90 + (0.3 - std) / 0.3 * 10
    elif std <= 1.0:
        lt_score = 60 + (1.0 - std) / 0.7 * 30
    elif std <= 2.0:
        lt_score = 30 + (2.0 - std) / 1.0 * 30
    else:
        lt_score = max(10, 30 - (std - 2.0) * 10)
    result.lap_time_score = float(np.clip(lt_score, 5, 100))

    if std <= 0.3:
        result.notes.append(f"Excellent lap time consistency (±{std:.3f}s) — pro-level repeatability.")
    elif std <= 1.0:
        result.notes.append(f"Good lap time consistency (±{std:.3f}s) — room to tighten up.")
    elif std <= 2.0:
        result.notes.append(f"Moderate lap time variance (±{std:.3f}s) — focus on eliminating mistakes.")
    else:
        result.notes.append(f"High lap time variance (±{std:.3f}s) — work on building a consistent rhythm.")

    # ══════════════════════════════════════════════════════════════════
    # 2. SECTOR CONSISTENCY (20%)
    # ══════════════════════════════════════════════════════════════════
    if sector_report and sector_report.sectors:
        sector_scores = [s.consistency for s in sector_report.sectors
                         if len(s.lap_times) >= 2]
        if sector_scores:
            result.sector_score = float(np.mean(sector_scores))
            worst_idx = int(np.argmin(sector_scores))
            result.worst_sector = worst_idx + 1
            worst_val = min(sector_scores)
            if worst_val < 85:
                result.notes.append(
                    f"Sector {result.worst_sector} is your least consistent "
                    f"({worst_val:.0f}%) — focus practice reps here.")
        else:
            result.sector_score = result.lap_time_score  # fallback
    else:
        result.sector_score = result.lap_time_score  # fallback

    # ══════════════════════════════════════════════════════════════════
    # 3. CORNER TIME CONSISTENCY (20%)
    # ══════════════════════════════════════════════════════════════════
    if corner_report and corner_report.corners:
        corner_scores = [c.consistency_pct for c in corner_report.corners
                         if len(c.lap_times_s) >= 2]
        if corner_scores:
            result.corner_score = float(np.mean(corner_scores))
            worst_ci = int(np.argmin(corner_scores))
            best_ci = int(np.argmax(corner_scores))
            result.worst_corner = corner_report.corners[worst_ci].corner_num
            result.best_corner = corner_report.corners[best_ci].corner_num
            worst_val = min(corner_scores)
            if worst_val < 85:
                result.notes.append(
                    f"Turn {result.worst_corner} is your least repeatable corner "
                    f"({worst_val:.0f}%) — practice this corner in isolation.")
        else:
            result.corner_score = result.lap_time_score
    else:
        result.corner_score = result.lap_time_score

    # ══════════════════════════════════════════════════════════════════
    # 4. BRAKE POINT PRECISION (15%)
    # ══════════════════════════════════════════════════════════════════
    if corner_report and corner_report.corners:
        bp_scores = [c.brake_point_consistency for c in corner_report.corners
                     if len(c.lap_brake_points) >= 2]
        if bp_scores:
            # Clamp individual scores to [0, 100] before averaging
            bp_scores = [float(np.clip(s, 0, 100)) for s in bp_scores]
            result.brake_point_score = float(np.mean(bp_scores))
            bp_stds = [float(np.std(c.lap_brake_points))
                       for c in corner_report.corners if len(c.lap_brake_points) >= 2]
            result.brake_point_std_avg = float(np.mean(bp_stds)) if bp_stds else 0.0
            if result.brake_point_score < 70:
                result.notes.append(
                    "Brake markers are inconsistent — pick fixed reference points "
                    "(signs, curb markings) for each braking zone.")
            elif result.brake_point_score > 90:
                result.notes.append("Strong brake point precision — hitting marks consistently.")
        else:
            result.brake_point_score = _fallback_brake(style_report, result.lap_time_score)
    elif style_report:
        result.brake_point_score = _fallback_brake(style_report, result.lap_time_score)
    else:
        result.brake_point_score = result.lap_time_score

    # ══════════════════════════════════════════════════════════════════
    # 5. SPEED CONSISTENCY (15%)
    # ══════════════════════════════════════════════════════════════════
    if corner_report and corner_report.corners:
        speed_scores = []
        for c in corner_report.corners:
            if len(c.lap_entry_speeds) >= 2:
                entry_cv = float(np.std(c.lap_entry_speeds) / max(np.mean(c.lap_entry_speeds), 1))
                speed_scores.append(float(np.clip(100 - entry_cv * 200, 30, 100)))
            if len(c.lap_exit_speeds) >= 2:
                exit_cv = float(np.std(c.lap_exit_speeds) / max(np.mean(c.lap_exit_speeds), 1))
                speed_scores.append(float(np.clip(100 - exit_cv * 200, 30, 100)))
        if speed_scores:
            result.speed_score = float(np.mean(speed_scores))
        else:
            result.speed_score = result.lap_time_score
    else:
        result.speed_score = result.lap_time_score

    # ══════════════════════════════════════════════════════════════════
    # COMPOSITE
    # ══════════════════════════════════════════════════════════════════
    result.overall = float(np.dot(
        [W_LAP_TIME, W_SECTOR, W_CORNER, W_BRAKE, W_SPEED],
        [result.lap_time_score, result.sector_score, result.corner_score,
         result.brake_point_score, result.speed_score]
    ))
    result.overall = float(np.clip(result.overall, 0, 100))

    # Grade-level note
    if result.overall >= 90:
        result.notes.append("Outstanding consistency — you're driving like a pro. Focus on raw speed.")
    elif result.overall >= 80:
        result.notes.append("Strong consistency — small gains available by tightening your weakest area.")
    elif result.overall >= 70:
        result.notes.append("Decent consistency — the biggest gains are in repeatability, not outright speed.")
    elif result.overall >= 60:
        result.notes.append("Building consistency — focus on hitting the same marks every lap before pushing harder.")
    else:
        result.notes.append("Consistency is the priority — slow down slightly and focus on clean, repeatable laps.")

    return result


def _fallback_brake(style_report, lap_score: float) -> float:
    """Use driving style brake_consistency if corner data isn't available."""
    if style_report and style_report.brake_consistency > 0:
        return style_report.brake_consistency
    return lap_score
