"""
Race Engineer Persona — "Steven"

Maintains a persistent DriverProfile that accumulates knowledge across
sessions. After MIN_SESSIONS_FOR_PERSONA sessions analyzed the AI advisor
switches to Steven mode: every recommendation is personalised to the driver's
known strengths, weaknesses, and setup preferences.

Profile is stored at ~/.iracing_engineer_profile.json and updated after
every session load via DriverProfileManager.update_from_session().
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Generator, Optional

logger = logging.getLogger(__name__)

PROFILE_PATH = os.path.expanduser("~/.iracing_engineer_profile.json")
MIN_SESSIONS_FOR_PERSONA = 3   # sessions before Alex activates


# ── EWA helper ────────────────────────────────────────────────────────────

def _ewa(old: float, new: float, alpha: float = 0.2) -> float:
    """Exponential weighted average. First observation: return new directly."""
    if old == 0.0:
        return new
    return alpha * new + (1.0 - alpha) * old


# ── Dataclasses ───────────────────────────────────────────────────────────

@dataclass
class WeaknessRecord:
    corner_type: str     # 'hairpin' | 'slow' | 'medium' | 'fast' | 'braking_zone' | 'exit'
    severity: float      # 0.0–1.0 rolling average severity
    occurrences: int     # how many sessions this appeared
    last_seen: str       # ISO date string


@dataclass
class SessionHistoryEntry:
    date: str
    car_name: str
    track_name: str
    best_lap: float
    avg_lap: float
    balance_score: float
    overall_style_score: float
    brake_consistency: float
    top_issue_titles: list         # up to 3 strings
    improvement_vs_avg: float      # seconds gained vs own historical avg on this combo
    deg_rate: float                # tire deg s/lap; 0 = unknown


@dataclass
class CarClassPreferences:
    car_class: str
    avg_balance_score: float       # typical session average
    preferred_brake_bias_offset: float   # signed delta from default
    tire_pressure_offset_psi: float
    note: str = ""


@dataclass
class DriverProfile:
    # Identity
    driver_name: str = "Driver"
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    last_updated: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    # Style traits (exponential weighted averages, α=0.20)
    overall_style_score: float = 0.0
    brake_consistency: float = 0.0
    throttle_smoothness: float = 0.0
    steering_smoothness: float = 0.0
    trail_braking_pct: float = 0.0
    coast_time_pct: float = 0.0

    # Balance tendencies (rolling EWA)
    avg_balance_score: float = 0.0
    balance_entry_avg: float = 0.0
    balance_mid_avg: float = 0.0
    balance_exit_avg: float = 0.0

    # Known weaknesses by corner type
    weaknesses: list = field(default_factory=list)   # list[WeaknessRecord]

    # Setup hints
    optimal_brake_bias_offset: float = 0.0
    preferred_tire_pressure_psi: float = 0.0

    # Per-car-class setup preferences
    setup_preferences: list = field(default_factory=list)  # list[CarClassPreferences]

    # History (newest-first, capped at 20)
    session_history: list = field(default_factory=list)    # list[SessionHistoryEntry]
    total_sessions_analyzed: int = 0
    persona_unlocked: bool = False


# ── Profile manager ───────────────────────────────────────────────────────

class DriverProfileManager:

    def load(self) -> DriverProfile:
        if not os.path.exists(PROFILE_PATH):
            return DriverProfile()
        try:
            with open(PROFILE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            profile = DriverProfile(**{
                k: v for k, v in data.items()
                if k in DriverProfile.__dataclass_fields__
            })
            # Reconstruct nested objects
            profile.weaknesses = [
                WeaknessRecord(**w) if isinstance(w, dict) else w
                for w in profile.weaknesses
            ]
            profile.session_history = [
                SessionHistoryEntry(**s) if isinstance(s, dict) else s
                for s in profile.session_history
            ]
            profile.setup_preferences = [
                CarClassPreferences(**p) if isinstance(p, dict) else p
                for p in profile.setup_preferences
            ]
            return profile
        except Exception as exc:
            logger.warning("Could not load driver profile: %s", exc)
            return DriverProfile()

    def save(self, profile: DriverProfile) -> None:
        try:
            profile.last_updated = datetime.utcnow().isoformat()
            tmp = PROFILE_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(asdict(profile), f, indent=2)
            os.replace(tmp, PROFILE_PATH)
        except Exception as exc:
            logger.warning("Could not save driver profile: %s", exc)

    def update_from_session(
        self,
        profile: DriverProfile,
        report,                    # AnalysisReport
        style_report=None,         # DriverStyleReport | None
        stint_report=None,         # TireDegReport | None
        corner_report=None,        # CornerAnalysisReport | None
        car_name: str = "",
        track_name: str = "",
        car_class: str = "default",
    ) -> DriverProfile:
        """
        Incorporate one session into the profile using EWA (α=0.20).
        Returns the mutated profile.
        """
        today = datetime.utcnow().date().isoformat()

        # ── 1. Style traits ───────────────────────────────────────────
        if style_report is not None:
            profile.overall_style_score    = _ewa(profile.overall_style_score,    style_report.overall_score)
            profile.brake_consistency      = _ewa(profile.brake_consistency,      style_report.brake_consistency)
            profile.throttle_smoothness    = _ewa(profile.throttle_smoothness,    style_report.throttle_smoothness)
            profile.steering_smoothness    = _ewa(profile.steering_smoothness,    getattr(style_report, "steering_smoothness", 0.0))
            profile.trail_braking_pct      = _ewa(profile.trail_braking_pct,      getattr(style_report, "trail_braking_pct", 0.0))
            profile.coast_time_pct         = _ewa(profile.coast_time_pct,         getattr(style_report, "coast_time_pct", 0.0))

        # ── 2. Balance ────────────────────────────────────────────────
        profile.avg_balance_score  = _ewa(profile.avg_balance_score,  report.balance_score)
        profile.balance_entry_avg  = _ewa(profile.balance_entry_avg,  getattr(report, "balance_entry", 0.0))
        profile.balance_mid_avg    = _ewa(profile.balance_mid_avg,    getattr(report, "balance_mid",   0.0))
        profile.balance_exit_avg   = _ewa(profile.balance_exit_avg,   getattr(report, "balance_exit",  0.0))

        # ── 3. Corner weaknesses ──────────────────────────────────────
        if corner_report is not None:
            session_weak: dict[str, float] = {}
            for c in getattr(corner_report, "corners", []):
                ctype = _classify_corner_type(c)
                # time_delta > 0.25s or consistency < 70 = weakness
                td = getattr(c, "time_delta", 0.0) or 0.0
                cs = getattr(c, "consistency_score", 100.0) or 100.0
                if td > 0.25 or cs < 70:
                    severity = min(1.0, td / 1.5 + (100 - cs) / 200)
                    session_weak[ctype] = max(session_weak.get(ctype, 0.0), severity)

            existing_types = {w.corner_type: w for w in profile.weaknesses}
            for ctype, sev in session_weak.items():
                if ctype in existing_types:
                    wr = existing_types[ctype]
                    wr.severity = _ewa(wr.severity, sev, alpha=0.3)
                    wr.occurrences += 1
                    wr.last_seen = today
                else:
                    profile.weaknesses.append(WeaknessRecord(
                        corner_type=ctype, severity=sev,
                        occurrences=1, last_seen=today,
                    ))
            # Sort by severity desc, keep top 8
            profile.weaknesses.sort(key=lambda w: w.severity, reverse=True)
            profile.weaknesses = profile.weaknesses[:8]

        # ── 4. Brake bias hint from entry balance ─────────────────────
        # Consistent understeer on entry (-) → driver needs more front brake bias
        # Consistent oversteer on entry (+) → driver needs less front brake bias
        if abs(profile.balance_entry_avg) > 0.1:
            # Map [-1, +1] oversteer range → [-1.0, +1.0] psi bias offset hint
            profile.optimal_brake_bias_offset = round(-profile.balance_entry_avg * 0.8, 2)

        # ── 5. Car class preferences ──────────────────────────────────
        prefs = {p.car_class: p for p in profile.setup_preferences}
        if car_class not in prefs:
            prefs[car_class] = CarClassPreferences(
                car_class=car_class,
                avg_balance_score=report.balance_score,
                preferred_brake_bias_offset=profile.optimal_brake_bias_offset,
                tire_pressure_offset_psi=0.0,
            )
        else:
            p = prefs[car_class]
            p.avg_balance_score = _ewa(p.avg_balance_score, report.balance_score)
            p.preferred_brake_bias_offset = _ewa(
                p.preferred_brake_bias_offset, profile.optimal_brake_bias_offset
            )
            # Tire pressure offset from stint findings
            if stint_report and hasattr(stint_report, "pressure_hot_actuals"):
                from core.car_classifier import classify_car, PRESSURE_TARGETS
                try:
                    targets = PRESSURE_TARGETS.get(classify_car(car_name), {})
                    if targets:
                        hot_avg = sum(stint_report.pressure_hot_actuals.values()) / max(1, len(stint_report.pressure_hot_actuals))
                        tgt_avg = sum(targets.values()) / max(1, len(targets))
                        p.tire_pressure_offset_psi = _ewa(p.tire_pressure_offset_psi, hot_avg - tgt_avg)
                except Exception:
                    pass
        profile.setup_preferences = list(prefs.values())

        # ── 6. Session history ────────────────────────────────────────
        deg = getattr(stint_report, "deg_rate", 0.0) if stint_report else 0.0
        improvement = _compute_improvement(profile, car_name, track_name, report.best_lap)
        entry = SessionHistoryEntry(
            date=today,
            car_name=car_name,
            track_name=track_name,
            best_lap=report.best_lap,
            avg_lap=report.avg_lap,
            balance_score=report.balance_score,
            overall_style_score=profile.overall_style_score,
            brake_consistency=profile.brake_consistency,
            top_issue_titles=[i.title for i in report.issues[:3]] if report.issues else [],
            improvement_vs_avg=improvement,
            deg_rate=deg or 0.0,
        )
        profile.session_history.insert(0, entry)
        profile.session_history = profile.session_history[:20]

        # ── 7. Counters & unlock ──────────────────────────────────────
        profile.total_sessions_analyzed += 1
        if profile.total_sessions_analyzed >= MIN_SESSIONS_FOR_PERSONA:
            profile.persona_unlocked = True

        return profile


def _classify_corner_type(corner) -> str:
    """Bucket corner by min speed into a human-readable type."""
    spd = getattr(corner, "min_speed_ms", None) or getattr(corner, "apex_speed_ms", 50.0)
    if spd < 30:
        return "hairpin"
    if spd < 55:
        return "slow_corner"
    if spd < 85:
        return "medium_corner"
    return "fast_corner"


def _compute_improvement(profile: DriverProfile, car: str,
                          track: str, best_lap: float) -> float:
    """Return seconds gained vs own historical avg for this car+track. 0 if no history."""
    relevant = [
        s.best_lap for s in profile.session_history
        if s.car_name == car and s.track_name == track and s.best_lap > 0
    ]
    if not relevant:
        return 0.0
    hist_avg = sum(relevant) / len(relevant)
    return round(hist_avg - best_lap, 3)  # positive = improvement


# ── Race Engineer AI wrapper ──────────────────────────────────────────────

class RaceEngineer:
    """
    Wraps AI advisor calls with Steven's persistent persona and driver profile.
    Activates when profile.total_sessions_analyzed >= MIN_SESSIONS_FOR_PERSONA.
    """

    PERSONA_NAME = "Steven"

    _SYSTEM_PROMPT = (
        "You are Steven, a professional race engineer with 15 years of iRacing experience. "
        "You have analysed this driver's telemetry across multiple sessions and know their "
        "specific tendencies intimately. You speak directly and practically — like a real "
        "engineer on team radio or in a post-session debrief. "
        "Every recommendation you give references specific data from this driver's history "
        "and current session numbers. You never give generic textbook advice. "
        "When you spot a recurring pattern (e.g. 'you consistently struggle at hairpin exits') "
        "you name it explicitly and explain *why* it keeps happening. "
        "Your goal is measurable lap time improvement, not reassurance."
    )

    def __init__(self, profile: DriverProfile):
        self.profile = profile

    def build_system_context(self) -> str:
        """
        Build a concise driver profile summary (<400 tokens) for the system prompt.
        """
        p = self.profile
        lines = [
            f"\n=== DRIVER PROFILE ({p.driver_name}) — {p.total_sessions_analyzed} sessions analysed ===",
        ]

        # Style summary
        if p.overall_style_score > 0:
            lines.append(
                f"Style scores (0–100): Overall {p.overall_style_score:.0f}  "
                f"Braking {p.brake_consistency:.0f}  Throttle {p.throttle_smoothness:.0f}  "
                f"Steering {p.steering_smoothness:.0f}"
            )
            if p.trail_braking_pct > 0:
                lines.append(f"Trail braking: {p.trail_braking_pct:.1f}% of zones  "
                             f"Coast time: {p.coast_time_pct:.1f}%")

        # Balance tendency
        bal_word = ("understeer" if p.avg_balance_score < -0.1
                    else "oversteer" if p.avg_balance_score > 0.1 else "neutral")
        lines.append(
            f"Typical balance: {bal_word} ({p.avg_balance_score:+.2f})  "
            f"Entry {p.balance_entry_avg:+.2f}  Mid {p.balance_mid_avg:+.2f}  "
            f"Exit {p.balance_exit_avg:+.2f}"
        )

        # Weaknesses
        sig_weak = [w for w in p.weaknesses if w.occurrences >= 2]
        if sig_weak:
            lines.append("Recurring weaknesses:")
            for w in sig_weak[:4]:
                lines.append(
                    f"  {w.corner_type}: severity {w.severity:.0%}, "
                    f"seen in {w.occurrences} sessions, last {w.last_seen}"
                )

        # Setup hints
        if abs(p.optimal_brake_bias_offset) > 0.05:
            direction = "more front" if p.optimal_brake_bias_offset > 0 else "less front"
            lines.append(f"Setup hint: driver typically benefits from {direction} brake bias "
                         f"({p.optimal_brake_bias_offset:+.2f}% offset from default)")

        # Car class prefs
        if p.setup_preferences:
            lines.append("Car class preferences:")
            for pref in p.setup_preferences[:3]:
                bal = "US" if pref.avg_balance_score < -0.1 else "OS" if pref.avg_balance_score > 0.1 else "neutral"
                lines.append(f"  {pref.car_class}: typically {bal}, "
                             f"bias offset {pref.preferred_brake_bias_offset:+.2f}%")

        # Last 3 sessions snapshot
        if p.session_history:
            lines.append("Recent sessions:")
            for s in p.session_history[:3]:
                imp = (f"  ↑{s.improvement_vs_avg:.3f}s" if s.improvement_vs_avg > 0.01
                       else f"  ↓{-s.improvement_vs_avg:.3f}s" if s.improvement_vs_avg < -0.01
                       else "")
                lines.append(
                    f"  {s.date} | {s.car_name[:20]} @ {s.track_name[:20]} | "
                    f"best {s.best_lap:.3f}s{imp}"
                )

        lines.append("=== END DRIVER PROFILE ===\n")
        return "\n".join(lines)

    # ── Drop-in replacement for get_ai_recommendations_stream ─────────────

    def get_recommendations_stream(
        self,
        report,
        car_name: str,
        track_name: str,
        api_key: str,
        setup_data=None,
        sector_report=None,
        style_report=None,
        stint_report=None,
        best_report=None,
        session_info=None,
        corner_report=None,
        incident_report=None,
        evolution_report=None,
        model: str = "claude-haiku-4-5-20251001",
    ) -> Generator[str, None, None]:
        if not api_key or not api_key.strip():
            yield "Set your Anthropic API key in Settings (⚙) to get Steven's analysis."
            return
        try:
            import anthropic
            from core.ai_advisor import _build_prompt
            client = anthropic.Anthropic(api_key=api_key, timeout=90.0)
            system = self._SYSTEM_PROMPT + self.build_system_context()
            user_prompt = _build_prompt(
                report, car_name, track_name, setup_data,
                sector_report, style_report, stint_report, best_report,
                session_info, corner_report, incident_report, evolution_report,
            )
            # Replace generic opener with personalised directive
            personalised_prompt = (
                f"[Steven mode — {self.profile.total_sessions_analyzed} sessions in profile]\n\n"
                + user_prompt
            )
            with client.messages.stream(
                model=model,
                max_tokens=1200,
                system=system,
                messages=[{"role": "user", "content": personalised_prompt}],
            ) as stream:
                for text in stream.text_stream:
                    yield text
        except ImportError:
            yield "Install the 'anthropic' package to use the AI advisor."
        except Exception as exc:
            logger.exception("RaceEngineer stream error")
            yield f"\n[Error: {exc}]"

    # ── Drop-in replacement for ask_setup_question_stream ─────────────────

    def ask_question_stream(
        self,
        question: str,
        report,
        car_name: str,
        track_name: str,
        api_key: str,
        setup_data=None,
        sector_report=None,
        session_info=None,
        model: str = "claude-haiku-4-5-20251001",
    ) -> Generator[str, None, None]:
        if not api_key or not api_key.strip():
            yield "Set your Anthropic API key in Settings (⚙)."
            return
        try:
            import anthropic
            from core.ai_advisor import _build_prompt, _sanitize
            client = anthropic.Anthropic(api_key=api_key, timeout=60.0)
            system = self._SYSTEM_PROMPT + self.build_system_context()
            context = _build_prompt(
                report, car_name, track_name, setup_data,
                sector_report, None, None, None, session_info,
            )
            user_msg = (
                f"[Steven mode — {self.profile.total_sessions_analyzed} sessions in profile]\n\n"
                f"Current session context:\n{context}\n\n"
                f"Driver's question: {_sanitize(question, 400)}"
            )
            with client.messages.stream(
                model=model,
                max_tokens=600,
                system=system,
                messages=[{"role": "user", "content": user_msg}],
            ) as stream:
                for text in stream.text_stream:
                    yield text
        except Exception as exc:
            logger.exception("RaceEngineer Q&A error")
            yield f"\n[Error: {exc}]"

    # ── Session evolution summary ─────────────────────────────────────────

    def generate_evolution_summary(
        self,
        car_name: str,
        track_name: str,
        api_key: str,
        model: str = "claude-haiku-4-5-20251001",
    ) -> Generator[str, None, None]:
        """
        Compare the driver's most recent session at car+track against their
        historical average there and stream a personalised evolution summary.
        Requires at least 2 sessions at the same venue in the profile history.
        """
        if not api_key or not api_key.strip():
            yield "Set your Anthropic API key in Settings (⚙)."
            return

        # Filter history to matching car+track (fuzzy: case-insensitive contains)
        cn_low = car_name.lower()
        tn_low = track_name.lower()
        matching = [
            s for s in self.profile.session_history
            if cn_low in s.car_name.lower() and tn_low in s.track_name.lower()
        ]

        if len(matching) < 2:
            yield (
                f"Not enough history yet for {car_name} at {track_name}. "
                f"Steven needs at least 2 sessions at this venue to generate an evolution report. "
                f"({len(matching)} session{'s' if len(matching) != 1 else ''} found)"
            )
            return

        latest = matching[0]          # newest-first order
        previous = matching[1:]

        avg_best = sum(s.best_lap for s in previous) / len(previous)
        avg_style = sum(s.overall_style_score for s in previous) / len(previous)
        avg_balance = sum(s.balance_score for s in previous) / len(previous)
        avg_brake = sum(s.brake_consistency for s in previous) / len(previous)

        delta_best = latest.best_lap - avg_best
        delta_style = latest.overall_style_score - avg_style
        delta_balance = latest.balance_score - avg_balance
        delta_brake = latest.brake_consistency - avg_brake

        from core.analysis_engine import format_laptime

        context = (
            f"[Steven evolution report — {car_name} @ {track_name}]\n\n"
            f"Sessions analysed: {len(matching)} (most recent vs {len(previous)} prior)\n\n"
            f"LATEST SESSION ({latest.date}):\n"
            f"  Best lap:       {format_laptime(latest.best_lap)}\n"
            f"  Style score:    {latest.overall_style_score:.1f}/100\n"
            f"  Balance score:  {latest.balance_score:.1f}\n"
            f"  Brake consist.: {latest.brake_consistency:.1f}/100\n"
            f"  Key issues:     {', '.join(latest.top_issue_titles[:3]) or 'none'}\n\n"
            f"HISTORICAL AVERAGE AT THIS VENUE ({len(previous)} sessions):\n"
            f"  Avg best lap:   {format_laptime(avg_best)}\n"
            f"  Avg style:      {avg_style:.1f}/100\n"
            f"  Avg balance:    {avg_balance:.1f}\n"
            f"  Avg brake:      {avg_brake:.1f}/100\n\n"
            f"DELTAS (positive = improvement):\n"
            f"  Lap time:  {-delta_best:+.3f}s  ({'faster' if delta_best < 0 else 'slower'})\n"
            f"  Style:     {delta_style:+.1f}\n"
            f"  Balance:   {delta_balance:+.1f}\n"
            f"  Braking:   {delta_brake:+.1f}\n\n"
            f"Driver profile context:\n{self.build_system_context()}"
        )

        prompt = (
            f"Based on this data, write a concise (~150 word) evolution debrief for the driver. "
            f"Name specific numbers. Highlight 1-2 genuine improvements and 1-2 areas still needing work. "
            f"Be direct — this is a real driver trying to get faster."
        )

        try:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key, timeout=60.0)
            with client.messages.stream(
                model=model,
                max_tokens=400,
                system=self._SYSTEM_PROMPT,
                messages=[{"role": "user", "content": context + "\n\n" + prompt}],
            ) as stream:
                for text in stream.text_stream:
                    yield text
        except Exception as exc:
            logger.exception("Evolution summary error")
            yield f"\n[Error: {exc}]"
