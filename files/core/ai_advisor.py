"""
AI Setup Advisor
Uses the Anthropic API to generate setup recommendations from telemetry analysis.
Supports both blocking and streaming modes.
"""

import time
import threading
from typing import Generator
from core.analysis_engine import AnalysisReport, Severity, format_laptime  # type: ignore[import-unresolved]

# ── Rate limiter ──────────────────────────────────────────────────────────
_MIN_INTERVAL_S = 10  # minimum seconds between API calls
_last_call_time = 0.0
_rate_lock = threading.Lock()


def _check_rate_limit() -> bool:
    """Return True if enough time has passed since the last API call (thread-safe)."""
    global _last_call_time
    with _rate_lock:
        now = time.monotonic()
        if now - _last_call_time < _MIN_INTERVAL_S:
            return False
        _last_call_time = now
        return True


def _sanitize(text: str, max_len: int = 200) -> str:
    """Strip control chars and truncate for safe prompt inclusion."""
    cleaned = ''.join(c for c in text if c.isprintable() or c in '\n\t')
    return cleaned[:max_len]


def _build_prompt(report, car_name, track_name, setup_data, sector_report,
                  style_report, stint_report, best_report,
                  session_info=None) -> str:
    """Build the full prompt string shared by sync and stream paths."""
    car_name = _sanitize(car_name, 120)
    track_name = _sanitize(track_name, 120)
    si = session_info or {}
    issues_text = ""
    for issue in report.issues:
        issues_text += f"- [{issue.severity.value.upper()}] {issue.title}: {issue.description}\n"

    tire_text = ""
    if report.tire_summary:
        for corner, temps in report.tire_summary.items():
            tire_text += f"  {corner}: inner={temps['inner']:.1f}°C, mid={temps['mid']:.1f}°C, outer={temps['outer']:.1f}°C\n"

    setup_text = ""
    if setup_data:
        setup_text = "\nCurrent Setup Parameters:\n"
        for param, val in setup_data.items():
            setup_text += f"  {_sanitize(str(param), 80)}: {_sanitize(str(val), 120)}\n"

    sector_text = ""
    if sector_report and sector_report.sectors:
        sector_text = "\nSector Analysis:\n"
        for i, s in enumerate(sector_report.sectors):
            if s.lap_times:
                sector_text += f"  S{i+1} ({s.start_pct*100:.0f}-{s.end_pct*100:.0f}%): best={s.best_time:.3f}s, avg={s.avg_time:.3f}s, delta=+{s.avg_time-s.best_time:.3f}s\n"
        if sector_report.theoretical_best > 0:
            sector_text += f"  Theoretical best: {format_laptime(sector_report.theoretical_best)}, time left on table: +{sector_report.time_left_on_table:.3f}s\n"
        sector_text += f"  Worst sector: S{sector_report.worst_sector + 1}\n"

    style_text = ""
    if style_report:
        style_text = f"\nDriving Style (scores 0-100):\n"
        style_text += f"  Overall: {style_report.overall_score:.0f}, Braking: {style_report.brake_consistency:.0f}, Throttle: {style_report.throttle_smoothness:.0f}\n"
        style_text += f"  Trail braking: {style_report.trail_braking_pct:.1f}% of brake zones, Coast time: {style_report.coast_time_pct:.1f}%\n"
        if style_report.balance_verdict:
            style_text += f"  Verdict: {style_report.balance_verdict}\n"
        if style_report.style_profile:
            style_text += f"  Profile: {style_report.style_profile}\n"

    stint_text = ""
    if stint_report:
        if stint_report.deg_rate > 0:
            stint_text += f"\nTire Degradation: +{stint_report.deg_rate:.3f}s/lap"
            if stint_report.optimal_stint_length > 0:
                stint_text += f", optimal stint: {stint_report.optimal_stint_length} laps"
            stint_text += "\n"
        if stint_report.findings:
            stint_text += "  Pressure findings: " + "; ".join(stint_report.findings[:3]) + "\n"

    fuel_text = ""
    if best_report:
        if best_report.fuel_per_lap_kg > 0:
            fuel_text += f"\nFuel: {best_report.fuel_per_lap_kg:.2f} kg/lap"
        if best_report.improvement_trend != 0:
            fuel_text += f", trend: {best_report.improvement_trend:+.3f}s/lap"
        if fuel_text:
            fuel_text += "\n"

    grip_text = ""
    if report.grip_utilization_pct > 0:
        grip_text = f"\nGrip Utilization: {report.grip_utilization_pct:.0f}%, Max combined G: {report.max_combined_g:.1f}\n"

    phase_text = ""
    if report.balance_entry != 0 or report.balance_mid != 0 or report.balance_exit != 0:
        phase_text = "\nCorner-Phase Balance (-=understeer, +=oversteer):\n"
        phase_text += f"  Entry (trail-brake): {report.balance_entry:+.2f}\n"
        phase_text += f"  Mid-corner (coast): {report.balance_mid:+.2f}\n"
        phase_text += f"  Exit (power-on): {report.balance_exit:+.2f}\n"

    susp_text = ""
    if report.suspension_summary:
        susp_text = "\nSuspension:\n"
        for corner, s in report.suspension_summary.items():
            susp_text += f"  {corner}: range={s['range']:.1f}mm, bottoming={s['bottoming_pct']:.1f}%\n"

    conditions_text = ""
    if si.get('air_temp_c') is not None or si.get('track_temp_c') is not None:
        parts = []
        if si.get('air_temp_c') is not None:
            parts.append(f"Air Temp: {si['air_temp_c']:.1f}°C")
        if si.get('track_temp_c') is not None:
            parts.append(f"Track Temp: {si['track_temp_c']:.1f}°C")
        if si.get('skies'):
            parts.append(f"Skies: {_sanitize(str(si['skies']), 40)}")
        if si.get('weather_type'):
            parts.append(f"Weather: {_sanitize(str(si['weather_type']), 40)}")
        if si.get('wind_speed_ms') is not None:
            wind_dir = si.get('wind_direction_deg', '')
            parts.append(f"Wind: {si['wind_speed_ms']:.1f} m/s" + (f" @ {wind_dir:.0f}°" if wind_dir != '' else ''))
        conditions_text = "\nSession Conditions:\n  " + ", ".join(parts) + "\n"

    return f"""You are an expert iRacing setup engineer. Analyze this telemetry session and provide specific, actionable setup recommendations.

Car: {car_name}
Track: {track_name}
Best Lap: {format_laptime(report.best_lap)}
Average Lap: {format_laptime(report.avg_lap)}
Balance Score: {report.balance_score:.2f} (-1=understeer, +1=oversteer)
{conditions_text}

Issues Found:
{issues_text if issues_text else "No major issues detected."}

Tire Temperatures:
{tire_text if tire_text else "No tire data available."}
{setup_text}{sector_text}{style_text}{stint_text}{fuel_text}{grip_text}{phase_text}{susp_text}
Provide 3-5 specific setup changes with expected impact. Reference actual current values when available. Distinguish between driver technique issues and car setup issues. Be concise and practical."""


def get_ai_recommendations_sync(report: AnalysisReport, car_name: str,
                                 track_name: str, api_key: str,
                                 setup_data: dict | None = None,
                                 sector_report=None,
                                 style_report=None,
                                 stint_report=None,
                                 best_report=None,
                                 session_info: dict | None = None) -> str:
    """
    Get AI-generated setup recommendations based on analysis report.
    Uses the Anthropic Claude API if available, otherwise returns rule-based advice.
    """
    if not api_key or api_key.strip() == "":
        return _rule_based_recommendations(report, car_name, track_name)

    if not _check_rate_limit():
        return "Please wait a few seconds between AI requests."

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key, timeout=30.0)

        prompt = _build_prompt(report, car_name, track_name, setup_data,
                               sector_report, style_report, stint_report, best_report,
                               session_info=session_info)

        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}]
        )
        return message.content[0].text  # type: ignore[union-attr]

    except ImportError:
        return ("Anthropic package not installed. Install with: pip install anthropic\n\n"
                + _rule_based_recommendations(report, car_name, track_name))
    except Exception as e:
        return ("AI request failed. Check your API key and internet connection.\n\n"
                + _rule_based_recommendations(report, car_name, track_name))


def get_ai_recommendations_stream(report: AnalysisReport, car_name: str,
                                   track_name: str, api_key: str,
                                   setup_data: dict | None = None,
                                   sector_report=None,
                                   style_report=None,
                                   stint_report=None,
                                   best_report=None,
                                   session_info: dict | None = None) -> Generator[str, None, None]:
    """
    Streaming variant — yields text chunks as they arrive from Claude.
    Falls back to a single-yield rule-based response on error.
    """
    if not api_key or api_key.strip() == "":
        yield _rule_based_recommendations(report, car_name, track_name)
        return

    if not _check_rate_limit():
        yield "Please wait a few seconds between AI requests."
        return

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key, timeout=60.0)

        prompt = _build_prompt(report, car_name, track_name, setup_data,
                               sector_report, style_report, stint_report, best_report,
                               session_info=session_info)

        with client.messages.stream(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            for text in stream.text_stream:
                yield text

    except ImportError:
        yield ("Anthropic package not installed. Install with: pip install anthropic\n\n"
               + _rule_based_recommendations(report, car_name, track_name))
    except Exception:
        yield ("AI request failed. Check your API key and internet connection.\n\n"
               + _rule_based_recommendations(report, car_name, track_name))


def _rule_based_recommendations(report: AnalysisReport, car_name: str, track_name: str) -> str:
    """Generate rule-based recommendations without AI API."""
    lines = [f"Setup Recommendations for {car_name} at {track_name}", "=" * 50, ""]

    if report.balance_score < -0.2:
        lines.append("🔧 UNDERSTEER detected:")
        lines.append("  • Soften front anti-roll bar 1-2 clicks")
        lines.append("  • Stiffen rear anti-roll bar 1-2 clicks")
        lines.append("  • Increase front wing angle by 1 step")
        lines.append("  • Reduce front ride height by 1-2mm")
        lines.append("")
    elif report.balance_score > 0.2:
        lines.append("🔧 OVERSTEER detected:")
        lines.append("  • Stiffen front anti-roll bar 1-2 clicks")
        lines.append("  • Soften rear anti-roll bar 1-2 clicks")
        lines.append("  • Increase rear wing angle by 1 step")
        lines.append("  • Increase rear ride height by 1-2mm")
        lines.append("")
    else:
        lines.append("✅ Car balance is neutral — good baseline.")
        lines.append("")

    if report.tire_summary:
        for corner, temps in report.tire_summary.items():
            spread = abs(temps['inner'] - temps['outer'])
            if spread > 10:
                if temps['inner'] > temps['outer']:
                    lines.append(f"🔧 {corner}: Reduce camber by 0.2-0.3° (inner running hot)")
                else:
                    lines.append(f"🔧 {corner}: Increase camber by 0.2-0.3° (outer running hot)")
            if temps['avg'] > 100:
                lines.append(f"🔧 {corner}: Increase cold pressure by 0.5 psi (overheating)")
            elif temps['avg'] < 70:
                lines.append(f"🔧 {corner}: Decrease cold pressure by 0.5 psi (too cool)")

    for issue in report.issues:
        if issue.severity == Severity.CRITICAL:
            lines.append(f"\n⚠️ PRIORITY: {issue.title}")
            lines.append(f"   {issue.recommendation}")

    if not lines[-1]:
        lines.append("No critical setup changes needed. Focus on driver consistency.")

    return "\n".join(lines)
