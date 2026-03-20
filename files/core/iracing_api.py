"""
iRacing Data API client.

Auth flow:
  1. Hash password: base64(SHA-256(password + email.lower()))
  2. POST https://members-ng.iracing.com/auth → sets authtoken_members cookie
  3. GET /data/<endpoint> → {"link": "<S3 pre-signed URL>"}
  4. GET that S3 URL → actual JSON payload

Rate limit: ~240 req/min. We enforce 250ms minimum inter-request gap.
Lap times are in tenths-of-milliseconds; divide by 10_000 for seconds.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Optional

import requests

logger = logging.getLogger(__name__)

_AUTH_URL = "https://members-ng.iracing.com/auth"
_BASE_URL = "https://members-ng.iracing.com/data"
_RATE_MIN_S = 0.25          # 240 req/min safety margin
_SESSION_TIMEOUT = 30       # seconds per request


# ── Data classes ──────────────────────────────────────────────────────────

@dataclass
class MemberSummary:
    cust_id: int
    display_name: str
    irating: int              # Road category by default
    license_level: int        # 1–20 maps to D4→A1
    safety_rating: float
    club_name: str
    member_since: str


@dataclass
class RaceResult:
    subsession_id: int
    series_name: str
    track_name: str
    car_name: str
    finish_pos: int
    start_pos: int
    incidents: int
    laps_completed: int
    best_lap_time: float      # seconds; -1 if no valid lap
    irating_change: int
    sr_change: float
    session_start_time: str   # ISO-8601


@dataclass
class BestLap:
    track_id: int
    track_name: str
    car_id: int
    car_name: str
    best_lap_time: float      # seconds
    subsession_id: int


@dataclass
class LapData:
    lap_number: int
    lap_time: float           # seconds; -1 if invalid
    incident_count: int
    flags: int


@dataclass
class CareerStats:
    category_name: str
    starts: int
    wins: int
    top5: int
    poles: int
    avg_start: float
    avg_finish: float
    avg_incidents: float
    win_pct: float
    top5_pct: float
    laps_led: int
    total_laps: int


@dataclass
class YearlyStat:
    year: int
    category_name: str
    starts: int
    wins: int
    top5: int
    poles: int
    avg_finish: float
    avg_incidents: float
    irating_change: int       # net iRating change across the year
    total_laps: int


@dataclass
class UpcomingRace:
    series_name: str
    track_name: str
    config_name: str
    session_start_utc: str    # ISO-8601
    registered: int
    field_size: int
    license_min: str
    series_id: int


@dataclass
class EventLogEntry:
    lap: int
    event_type: str
    description: str
    car_number: str


@dataclass
class APIConnectionStatus:
    authenticated: bool = False
    error_message: str = ""
    cust_id: int = 0
    display_name: str = ""
    last_auth_time: float = 0.0


# ── Client ────────────────────────────────────────────────────────────────

class IRacingAPIClient:
    """
    Thread-safe iRacing Data API client.
    All network calls are blocking — invoke from a background thread.
    """

    def __init__(self):
        self._session = requests.Session()
        self._session.headers["User-Agent"] = "OptimalSector/3.x"
        self._status = APIConnectionStatus()
        self._lock = threading.Lock()
        self._rate_last: float = 0.0
        # Caches populated once per session
        self._cars_cache: list[dict] = []
        self._tracks_cache: list[dict] = []

    # ── Credentials ───────────────────────────────────────────────────────

    @staticmethod
    def save_credentials(email: str, password: str) -> None:
        from core.config import set_iracing_credentials
        set_iracing_credentials(email, password)

    @staticmethod
    def load_credentials() -> tuple[str, str]:
        from core.config import get_iracing_credentials
        return get_iracing_credentials()

    @staticmethod
    def clear_credentials() -> None:
        from core.config import clear_iracing_credentials
        clear_iracing_credentials()

    # ── Auth ──────────────────────────────────────────────────────────────

    def authenticate(self, email: str, password: str) -> APIConnectionStatus:
        """Authenticate with iRacing SSO. Thread-safe."""
        with self._lock:
            hashed = self._hash_password(password, email)
            try:
                # Warm up the session — members-ng requires a prior GET to set
                # session cookies before the auth POST is accepted (anti-bot measure)
                try:
                    self._session.get(
                        "https://members-ng.iracing.com/",
                        timeout=_SESSION_TIMEOUT,
                    )
                except Exception:
                    pass  # non-fatal; attempt auth anyway

                resp = self._session.post(
                    _AUTH_URL,
                    json={"email": email, "password": hashed},
                    headers={"Content-Type": "application/json",
                             "Referer": "https://members-ng.iracing.com/"},
                    timeout=_SESSION_TIMEOUT,
                )
                if resp.status_code == 429:
                    self._status = APIConnectionStatus(
                        authenticated=False,
                        error_message="Rate limited by iRacing — wait 60s and try again"
                    )
                    return self._status
                if resp.status_code != 200:
                    try:
                        body = resp.json()
                        msg = body.get("message", body.get("error", ""))
                    except Exception:
                        msg = resp.text[:120] if resp.text else ""
                    detail = f": {msg}" if msg else ""
                    self._status = APIConnectionStatus(
                        authenticated=False,
                        error_message=f"Auth failed ({resp.status_code}){detail}"
                    )
                    return self._status

                data = resp.json()
                if data.get("authcode", 0) == 0:
                    # authcode=0 means failure; message field has details
                    msg = data.get("message", "Authentication failed")
                    self._status = APIConnectionStatus(
                        authenticated=False,
                        error_message=msg,
                    )
                    return self._status

                # Fetch cust_id from /data/member/info
                info = self._get_data("/member/info")
                cust_id = info.get("cust_id", 0)
                display_name = info.get("display_name", email.split("@")[0])

                self._status = APIConnectionStatus(
                    authenticated=True,
                    cust_id=cust_id,
                    display_name=display_name,
                    last_auth_time=time.monotonic(),
                )
                logger.info("iRacing auth OK: %s (cust_id=%d)", display_name, cust_id)
                return self._status

            except requests.RequestException as exc:
                self._status = APIConnectionStatus(
                    authenticated=False,
                    error_message=f"Network error: {exc}"
                )
                return self._status

    @staticmethod
    def _hash_password(password: str, email: str) -> str:
        combined = (password + email.lower()).encode("utf-8")
        return base64.b64encode(hashlib.sha256(combined).digest()).decode("utf-8")

    def is_authenticated(self) -> bool:
        return self._status.authenticated

    def get_status(self) -> APIConnectionStatus:
        return self._status

    # ── Core request helper ───────────────────────────────────────────────

    def _rate_limit(self) -> None:
        elapsed = time.monotonic() - self._rate_last
        if elapsed < _RATE_MIN_S:
            time.sleep(_RATE_MIN_S - elapsed)
        self._rate_last = time.monotonic()

    def _get_data(self, endpoint: str, params: Optional[dict] = None) -> dict | list:
        """
        GET endpoint, follow S3 redirect link if present.
        Raises RuntimeError on auth/HTTP failure.
        """
        self._rate_limit()
        url = _BASE_URL + endpoint
        resp = self._session.get(url, params=params, timeout=_SESSION_TIMEOUT)

        if resp.status_code == 401:
            self._status.authenticated = False
            raise RuntimeError("iRacing session expired — please re-authenticate")
        if resp.status_code == 429:
            raise RuntimeError("iRacing API rate limit reached — wait and retry")
        if not resp.ok:
            raise RuntimeError(f"iRacing API error {resp.status_code}: {endpoint}")

        data = resp.json()

        # Most endpoints return {"link": "<S3 URL>"} — follow it
        if isinstance(data, dict) and "link" in data:
            self._rate_limit()
            s3_resp = requests.get(data["link"], timeout=_SESSION_TIMEOUT)
            s3_resp.raise_for_status()
            return s3_resp.json()

        return data

    # ── Member info ───────────────────────────────────────────────────────

    def get_member_summary(self, cust_id: Optional[int] = None) -> MemberSummary:
        cid = cust_id or self._status.cust_id
        data = self._get_data("/member/profile", {"cust_id": cid})

        member = data.get("member", data)
        licenses = member.get("licenses", [])
        # Category 2 = Road; fall back to first available
        road_lic = next(
            (l for l in licenses if l.get("category_id") == 2),
            licenses[0] if licenses else {}
        )

        return MemberSummary(
            cust_id=member.get("cust_id", cid),
            display_name=member.get("display_name", ""),
            irating=road_lic.get("irating", 1350),
            license_level=road_lic.get("license_level", 1),
            safety_rating=road_lic.get("safety_rating", 0.0),
            club_name=member.get("club_name", ""),
            member_since=member.get("member_since", ""),
        )

    def get_irating_history(self, cust_id: Optional[int] = None,
                             category_id: int = 2) -> list[dict]:
        """Return [{"timestamp": str, "value": int}, ...] sorted oldest-first."""
        cid = cust_id or self._status.cust_id
        data = self._get_data("/member/chart_data", {
            "cust_id": cid, "category_id": category_id, "chart_type": 1
        })
        return sorted(data.get("data", []), key=lambda x: x.get("timestamp", ""))

    def get_sr_history(self, cust_id: Optional[int] = None,
                        category_id: int = 2) -> list[dict]:
        """Return [{"timestamp": str, "value": float}, ...] sorted oldest-first."""
        cid = cust_id or self._status.cust_id
        data = self._get_data("/member/chart_data", {
            "cust_id": cid, "category_id": category_id, "chart_type": 2
        })
        return sorted(data.get("data", []), key=lambda x: x.get("timestamp", ""))

    # ── Race results ──────────────────────────────────────────────────────

    def get_recent_results(self, cust_id: Optional[int] = None,
                            limit: int = 25) -> list[RaceResult]:
        """Fetch last *limit* race results (road + sports car categories)."""
        cid = cust_id or self._status.cust_id
        try:
            data = self._get_data("/stats/member_recent_races", {"cust_id": cid})
        except RuntimeError:
            return []

        races = data.get("races", [])[:limit]
        results: list[RaceResult] = []
        for r in races:
            track = r.get("track", {})
            best_raw = r.get("best_lap_time", -1)
            best_s = _tmstoms(best_raw) if best_raw and best_raw > 0 else -1.0

            new_ir = r.get("newi_rating", 0)
            old_ir = r.get("oldi_rating", 0)
            new_sr = r.get("new_cpi", 0.0)   # CPI = Safety Rating composite
            old_sr = r.get("old_cpi", 0.0)

            results.append(RaceResult(
                subsession_id=r.get("subsession_id", 0),
                series_name=r.get("series_name", ""),
                track_name=track.get("track_name", ""),
                car_name=r.get("car_name", ""),
                finish_pos=r.get("finish_position_in_class", 0) + 1,
                start_pos=r.get("starting_position_in_class", 0) + 1,
                incidents=r.get("incidents", 0),
                laps_completed=r.get("laps_complete", 0),
                best_lap_time=best_s,
                irating_change=new_ir - old_ir,
                sr_change=round(new_sr - old_sr, 2),
                session_start_time=r.get("start_time", ""),
            ))
        return results

    def get_subsession_laps(self, subsession_id: int,
                             cust_id: Optional[int] = None) -> list[LapData]:
        """Fetch individual lap data for one subsession."""
        cid = cust_id or self._status.cust_id
        try:
            data = self._get_data("/results/lap_data", {
                "subsession_id": subsession_id,
                "simsession_number": 0,
                "cust_id": cid,
            })
        except RuntimeError:
            return []

        laps: list[LapData] = []
        for chunk in data.get("chunk_info", {}).get("chunk_file_names", []):
            # Chunks are additional S3 files with lap arrays
            try:
                self._rate_limit()
                chunk_data = requests.get(chunk, timeout=_SESSION_TIMEOUT).json()
                for lap in chunk_data:
                    raw_time = lap.get("lap_time", -1)
                    laps.append(LapData(
                        lap_number=lap.get("lap_number", 0),
                        lap_time=_tmstoms(raw_time) if raw_time > 0 else -1.0,
                        incident_count=lap.get("incident_count", 0),
                        flags=lap.get("flags", 0),
                    ))
            except Exception:
                pass

        # Fallback: laps might be inline
        if not laps:
            for lap in data.get("laps", []):
                raw_time = lap.get("lap_time", -1)
                laps.append(LapData(
                    lap_number=lap.get("lap_number", 0),
                    lap_time=_tmstoms(raw_time) if raw_time > 0 else -1.0,
                    incident_count=lap.get("incident_count", 0),
                    flags=lap.get("flags", 0),
                ))
        return laps

    # ── Car / Track lookup ────────────────────────────────────────────────

    def get_cars(self) -> list[dict]:
        if not self._cars_cache:
            try:
                self._cars_cache = self._get_data("/car/get") or []
            except RuntimeError:
                pass
        return self._cars_cache

    def get_tracks(self) -> list[dict]:
        if not self._tracks_cache:
            try:
                data = self._get_data("/track/get")
                self._tracks_cache = data if isinstance(data, list) else data.get("tracks", [])
            except RuntimeError:
                pass
        return self._tracks_cache

    def lookup_car_name(self, car_id: int) -> str:
        for c in self.get_cars():
            if c.get("car_id") == car_id:
                return c.get("car_name", str(car_id))
        return str(car_id)

    def lookup_track_name(self, track_id: int) -> str:
        for t in self.get_tracks():
            if t.get("track_id") == track_id:
                name = t.get("track_name", "")
                config = t.get("config_name", "")
                return f"{name} — {config}" if config else name
        return str(track_id)

    def get_best_laps(self, cust_id: Optional[int] = None) -> list[BestLap]:
        """Return personal best laps per car per track combination."""
        cid = cust_id or self._status.cust_id
        try:
            data = self._get_data("/stats/member_bests", {"cust_id": cid})
        except RuntimeError:
            return []

        bests: list[BestLap] = []
        for car_entry in data.get("cars_driven", []):
            car_id = car_entry.get("car_id", 0)
            car_name = self.lookup_car_name(car_id)
            for b in car_entry.get("bests", []):
                raw = b.get("best_lap_time", -1)
                bests.append(BestLap(
                    track_id=b.get("track_id", 0),
                    track_name=self.lookup_track_name(b.get("track_id", 0)),
                    car_id=car_id,
                    car_name=car_name,
                    best_lap_time=_tmstoms(raw) if raw and raw > 0 else -1.0,
                    subsession_id=b.get("subsession_id", 0),
                ))
        # Sort by car name, then track name
        bests.sort(key=lambda x: (x.car_name, x.track_name))
        return bests

    # ── Career & yearly stats ─────────────────────────────────────────────

    def get_career_stats(self, cust_id: Optional[int] = None) -> list[CareerStats]:
        """Return career statistics broken down by category (Road, Oval, Dirt…)."""
        cid = cust_id or self._status.cust_id
        try:
            data = self._get_data("/stats/member_career", {"cust_id": cid})
        except RuntimeError:
            return []

        stats: list[CareerStats] = []
        for s in data.get("stats", []):
            starts = s.get("starts", 0) or 0
            wins   = s.get("wins", 0) or 0
            top5   = s.get("top5", 0) or 0
            stats.append(CareerStats(
                category_name=s.get("category", "Unknown"),
                starts=starts,
                wins=wins,
                top5=top5,
                poles=s.get("poles", 0) or 0,
                avg_start=s.get("avg_start_position", 0.0) or 0.0,
                avg_finish=s.get("avg_finish_position", 0.0) or 0.0,
                avg_incidents=s.get("avg_incidents", 0.0) or 0.0,
                win_pct=wins / starts * 100 if starts else 0.0,
                top5_pct=top5 / starts * 100 if starts else 0.0,
                laps_led=s.get("laps_led", 0) or 0,
                total_laps=s.get("laps", 0) or 0,
            ))
        return stats

    def get_yearly_stats(self, cust_id: Optional[int] = None) -> list[YearlyStat]:
        """Return per-year statistics across all categories, newest first."""
        cid = cust_id or self._status.cust_id
        try:
            data = self._get_data("/stats/member_yearly", {"cust_id": cid})
        except RuntimeError:
            return []

        yearly: list[YearlyStat] = []
        for s in data.get("stats", []):
            starts = s.get("starts", 0) or 0
            ir_change = (s.get("irating", 0) or 0) - (s.get("old_irating", 0) or 0)
            yearly.append(YearlyStat(
                year=s.get("year", 0),
                category_name=s.get("category", "Unknown"),
                starts=starts,
                wins=s.get("wins", 0) or 0,
                top5=s.get("top5", 0) or 0,
                poles=s.get("poles", 0) or 0,
                avg_finish=s.get("avg_finish_position", 0.0) or 0.0,
                avg_incidents=s.get("avg_incidents", 0.0) or 0.0,
                irating_change=ir_change,
                total_laps=s.get("laps", 0) or 0,
            ))
        # Sort newest year first
        yearly.sort(key=lambda x: x.year, reverse=True)
        return yearly

    # ── Race schedule ─────────────────────────────────────────────────────

    def get_upcoming_races(self) -> list[UpcomingRace]:
        """
        Fetch upcoming official race sessions from the iRacing race guide.
        Returns sessions sorted by start time (soonest first).
        """
        try:
            data = self._get_data("/season/race_guide")
        except RuntimeError:
            return []

        sessions: list[UpcomingRace] = []
        for s in data.get("sessions", []):
            track = s.get("track", {})
            license_group = s.get("license_group_types", [{}])
            lic = license_group[0].get("license_group_type", "") if license_group else ""
            sessions.append(UpcomingRace(
                series_name=s.get("series_name", ""),
                track_name=track.get("track_name", ""),
                config_name=track.get("config_name", ""),
                session_start_utc=s.get("start_time", ""),
                registered=s.get("entry_count", 0) or 0,
                field_size=s.get("max_entrants", 0) or 0,
                license_min=lic,
                series_id=s.get("series_id", 0) or 0,
            ))
        sessions.sort(key=lambda x: x.session_start_utc)
        return sessions[:50]   # cap at 50 entries

    # ── Subsession drill-down ─────────────────────────────────────────────

    def get_subsession_detail(self, subsession_id: int) -> dict:
        """Full subsession result JSON (contains car list, weather, results grid)."""
        try:
            return self._get_data("/results/get", {"subsession_id": subsession_id})
        except RuntimeError:
            return {}

    def get_lap_chart(self, subsession_id: int,
                       cust_id: Optional[int] = None) -> list[dict]:
        """
        Per-lap position data for a subsession.
        Returns [{"lap": int, "lap_position": int, "lap_time": float,
                  "lap_events": int}, ...]  for the authenticated user.
        """
        cid = cust_id or self._status.cust_id
        try:
            data = self._get_data("/results/lap_chart_data", {
                "subsession_id": subsession_id,
                "simsession_number": 0,
            })
        except RuntimeError:
            return []

        laps: list[dict] = []
        # API may return chunk files or inline data
        chunk_names = data.get("chunk_info", {}).get("chunk_file_names", [])
        base_url = data.get("chunk_info", {}).get("base_download_url", "")
        raw_laps = data.get("laps", [])

        if chunk_names and base_url:
            for chunk_name in chunk_names:
                try:
                    self._rate_limit()
                    url = base_url + chunk_name
                    chunk = requests.get(url, timeout=_SESSION_TIMEOUT).json()
                    for entry in chunk:
                        if entry.get("cust_id") == cid:
                            laps.append({
                                "lap": entry.get("lap_number", 0),
                                "lap_position": entry.get("lap_position", 0),
                                "lap_time": _tmstoms(entry.get("lap_time", -1)),
                                "lap_events": entry.get("lap_events", 0),
                            })
                except Exception:
                    pass
        else:
            for entry in raw_laps:
                if entry.get("cust_id") == cid:
                    laps.append({
                        "lap": entry.get("lap_number", 0),
                        "lap_position": entry.get("lap_position", 0),
                        "lap_time": _tmstoms(entry.get("lap_time", -1)),
                        "lap_events": entry.get("lap_events", 0),
                    })

        laps.sort(key=lambda x: x["lap"])
        return laps

    def get_event_log(self, subsession_id: int) -> list[EventLogEntry]:
        """
        Incident and event log for a subsession.
        """
        try:
            data = self._get_data("/results/event_log", {
                "subsession_id": subsession_id,
                "simsession_number": 0,
            })
        except RuntimeError:
            return []

        entries: list[EventLogEntry] = []
        chunk_names = data.get("chunk_info", {}).get("chunk_file_names", [])
        base_url = data.get("chunk_info", {}).get("base_download_url", "")

        raw = data.get("events", [])
        if chunk_names and base_url:
            for chunk_name in chunk_names:
                try:
                    self._rate_limit()
                    url = base_url + chunk_name
                    chunk = requests.get(url, timeout=_SESSION_TIMEOUT).json()
                    raw.extend(chunk)
                except Exception:
                    pass

        for e in raw:
            entries.append(EventLogEntry(
                lap=e.get("lap_num", 0) or 0,
                event_type=e.get("type", ""),
                description=e.get("message", e.get("description", "")),
                car_number=str(e.get("car_number", "")),
            ))
        return entries

    # ── IBT correlation ───────────────────────────────────────────────────

    def correlate_with_ibt(
        self,
        results: list[RaceResult],
        sessions: list,          # list of (TelemetryData, AnalysisReport)
    ) -> list[tuple[RaceResult, Optional[int]]]:
        """
        Match API results to locally-loaded IBT sessions.
        Returns [(RaceResult, session_index_or_None), ...]
        Matching: fuzzy track name (threshold 0.6) + lap time within ±3s.
        """
        out: list[tuple[RaceResult, Optional[int]]] = []
        for result in results:
            best_match_idx: Optional[int] = None
            best_score = 0.0
            for idx, (data, rpt) in enumerate(sessions):
                track_score = SequenceMatcher(
                    None,
                    result.track_name.lower(),
                    data.track_name.lower(),
                ).ratio()
                if track_score < 0.6:
                    continue
                # Lap time proximity check
                if result.best_lap_time > 0 and rpt.best_lap > 0:
                    if abs(result.best_lap_time - rpt.best_lap) > 3.0:
                        continue
                if track_score > best_score:
                    best_score = track_score
                    best_match_idx = idx
            out.append((result, best_match_idx))
        return out


# ── Module-level singleton ────────────────────────────────────────────────

_client: Optional[IRacingAPIClient] = None


def get_client() -> IRacingAPIClient:
    global _client
    if _client is None:
        _client = IRacingAPIClient()
    return _client


# ── Helpers ───────────────────────────────────────────────────────────────

def _tmstoms(tenths_ms: int) -> float:
    """Convert iRacing tenths-of-milliseconds to seconds."""
    if tenths_ms <= 0:
        return -1.0
    return tenths_ms / 10_000.0


def format_laptime_api(seconds: float) -> str:
    """Format seconds as M:SS.mmm, or '—' for invalid times."""
    if seconds <= 0:
        return "—"
    m = int(seconds // 60)
    s = seconds - m * 60
    return f"{m}:{s:06.3f}"


def license_level_to_str(level: int) -> str:
    """Convert iRacing license_level int to display string (e.g. 16 → 'B 4.xx')."""
    classes = {
        range(1, 5):   "R",   # Rookie
        range(5, 9):   "D",
        range(9, 13):  "C",
        range(13, 17): "B",
        range(17, 21): "A",
        range(21, 25): "P",   # Pro
    }
    for r, cls in classes.items():
        if level in r:
            return cls
    return "?"
