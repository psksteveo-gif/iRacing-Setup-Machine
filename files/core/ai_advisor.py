"""
Optimal Sector
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


# ── Retry helper ──────────────────────────────────────────────────────────
_MAX_RETRIES = 2          # attempt up to 3 total calls (1 + 2 retries)
_RETRY_BASE_DELAY = 1.5   # seconds; doubles each retry


def _is_retryable_error(exc: Exception) -> bool:
    """Return True for transient errors that are worth retrying."""
    msg = str(exc).lower()
    # Retry on network issues, timeouts, and 529 overload — not on auth or content errors
    retryable_keywords = ('timeout', 'connection', 'network', 'overloaded',
                          'service unavailable', '529', '503', '502', 'reset')
    non_retryable = ('invalid_api_key', 'authentication', '401', '403',
                     'content_policy', 'permission')
    if any(kw in msg for kw in non_retryable):
        return False
    return any(kw in msg for kw in retryable_keywords)


def _stream_with_retry(client, *, model: str, max_tokens: int,
                       messages: list, system: str = "") -> list[str]:
    """
    Call client.messages.stream() with up to _MAX_RETRIES retries on transient errors.
    Returns all text chunks as a list (collected before yielding to allow retry).
    Raises the final exception if all retries are exhausted.
    """
    kwargs: dict = dict(model=model, max_tokens=max_tokens, messages=messages)
    if system:
        kwargs['system'] = system
    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES + 1):
        try:
            chunks: list[str] = []
            with client.messages.stream(**kwargs) as stream:
                for text in stream.text_stream:
                    chunks.append(text)
            return chunks
        except Exception as exc:
            last_exc = exc
            if attempt < _MAX_RETRIES and _is_retryable_error(exc):
                delay = _RETRY_BASE_DELAY * (2 ** attempt)
                import logging as _log
                _log.getLogger(__name__).warning(
                    "API call failed (attempt %d/%d): %s — retrying in %.1fs",
                    attempt + 1, _MAX_RETRIES + 1, exc, delay,
                )
                time.sleep(delay)
            else:
                break
    raise last_exc  # type: ignore[misc]


def _weather_guidance(si: dict) -> str:
    """
    Translate raw session conditions into concrete setup adjustment guidance
    for the AI prompt.  Returns an empty string if no useful data is available.
    """
    lines = []
    air   = si.get('air_temp_c')
    track = si.get('track_temp_c')
    wtype = str(si.get('weather_type', '')).lower()
    skies = str(si.get('skies', '')).lower()
    wind  = si.get('wind_speed_ms')

    # ── Wet / rain ──────────────────────────────────────────────────────────
    is_wet = any(k in wtype for k in ('rain', 'wet', 'storm')) or \
             any(k in skies for k in ('rain', 'overcast'))
    if is_wet:
        lines += [
            "WET CONDITIONS — mandatory setup changes:",
            "  • Tire pressures: start 1.5–2.0 psi LOWER than dry baseline (cold wet rubber needs more contact patch)",
            "  • Wing angles: reduce by 1–2 steps each end (less drag; mechanical grip matters more than aero)",
            "  • Ride heights: raise 3–5 mm front and rear (water standing on track reduces aero sensitivity)",
            "  • Brake bias: shift 1–2% rearward (front lock risk rises dramatically on wet tarmac)",
            "  • ARBs: soften 1 step each end (suspension compliance helps maintain traction on slippery surfaces)",
            "  • TC: increase 1–2 levels (exit wheelspin is far more costly than TC intervention in the wet)",
            "  • ABS: increase 1 level (consistent braking distances are harder to achieve)",
        ]

    # ── Track temperature ───────────────────────────────────────────────────
    if track is not None and not is_wet:
        if track >= 50.0:
            lines += [
                f"HOT TRACK ({track:.0f}°C) — tire pressure management critical:",
                "  • Cold tire pressures: start 0.5–1.0 psi LOWER than baseline (tires reach operating temp very quickly and peak pressure will be high)",
                "  • Expect front tires to overheat on long stints — consider slightly higher front pressures if inner-edge wear appears",
                "  • Brake cooling ducts (if adjustable): open 1–2 steps (brake fade risk rises sharply above 45°C ambient)",
                "  • Fuel load effect is amplified — watch balance shift over stint length",
            ]
        elif track >= 40.0:
            lines += [
                f"WARM TRACK ({track:.0f}°C) — minor pressure adjustment:",
                "  • Cold tire pressures: start 0.25–0.5 psi lower than baseline",
                "  • Tires reach operating window quickly — avoid excessive warm-up laps wasting rubber",
            ]
        elif track <= 20.0:
            lines += [
                f"COLD TRACK ({track:.0f}°C) — tires slow to reach optimal window:",
                "  • Cold tire pressures: start 1.0–2.0 psi HIGHER than baseline (pressures drop further before tires warm up)",
                "  • Warm-up laps are critical — at least 2 full laps before pushing",
                "  • Reduce TC by 1 level only once confident tires are up to temperature",
                "  • Brake bias: consider 0.5% more front (cold rears lock more easily)",
            ]
        elif track <= 28.0:
            lines += [
                f"COOL TRACK ({track:.0f}°C) — modest pressure increase recommended:",
                "  • Cold tire pressures: start 0.5 psi higher than baseline",
                "  • First flying lap may feel understeer as fronts lag behind rears in warm-up",
            ]

    # ── Air temperature / density ───────────────────────────────────────────
    if air is not None and not is_wet:
        if air >= 35.0:
            lines.append(
                f"HIGH AIR TEMP ({air:.0f}°C): reduced air density → marginally less downforce (~1–2%). "
                "No setup change needed but be aware top speed will be slightly higher than baseline suggests."
            )
        elif air <= 10.0:
            lines.append(
                f"LOW AIR TEMP ({air:.0f}°C): dense cold air → slightly more downforce than baseline. "
                "Car may feel more planted than expected. Engine also produces peak power more easily."
            )

    # ── Wind ────────────────────────────────────────────────────────────────
    if wind is not None and wind >= 6.0:
        wind_dir = si.get('wind_direction_deg')
        dir_str  = f" from {wind_dir:.0f}°" if wind_dir is not None else ""
        lines += [
            f"SIGNIFICANT WIND ({wind:.1f} m/s{dir_str}) — handling implications:",
            "  • High-speed corner balance will vary lap-to-lap depending on wind direction vs corner heading",
            "  • Consider 0.5–1 step more rear wing for stability if main straight is a headwind",
            "  • Brake markers may need adjusting into a headwind (car brakes shorter) vs tailwind (longer zone)",
        ]

    if not lines:
        return ""
    return "CONDITION-SPECIFIC SETUP ADJUSTMENTS:\n" + "\n".join(lines) + "\n"


def _sanitize(text: str, max_len: int = 200) -> str:
    """Strip control chars and truncate for safe prompt inclusion."""
    cleaned = ''.join(c for c in text if c.isprintable() or c in '\n\t')
    return cleaned[:max_len]


def _build_prompt(report, car_name, track_name, setup_data, sector_report,
                  style_report, stint_report, best_report,
                  session_info=None, corner_report=None,
                  incident_report=None, evolution_report=None,
                  car_class_str: str = "") -> str:
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

    corner_text = ""
    if corner_report is not None:
        try:
            from core.corner_analysis import format_corner_summary
            corner_text = format_corner_summary(corner_report)
        except Exception:
            pass

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

    quality_text = ""
    if incident_report is not None:
        quality_text = f"\nSession Quality: {incident_report.summary_text()}\n"
    if evolution_report is not None and evolution_report.detected:
        quality_text += f"{evolution_report.for_prompt()}\n"

    # ── Tech inspection bounds ────────────────────────────────────────────────
    tech_bounds_text = ""
    try:
        from core.car_classifier import classify_car, CarClass
        from core.tech_inspector import bounds_summary_for_prompt
        _cls_str = car_class_str or (report.car_class if hasattr(report, 'car_class') else "")
        if _cls_str:
            try:
                car_class = CarClass(_cls_str.lower())
            except (ValueError, AttributeError):
                car_class = classify_car(car_name)
        else:
            car_class = classify_car(car_name)
        tech_bounds_text = bounds_summary_for_prompt(car_class)
    except Exception:
        tech_bounds_text = ""

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

    tech_section = f"""
TECH INSPECTION — MANDATORY COMPLIANCE
=======================================
{tech_bounds_text}
CRITICAL: ALL setup values you recommend MUST fall within the legal ranges above.
Never suggest a value outside these bounds. If a current value is already at the limit, do not recommend moving it further in that direction.
Any recommendation that violates these bounds will cause the driver to FAIL tech inspection and be disqualified. Compliance is non-negotiable.
""" if tech_bounds_text else ""

    return f"""You are an expert iRacing setup engineer. Analyze this telemetry session and provide specific, actionable setup recommendations.

Car: {car_name}
Track: {track_name}
Best Lap: {format_laptime(report.best_lap)}
Average Lap: {format_laptime(report.avg_lap)}
Balance Score: {report.balance_score:.2f} (-1=understeer, +1=oversteer)
{conditions_text}{quality_text}
Issues Found:
{issues_text if issues_text else "No major issues detected."}

Tire Temperatures:
{tire_text if tire_text else "No tire data available."}
{setup_text}{sector_text}{style_text}{stint_text}{fuel_text}{grip_text}{phase_text}{susp_text}
{corner_text}{tech_section}
For EACH corner with issues, provide a specific setup change recommendation that addresses the problem at that corner. Reference corners by name (e.g. "Eau Rouge entry" or "T3 Andretti Hairpin") where names are available.

Provide 3-5 specific setup changes with expected impact, prioritizing the worst corners. Reference actual current values when available. Distinguish between driver technique issues (brake point, throttle timing) and car setup issues (balance, springs, ARB, aero). Be concise and practical.
At the end of your response, add a one-line tech inspection summary: either "✅ All recommended values are within legal limits." or list any parameters that could not be confirmed within bounds."""


_MODEL_HAIKU  = "claude-haiku-4-5-20251001"
_MODEL_SONNET = "claude-sonnet-4-6"


def get_setup_recommendation_stream(
        report,
        car_name: str,
        track_name: str,
        api_key: str,
        setup=None,
        opt_result=None,
        model: str = _MODEL_HAIKU) -> Generator[str, None, None]:
    """
    Stream a focused Claude analysis for the Recommend to iRacing dialog.

    Validates and enriches the optimizer's suggested changes with physics
    reasoning, warns about risks, and adds track-specific context.

    Parameters
    ----------
    report      : AnalysisReport  — telemetry analysis
    car_name    : str
    track_name  : str
    api_key     : str
    setup       : ParsedSetup | None — IBT-extracted setup (flat dict)
    opt_result  : OptimizationResult | None — optimizer output
    model       : str — Claude model ID ('haiku' or 'sonnet')
    """
    if not api_key or not api_key.strip():
        yield "Set your Anthropic API key in Settings (⚙) to get Claude's analysis."
        return

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key, timeout=60.0)
    except ImportError:
        yield "Install the anthropic package: pip install anthropic"
        return

    car_name   = _sanitize(car_name, 120)
    track_name = _sanitize(track_name, 120)

    # --- Build context blocks ---
    bal = report.balance_score if report else 0.0
    bal_desc = (
        f"{bal:+.2f} — "
        + ("significant oversteer" if bal > 0.3
           else "mild oversteer" if bal > 0.05
           else "neutral" if abs(bal) <= 0.05
           else "mild understeer" if bal > -0.3
           else "significant understeer")
    )

    phase_text = ""
    if report and (report.balance_entry or report.balance_mid or report.balance_exit):
        phase_text = (
            f"\nCorner phase balance (+=OS, -=US):\n"
            f"  Entry:  {report.balance_entry:+.2f}\n"
            f"  Mid:    {report.balance_mid:+.2f}\n"
            f"  Exit:   {report.balance_exit:+.2f}"
        )

    tire_text = ""
    if report and report.tire_summary:
        tire_text = "\nTire temperatures:\n"
        for corner, temps in report.tire_summary.items():
            tire_text += (f"  {corner}: inner={temps['inner']:.0f}°C "
                          f"mid={temps['mid']:.0f}°C outer={temps['outer']:.0f}°C "
                          f"avg={temps['avg']:.0f}°C\n")

    issues_text = ""
    if report and report.issues:
        issues_text = "\nDetected issues:\n"
        for iss in report.issues[:6]:
            issues_text += f"  [{iss.severity.value.upper()}] {iss.title}: {iss.description}\n"

    setup_text = ""
    if setup and hasattr(setup, 'flat') and setup.flat:
        pairs = [f"  {_sanitize(k, 60)}: {_sanitize(str(v), 80)}"
                 for k, v in list(setup.flat.items())[:40]]
        setup_text = "\nCurrent setup (from IBT):\n" + "\n".join(pairs)

    changes_text = ""
    if opt_result and opt_result.changes:
        changes_text = "\nOptimizer recommended changes:\n"
        for ch in opt_result.changes:
            param = ch.get('parameter', '').replace('_', ' ')
            delta = ch.get('delta', 0)
            sign = '+' if delta > 0 else ''
            changes_text += f"  {param}: {sign}{delta:g}\n"

    best_lap = f"{report.best_lap:.3f}s" if report and report.best_lap else "unknown"

    prompt = f"""You are an expert iRacing setup engineer. A driver has loaded their telemetry and the app's optimizer has suggested setup changes. Your job is to:
1. Validate the optimizer's recommendations — explain WHY each change makes sense (or flag if risky)
2. Add context specific to this car and track
3. Note any setup concerns the optimizer may have missed (e.g. tire temp imbalances suggesting camber issue)
4. Give a 1-sentence priority tip: the single most impactful change to make first

Car: {car_name}
Track: {track_name}
Best lap: {best_lap}
Balance score: {bal_desc}
{phase_text}
{tire_text}
{issues_text}
{setup_text}
{changes_text}
Keep your response under 250 words. Use short paragraphs, no bullet soup. Speak directly to the driver."""

    try:
        chunks = _stream_with_retry(
            client, model=model, max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        for text in chunks:
            yield text
    except Exception as e:
        yield f"AI request failed: {e}\nCheck your API key and internet connection."


def get_ai_recommendations_sync(report: AnalysisReport, car_name: str,
                                 track_name: str, api_key: str,
                                 setup_data: dict | None = None,
                                 sector_report=None,
                                 style_report=None,
                                 stint_report=None,
                                 best_report=None,
                                 session_info: dict | None = None,
                                 corner_report=None,
                                 incident_report=None,
                                 evolution_report=None,
                                 car_class_str: str = "") -> str:
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
                               session_info=session_info, corner_report=corner_report,
                               incident_report=incident_report, evolution_report=evolution_report,
                               car_class_str=car_class_str)

        message = client.messages.create(
            model=_MODEL_SONNET,
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
                                   session_info: dict | None = None,
                                   corner_report=None,
                                   incident_report=None,
                                   evolution_report=None,
                                   car_class_str: str = "") -> Generator[str, None, None]:
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
                               session_info=session_info, corner_report=corner_report,
                               incident_report=incident_report, evolution_report=evolution_report,
                               car_class_str=car_class_str)

        chunks = _stream_with_retry(
            client, model=_MODEL_SONNET, max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        for text in chunks:
            yield text

    except ImportError:
        yield ("Anthropic package not installed. Install with: pip install anthropic\n\n"
               + _rule_based_recommendations(report, car_name, track_name))
    except Exception:
        yield ("AI request failed. Check your API key and internet connection.\n\n"
               + _rule_based_recommendations(report, car_name, track_name))


def generate_session_note_stream(
        report,
        car_name: str,
        track_name: str,
        api_key: str,
        sector_report=None,
        style_report=None,
        session_info: dict | None = None) -> Generator[str, None, None]:
    """
    Auto-generate a concise 3-sentence session diary entry.
    Streams the response. Intended for automatic post-load notes.
    """
    if not api_key or api_key.strip() == "":
        return

    # Use a separate rate limit token — don't consume the main one
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key, timeout=20.0)
    except ImportError:
        return

    car_name = _sanitize(car_name, 120)
    track_name = _sanitize(track_name, 120)
    si = session_info or {}

    issues_line = ""
    if report and report.issues:
        issues_line = "Key issues: " + "; ".join(i.title for i in report.issues[:3])

    sector_line = ""
    if sector_report and getattr(sector_report, 'time_left_on_table', 0) > 0:
        sector_line = f"Time left on table: +{sector_report.time_left_on_table:.3f}s."

    style_line = ""
    if style_report:
        style_line = f"Driving style: {style_report.style_profile}. {style_report.balance_verdict}."

    best_lap = _sanitize(str(round(report.best_lap, 3)) if report else "?", 20)

    prompt = f"""Summarise this iRacing session as a driver diary entry in exactly 3 concise sentences. Sound like a driver writing their own notes after a session — factual, specific, no fluff.

Car: {car_name}  Track: {track_name}  Best lap: {best_lap}s
{issues_line}
{sector_line}
{style_line}

Write 3 sentences max. No bullet points. No intro phrase like "In this session..."."""

    try:
        with client.messages.stream(
            model=_MODEL_SONNET,
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            for text in stream.text_stream:
                yield text
    except Exception:
        return


def ask_setup_question_stream(
        question: str,
        report: AnalysisReport,
        car_name: str,
        track_name: str,
        api_key: str,
        setup_data: dict | None = None,
        sector_report=None,
        session_info: dict | None = None) -> Generator[str, None, None]:
    """
    Answer a specific natural-language question about the current setup or telemetry.
    Streams the response in real time.

    Intended for targeted queries like "What if I soften the front ARB 2 clicks?"
    or "Why is the car understeering at Turn 3 exit?".
    """
    if not api_key or api_key.strip() == "":
        yield "API key required to answer setup questions. Set it in Settings (⚙)."
        return

    if not _check_rate_limit():
        yield "Please wait a few seconds between AI requests."
        return

    car_name = _sanitize(car_name, 120)
    track_name = _sanitize(track_name, 120)
    question_clean = _sanitize(question.strip(), 600)
    if not question_clean:
        yield "Please enter a question."
        return

    si = session_info or {}

    # Compact context summary
    balance_line = f"Balance: {report.balance_score:+.2f} (-1=US, +1=OS)" if report else ""
    issues_summary = ""
    if report and report.issues:
        top = report.issues[:4]
        issues_summary = "Top issues: " + "; ".join(f"{i.title}" for i in top)

    setup_text = ""
    if setup_data:
        lines = [f"  {_sanitize(str(k), 60)}: {_sanitize(str(v), 80)}"
                 for k, v in list(setup_data.items())[:50]]
        setup_text = "Current setup:\n" + "\n".join(lines)

    sector_text = ""
    if sector_report and sector_report.sectors:
        worst = getattr(sector_report, 'worst_sector', None)
        tbl = getattr(sector_report, 'time_left_on_table', 0.0)
        if worst is not None:
            sector_text = f"Worst sector: S{worst + 1}; time left on table: +{tbl:.3f}s"

    conditions_text = ""
    if si.get('air_temp_c') is not None or si.get('track_temp_c') is not None:
        parts = []
        if si.get('air_temp_c') is not None:
            parts.append(f"Air {si['air_temp_c']:.1f}°C")
        if si.get('track_temp_c') is not None:
            parts.append(f"Track {si['track_temp_c']:.1f}°C")
        conditions_text = ", ".join(parts)

    prompt = f"""You are an expert iRacing setup engineer. Answer the driver's specific question concisely (2–5 sentences).

Car: {car_name}
Track: {track_name}
{balance_line}
{issues_summary}
{sector_text}
{conditions_text}
{setup_text}

Question: {question_clean}

Answer directly and specifically. If the question concerns a setup parameter change, explain the expected effect on car balance, tire behaviour, and lap time. Reference current values where relevant. If the question is about driver technique, distinguish setup vs driver cause."""

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key, timeout=30.0)
        with client.messages.stream(
            model=_MODEL_SONNET,
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            for text in stream.text_stream:
                yield text
    except ImportError:
        yield "Anthropic package not installed. Run: pip install anthropic"
    except Exception:
        yield "AI request failed. Check your API key and internet connection."


def generate_tech_legal_setup_stream(
        report: AnalysisReport,
        car_name: str,
        track_name: str,
        api_key: str,
        car_class_str: str = "gt3",
        style_report=None,
        stint_report=None,
        sector_report=None,
        corner_report=None,
        current_setup: dict | None = None,
        session_info: dict | None = None,
        track_info=None,
        stint_mode: str = "race",   # "qualifying" | "race" | "endurance"
) -> "Generator[str, None, None]":
    """
    Generate a complete, tech-inspection-passing iRacing setup tailored to
    the driver's telemetry, balance issues, and driving style.

    Requires a valid Anthropic API key.  Falls back to a rule-based summary
    if the key is missing or the call fails.

    Yields text chunks as they stream from Claude.

    Why setups can fail tech inspection
    ------------------------------------
    The genetic-algorithm optimizer previously worked only in delta-space
    (±clicks) without validating whether the resulting absolute value stayed
    inside the car's legal garage range.  This function solves that by:

    1. Including the full legal bounds table in the prompt so Claude knows
       exactly what values are allowed.
    2. Instructing Claude to emit a structured parameter table that can be
       validated and clamped by ``tech_inspector.clamp_to_legal()``.
    3. Explaining *why* the setup is built the way it is — connecting every
       change to a specific telemetry finding or driving-style observation.
    """
    from typing import Generator  # local import avoids circular at module level

    if not api_key or api_key.strip() == "":
        yield _rule_based_recommendations(report, car_name, track_name)
        return

    if not _check_rate_limit():
        yield "Please wait a few seconds between AI requests."
        return

    # ── Resolve car class ──────────────────────────────────────────────────
    try:
        from core.car_classifier import CarClass, car_class_profile_text
        try:
            car_class = CarClass(car_class_str.lower())
        except ValueError:
            car_class = CarClass.DEFAULT
    except Exception:
        car_class = None

    # ── Legal bounds ───────────────────────────────────────────────────────
    try:
        from core.tech_inspector import bounds_summary_for_prompt
        bounds_text = bounds_summary_for_prompt(car_class) if car_class else \
            "(parameter bounds unavailable — stay within iRacing garage slider limits)"
    except Exception:
        bounds_text = "(parameter bounds unavailable — stay within iRacing garage slider limits)"

    # ── Car class personality ──────────────────────────────────────────────
    try:
        car_profile = car_class_profile_text(car_class) if car_class else ""
    except Exception:
        car_profile = ""

    # ── Baseline setup (grounded starting point) ───────────────────────────
    try:
        from data.templates.track_templates import get_baseline_setup_text
        baseline_text = get_baseline_setup_text(
            car_class_str.lower() if car_class_str else "gt3",
            track_name)
    except Exception:
        baseline_text = "(baseline unavailable)"

    # ── Driving style → setup hints ────────────────────────────────────────
    style_hints: list = []
    if style_report is not None:
        try:
            from core.driving_style import driving_style_to_setup_hints
            style_hints = driving_style_to_setup_hints(style_report)
        except Exception:
            pass

    # ── Build prompt sections ──────────────────────────────────────────────
    car_name    = _sanitize(car_name, 120)
    track_name  = _sanitize(track_name, 120)
    si          = session_info or {}

    # Telemetry overview
    telem_lines = [
        f"Car: {car_name}",
        f"Track: {track_name}",
        f"Best Lap: {format_laptime(report.best_lap)}",
        f"Avg Lap:  {format_laptime(report.avg_lap)}",
        f"Overall Balance: {report.balance_score:+.2f}  (-1=full understeer, +1=full oversteer)",
    ]
    if report.balance_entry != 0 or report.balance_mid != 0 or report.balance_exit != 0:
        telem_lines += [
            f"Entry balance (trail-brake): {report.balance_entry:+.2f}",
            f"Mid-corner balance (coast):  {report.balance_mid:+.2f}",
            f"Exit balance (power-on):     {report.balance_exit:+.2f}",
        ]
    if report.grip_utilization_pct > 0:
        telem_lines.append(
            f"Grip utilisation: {report.grip_utilization_pct:.0f}%  "
            f"(max lateral {report.max_lat_g:.1f}G, longitudinal {report.max_long_g:.1f}G)"
        )
    if report.avg_upshift_rpm_pct > 0:
        telem_lines.append(f"Avg upshift: {report.avg_upshift_rpm_pct:.0f}% of max RPM")
    if report.rev_limiter_pct > 0:
        telem_lines.append(f"Rev limiter: {report.rev_limiter_pct:.1f}% of session")
    telem_text = "\n".join(telem_lines)

    # Issues
    issues_text = ""
    for issue in report.issues:
        issues_text += (
            f"  [{issue.severity.value.upper()}] {issue.category.value} — "
            f"{issue.title}: {issue.description}\n"
        )
    if not issues_text:
        issues_text = "  No major issues detected.\n"

    # Tire temperatures
    tire_text = ""
    if report.tire_summary:
        for corner, temps in report.tire_summary.items():
            spread = temps['inner'] - temps['outer']
            tire_text += (
                f"  {corner}: inner={temps['inner']:.1f}°C  mid={temps['mid']:.1f}°C  "
                f"outer={temps['outer']:.1f}°C  avg={temps['avg']:.1f}°C  "
                f"spread(in-out)={spread:+.1f}°C\n"
            )

    # Suspension
    susp_text = ""
    if report.suspension_summary:
        for corner, s in report.suspension_summary.items():
            susp_text += (
                f"  {corner}: travel range={s['range']:.1f}mm  "
                f"bottoming={s['bottoming_pct']:.1f}%\n"
            )

    # Driving style
    style_text = ""
    if style_report:
        style_text = (
            f"Driving style (scores 0–100, higher=better):\n"
            f"  Overall {style_report.overall_score:.0f} | "
            f"Braking {style_report.brake_consistency:.0f} | "
            f"Throttle smoothness {style_report.throttle_smoothness:.0f} | "
            f"Steering smoothness {style_report.steering_smoothness:.0f}\n"
            f"  Trail braking: {style_report.trail_braking_pct:.1f}% of brake zones\n"
            f"  Coast (no input) time: {style_report.coast_time_pct:.1f}%\n"
            f"  Full throttle: {style_report.full_throttle_pct:.1f}%\n"
        )
        if style_report.balance_verdict:
            style_text += f"  Balance verdict: {style_report.balance_verdict}\n"
        if style_report.style_profile:
            style_text += f"  Driver profile: {style_report.style_profile}\n"
        if style_report.findings:
            style_text += "  Findings:\n"
            for f_ in style_report.findings[:5]:
                style_text += f"    • {f_}\n"

    # Sector / corner
    sector_text = ""
    if sector_report and getattr(sector_report, 'sectors', None):
        sector_text = "Sector times:\n"
        for i, s in enumerate(sector_report.sectors):
            if getattr(s, 'lap_times', None):
                sector_text += (
                    f"  S{i+1}: best={s.best_time:.3f}s  avg={s.avg_time:.3f}s  "
                    f"delta=+{s.avg_time - s.best_time:.3f}s\n"
                )
        tbl = getattr(sector_report, 'time_left_on_table', 0)
        ws  = getattr(sector_report, 'worst_sector', None)
        if tbl > 0:
            sector_text += f"  Time left on table: +{tbl:.3f}s  (worst: S{(ws or 0)+1})\n"

    corner_text = ""
    if corner_report is not None:
        try:
            from core.corner_analysis import format_corner_summary
            corner_text = "Corner analysis:\n" + format_corner_summary(corner_report)
        except Exception:
            pass

    # Stint / degradation
    stint_text = ""
    if stint_report:
        if getattr(stint_report, 'deg_rate', 0) > 0:
            stint_text = (
                f"Tire degradation: +{stint_report.deg_rate:.3f}s/lap"
            )
            if getattr(stint_report, 'optimal_stint_length', 0) > 0:
                stint_text += f"  (optimal stint: {stint_report.optimal_stint_length} laps)"
            stint_text += "\n"
        if getattr(stint_report, 'findings', None):
            stint_text += "Pressure findings: " + "; ".join(stint_report.findings[:3]) + "\n"

    # Current setup
    setup_text = ""
    if current_setup:
        lines = [
            f"  {_sanitize(str(k), 60)}: {_sanitize(str(v), 80)}"
            for k, v in list(current_setup.items())[:60]
        ]
        setup_text = "Current setup values:\n" + "\n".join(lines) + "\n"

    # Conditions
    cond_text = ""
    cond_parts = []
    if si.get('air_temp_c') is not None:
        cond_parts.append(f"Air {si['air_temp_c']:.1f}°C")
    if si.get('track_temp_c') is not None:
        cond_parts.append(f"Track {si['track_temp_c']:.1f}°C")
    if si.get('skies'):
        cond_parts.append(_sanitize(str(si['skies']), 30))
    if si.get('weather_type'):
        cond_parts.append(_sanitize(str(si['weather_type']), 30))
    if si.get('wind_speed_ms') is not None:
        cond_parts.append(f"Wind {si['wind_speed_ms']:.1f} m/s")
    if cond_parts:
        cond_text = "Conditions: " + ", ".join(cond_parts) + "\n"

    # Track character
    track_text = ""
    if track_info:
        track_text = (
            f"Track character: downforce demand={getattr(track_info,'downforce_demand','?')}, "
            f"tire stress={getattr(track_info,'tire_stress','?')}, "
            f"surface={getattr(track_info,'surface','?')}, "
            f"type={getattr(track_info,'track_type','?')}\n"
        )
        if getattr(track_info, 'notes', None):
            track_text += f"  Notes: {track_info.notes}\n"

    # ── Weather interpretation guidance ───────────────────────────────────
    weather_guidance = _weather_guidance(si)

    # ── Style hints section ────────────────────────────────────────────────
    hints_text = ""
    if style_hints:
        hints_text = "DRIVER-SPECIFIC SETUP IMPLICATIONS (from measured technique):\n"
        for h in style_hints:
            hints_text += f"  • {h}\n"

    # ── Stint mode context ─────────────────────────────────────────────────
    _STINT_GUIDANCE = {
        "qualifying": (
            "SESSION TYPE: QUALIFYING — optimise purely for maximum single-lap pace. "
            "Ignore tire wear and fuel weight. Prioritise peak grip, minimum drag, and "
            "the sharpest possible turn-in and exit traction. Fuel load = qualifying (minimal)."
        ),
        "endurance": (
            "SESSION TYPE: ENDURANCE RACE — balance lap time against tire longevity. "
            "Avoid aggressive camber or pressure settings that accelerate wear. "
            "Favour stability and predictability over outright speed. "
            "Account for a heavy fuel load at the start of each stint."
        ),
        "race": (
            "SESSION TYPE: SPRINT RACE — balance peak lap time with reasonable tire life "
            "for a full race stint. Account for a moderate starting fuel load."
        ),
    }
    stint_context = _STINT_GUIDANCE.get(stint_mode, _STINT_GUIDANCE["race"])

    # ── Assemble prompt ────────────────────────────────────────────────────
    trail_pct_str = (f"{style_report.trail_braking_pct:.0f}%"
                     if style_report else "unknown")

    prompt = f"""You are a professional iRacing setup engineer building a PERSONALISED, TECH-INSPECTION-PASSING setup.

{stint_context}

Your job is to START from the validated baseline below and ADJUST it to suit:
  1. The specific challenges of {track_name}
  2. This driver's measured technique and weaknesses
  3. The telemetry findings from their session

Every final value MUST fall within the legal parameter ranges. Do not invent values from scratch — adjust the baseline with specific, data-driven reasoning.

═══════════════════════════════════════════════════════
CAR CHARACTER — {car_name} ({car_class_str.upper()})
═══════════════════════════════════════════════════════
{car_profile}

═══════════════════════════════════════════════════════
VALIDATED BASELINE  (start here, adjust as needed)
═══════════════════════════════════════════════════════
{baseline_text}

═══════════════════════════════════════════════════════
TELEMETRY — what this driver's session shows
═══════════════════════════════════════════════════════
{telem_text}
{cond_text}{track_text}
{weather_guidance}DETECTED ISSUES:
{issues_text}
TIRE TEMPERATURES:
{tire_text if tire_text else "  No tire data.\n"}
SUSPENSION TRAVEL:
{susp_text if susp_text else "  No suspension data.\n"}
{style_text}
{sector_text}
{corner_text}
{stint_text}
{setup_text}
═══════════════════════════════════════════════════════
DRIVER TECHNIQUE → SETUP IMPLICATIONS
═══════════════════════════════════════════════════════
{hints_text if hints_text else "  No driving style data available.\n"}
═══════════════════════════════════════════════════════
LEGAL PARAMETER RANGES  (values outside these FAIL tech inspection)
═══════════════════════════════════════════════════════
{bounds_text}

═══════════════════════════════════════════════════════
YOUR DELIVERABLE
═══════════════════════════════════════════════════════
Structure your response in four sections:

**1. DIAGNOSIS** (3–5 bullets)
  Identify the primary performance deficits. Quote specific numbers
  (e.g. "entry understeer −0.42, RF inner 8°C hotter than outer").
  Distinguish setup issues from driver technique issues.

**2. TRACK-SPECIFIC REASONING**
  Explain which track challenges from the setup guidance above drive
  which parameter decisions. Reference specific corners by name.

**3. COMPLETE SETUP TABLE**
  Adjust the baseline values. Format as:

  PARAMETER              | VALUE        | CHANGED FROM BASELINE? | REASON
  -----------------------|--------------|------------------------|-------
  LF Camber              | -3.2 deg     | Yes (was -3.0)         | RF inner +8°C → reduce camber
  Brake Bias             | 54.0%        | Yes (was 55.0%)        | Entry understeer phase −0.42
  LF Cold Pressure       | 27.0 psi     | No                     | Within target range

  Include ALL parameters: camber ×4, toe (F/R), cold pressures ×4,
  springs ×4, ARBs (F/R), ride heights ×4, slow bump ×4, fast bump ×4,
  slow rebound ×4, fast rebound ×4, wing angles (F/R), brake bias,
  brake pressure, TC, ABS, diff (preload, power ramp, coast ramp).

**4. DRIVER STYLE NOTES**
  Explain 2–3 choices that are specifically adapted to this driver's
  measured technique (trail braking {trail_pct_str}, consistency scores, etc.).
  Tell the driver what they will feel differently and why it helps them.

Keep reasons on one line per parameter. Every value must be within the legal ranges."""

    # ── Stream from Claude ─────────────────────────────────────────────────
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key, timeout=90.0)

        chunks = _stream_with_retry(
            client, model="claude-sonnet-4-6", max_tokens=2500,
            messages=[{"role": "user", "content": prompt}],
        )
        for text in chunks:
            yield text

    except ImportError:
        yield "Anthropic package not installed. Run: pip install anthropic\n\n"
        yield _rule_based_recommendations(report, car_name, track_name)
    except Exception as exc:
        yield f"AI request failed ({exc}). Check your API key and internet connection.\n\n"
        yield _rule_based_recommendations(report, car_name, track_name)


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
