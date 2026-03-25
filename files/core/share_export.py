"""
One-Click Share Export — Export compact analysis summary as JSON.
Designed for sharing with teammates or for record-keeping.
"""

import json
import os
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any
from datetime import datetime


@dataclass
class ShareSummary:
    """Compact session summary for sharing."""
    app_version: str
    export_time: str
    car_name: str
    track_name: str
    num_laps: int
    best_lap: float
    avg_lap: float
    lap_times: List[float]
    consistency_score: float
    consistency_grade: str
    # Setup snapshot
    setup_highlights: Dict[str, Any]
    # Key findings
    issues: List[str]
    tire_findings: List[str]
    fuel_info: Dict[str, Any]
    # Sector breakdown
    sector_times: List[float]
    theoretical_best: float
    # Weather
    conditions: Dict[str, Any]


def build_share_summary(
    data,
    report,
    consistency=None,
    sector_report=None,
    stint_report=None,
    setup=None,
    app_version: str = "1.0",
) -> ShareSummary:
    """
    Build a compact share summary from session data.

    Parameters
    ----------
    data : TelemetryData
    report : AnalysisReport
    consistency : ConsistencyBreakdown or None
    sector_report : SectorAnalysisReport or None
    stint_report : TireDegReport or None
    setup : ParsedSetup or None
    app_version : version string
    """
    issues = [f.title for f in report.issues] if report.issues else []
    tire_findings = stint_report.findings if stint_report else []
    fuel_info = {}
    fuel_ch = data.get_channel('FuelLevel')
    if fuel_ch is not None and data.num_laps > 0:
        fuel_start = float(fuel_ch[data.lap_boundaries[0]])
        fuel_end = float(fuel_ch[min(data.lap_boundaries[-1], len(fuel_ch) - 1)])
        fuel_info = {
            "fuel_start_l": round(fuel_start, 1),
            "fuel_end_l": round(fuel_end, 1),
            "fuel_per_lap_l": round((fuel_start - fuel_end) / max(data.num_laps, 1), 2),
        }

    sector_times = []
    theoretical = 0.0
    if sector_report:
        sector_times = [s.best_time for s in sector_report.sectors]
        theoretical = sector_report.theoretical_best

    conditions = {}
    si = data.session_info
    if si:
        conditions = {
            k: si[k] for k in ['air_temp_c', 'track_temp_c', 'wind_speed_ms',
                                'wind_direction_deg', 'weather_type', 'skies']
            if k in si
        }

    setup_highlights = {}
    if setup and hasattr(setup, 'flat') and setup.flat:
        # Pick key setup params
        for key in ['front_wing', 'rear_wing', 'front_arb', 'rear_arb',
                     'LF_cold_psi', 'RF_cold_psi', 'LR_cold_psi', 'RR_cold_psi',
                     'brake_bias', 'tc_level', 'abs_level']:
            if key in setup.flat:
                setup_highlights[key] = setup.flat[key]

    con_score = consistency.overall if consistency else 0.0
    con_grade = consistency.grade if consistency else "N/A"

    return ShareSummary(
        app_version=app_version,
        export_time=datetime.now().isoformat(timespec='seconds'),
        car_name=data.car_name,
        track_name=data.track_name,
        num_laps=data.num_laps,
        best_lap=report.best_lap,
        avg_lap=report.avg_lap,
        lap_times=list(data.lap_times),
        consistency_score=con_score,
        consistency_grade=con_grade,
        setup_highlights=setup_highlights,
        issues=issues,
        tire_findings=tire_findings,
        fuel_info=fuel_info,
        sector_times=sector_times,
        theoretical_best=theoretical,
        conditions=conditions,
    )


def export_json(summary: ShareSummary, path: str) -> str:
    """Export share summary as formatted JSON. Returns the file path written."""
    d = asdict(summary)
    # Round floats for readability
    d['best_lap'] = round(d['best_lap'], 3)
    d['avg_lap'] = round(d['avg_lap'], 3)
    d['consistency_score'] = round(d['consistency_score'], 1)
    d['theoretical_best'] = round(d['theoretical_best'], 3)
    d['lap_times'] = [round(t, 3) for t in d['lap_times']]
    d['sector_times'] = [round(t, 3) for t in d['sector_times']]

    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(d, f, indent=2, ensure_ascii=False)
    return path


def export_clipboard_text(summary: ShareSummary) -> str:
    """Generate a compact text summary for clipboard sharing."""
    lines = [
        f"🏁 {summary.car_name} @ {summary.track_name}",
        f"Best: {_fmt(summary.best_lap)} | Avg: {_fmt(summary.avg_lap)} | Laps: {summary.num_laps}",
        f"Consistency: {summary.consistency_score:.0f}/100 ({summary.consistency_grade})",
    ]
    if summary.sector_times:
        st = " | ".join(f"S{i+1}: {_fmt(t)}" for i, t in enumerate(summary.sector_times))
        lines.append(f"Sectors: {st}")
        if summary.theoretical_best > 0:
            lines.append(f"Theoretical best: {_fmt(summary.theoretical_best)}")
    if summary.fuel_info:
        lines.append(f"Fuel/lap: {summary.fuel_info.get('fuel_per_lap_l', '?')}L")
    if summary.conditions:
        parts = []
        if 'air_temp_c' in summary.conditions:
            parts.append(f"Air: {summary.conditions['air_temp_c']}°C")
        if 'track_temp_c' in summary.conditions:
            parts.append(f"Track: {summary.conditions['track_temp_c']}°C")
        if parts:
            lines.append("Conditions: " + " | ".join(parts))
    if summary.issues:
        lines.append("Key issues: " + "; ".join(summary.issues[:3]))
    lines.append(f"Exported: {summary.export_time}")
    return "\n".join(lines)


def _fmt(seconds: float) -> str:
    """Format lap time as M:SS.mmm."""
    if seconds <= 0:
        return "—"
    m = int(seconds // 60)
    s = seconds - m * 60
    return f"{m}:{s:06.3f}" if m > 0 else f"{s:.3f}"
