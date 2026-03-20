"""
Cloud sync client for the desktop app.

Handles:
  - Auth (login, register, token refresh)
  - Session upload / status polling
  - AI calls via the backend (server holds the API key)
  - Setup upload / download / diff
  - Usage info
"""
from __future__ import annotations

import io
import json
import logging
import os
import threading
import time
from typing import Any, Callable, Generator, Optional

import requests

from .license import license_state

logger = logging.getLogger(__name__)

# ── Default API base URL — overridable via env ────────────────────────────

API_BASE = os.environ.get("IRACING_ADVISOR_API", "https://api.iracing-advisor.com")
_TIMEOUT = 30     # seconds
_UPLOAD_TIMEOUT = 120


class CloudSyncError(Exception):
    pass


class AuthError(CloudSyncError):
    pass


class QuotaError(CloudSyncError):
    pass


# ── HTTP session ──────────────────────────────────────────────────────────

def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": "OptimalSector-Desktop/1.0"})
    if license_state.access_token:
        s.headers["Authorization"] = f"Bearer {license_state.access_token}"
    return s


def _handle_response(resp: requests.Response) -> dict:
    if resp.status_code == 401:
        raise AuthError("Session expired — please log in again")
    if resp.status_code == 403:
        data = resp.json() if resp.text else {}
        raise CloudSyncError(data.get("detail", "Access denied"))
    if resp.status_code == 429:
        data = resp.json() if resp.text else {}
        raise QuotaError(data.get("detail", "Rate limit exceeded"))
    if not resp.ok:
        try:
            detail = resp.json().get("detail", resp.text)
        except Exception:
            detail = resp.text
        raise CloudSyncError(f"API error {resp.status_code}: {detail}")
    return resp.json() if resp.text else {}


# ── Auth ──────────────────────────────────────────────────────────────────

def register(email: str, password: str, display_name: Optional[str] = None) -> dict:
    resp = requests.post(
        f"{API_BASE}/auth/register",
        json={"email": email, "password": password, "display_name": display_name},
        timeout=_TIMEOUT,
    )
    data = _handle_response(resp)
    license_state.login(
        user_id=data["user_id"],
        email=data["email"],
        tier=data["tier"],
        access_token=data["access_token"],
        refresh_token=data["refresh_token"],
        display_name=data.get("display_name"),
    )
    return data


def login(email: str, password: str) -> dict:
    resp = requests.post(
        f"{API_BASE}/auth/login",
        json={"email": email, "password": password, "device_hint": "desktop"},
        timeout=_TIMEOUT,
    )
    data = _handle_response(resp)
    license_state.login(
        user_id=data["user_id"],
        email=data["email"],
        tier=data["tier"],
        access_token=data["access_token"],
        refresh_token=data["refresh_token"],
        display_name=data.get("display_name"),
    )
    return data


def logout() -> None:
    if license_state.refresh_token:
        try:
            requests.post(
                f"{API_BASE}/auth/logout",
                json={"refresh_token": license_state.refresh_token},
                timeout=_TIMEOUT,
            )
        except Exception:
            pass
    license_state.logout()


def refresh_token() -> bool:
    """Silently refresh access token. Returns True on success."""
    if not license_state.refresh_token:
        return False
    try:
        resp = requests.post(
            f"{API_BASE}/auth/refresh",
            json={"refresh_token": license_state.refresh_token},
            timeout=_TIMEOUT,
        )
        if not resp.ok:
            return False
        data = resp.json()
        license_state.access_token = data["access_token"]
        license_state.refresh_token = data["refresh_token"]
        license_state.tier = data["tier"]
        license_state._save_cache()
        return True
    except Exception as exc:
        logger.warning("Token refresh failed: %s", exc)
        return False


def get_profile() -> dict:
    resp = _session().get(f"{API_BASE}/auth/me", timeout=_TIMEOUT)
    data = _handle_response(resp)
    license_state.update_tier(data["tier"])
    return data


def get_usage() -> dict:
    resp = _session().get(f"{API_BASE}/auth/me/usage", timeout=_TIMEOUT)
    return _handle_response(resp)


# ── Session upload ────────────────────────────────────────────────────────

def upload_session(
    ibt_path: str,
    on_progress: Optional[Callable[[str], None]] = None,
) -> str:
    """Upload an IBT file. Returns session_id."""
    filename = os.path.basename(ibt_path)
    size_mb = os.path.getsize(ibt_path) / 1_048_576

    if on_progress:
        on_progress(f"Uploading {filename} ({size_mb:.1f} MB)…")

    with open(ibt_path, "rb") as f:
        resp = _session().post(
            f"{API_BASE}/sessions",
            files={"file": (filename, f, "application/octet-stream")},
            timeout=_UPLOAD_TIMEOUT,
        )
    data = _handle_response(resp)
    session_id = data["session_id"]

    if on_progress:
        on_progress(f"Upload complete — processing ({session_id[:8]}…)")

    return session_id


def watch_session_status(
    session_id: str,
    timeout_s: int = 180,
    on_progress: Optional[Callable[[str], None]] = None,
) -> dict:
    """
    Connect via WebSocket and wait for a terminal status (complete/error).
    Falls back to HTTP polling if the websocket package is unavailable or the
    connection fails.  Returns the final status dict.
    """
    ws_base = API_BASE.replace("https://", "wss://").replace("http://", "ws://")
    token = license_state.access_token or ""
    ws_url = f"{ws_base}/ws/sessions/{session_id}?token={token}"

    try:
        import websocket as _ws_lib  # websocket-client package

        result: dict = {}
        error: list[str] = []
        done = threading.Event()

        def on_message(ws, msg):
            try:
                data = json.loads(msg)
            except Exception:
                return
            status = data.get("status", "")
            if on_progress and status:
                on_progress(f"Status: {status}…")
            if status == "complete":
                result.update(data)
                done.set()
                ws.close()
            elif status == "error":
                error.append(data.get("error", "Processing failed"))
                done.set()
                ws.close()

        def on_error(ws, err):
            error.append(str(err))
            done.set()

        def on_open(ws):
            pass  # initial status is sent immediately by the server

        ws_conn = _ws_lib.WebSocketApp(
            ws_url,
            on_message=on_message,
            on_error=on_error,
            on_open=on_open,
        )
        t = threading.Thread(target=ws_conn.run_forever, daemon=True)
        t.start()
        done.wait(timeout=timeout_s)

        if error:
            raise CloudSyncError(f"Processing failed: {error[0]}")
        if not result:
            raise CloudSyncError("Session processing timed out")
        return result

    except ImportError:
        # websocket-client not installed — fall back to HTTP polling
        return poll_session_status(session_id, timeout_s, on_progress)


def poll_session_status(
    session_id: str,
    timeout_s: int = 180,
    on_progress: Optional[Callable[[str], None]] = None,
) -> dict:
    """HTTP polling fallback (used when websocket-client is unavailable)."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        resp = _session().get(f"{API_BASE}/sessions/{session_id}/status", timeout=_TIMEOUT)
        data = _handle_response(resp)
        st = data.get("status")
        if on_progress:
            on_progress(f"Status: {st}…")
        if st == "complete":
            return data
        if st == "error":
            raise CloudSyncError(f"Processing failed: {data.get('error_message', '?')}")
        time.sleep(3)
    raise CloudSyncError("Session processing timed out")


def get_session_report(session_id: str) -> dict:
    resp = _session().get(f"{API_BASE}/sessions/{session_id}/report", timeout=_TIMEOUT)
    return _handle_response(resp)


def list_sessions(**kwargs) -> list:
    resp = _session().get(f"{API_BASE}/sessions", params=kwargs, timeout=_TIMEOUT)
    return _handle_response(resp)


def delete_session(session_id: str) -> None:
    resp = _session().delete(f"{API_BASE}/sessions/{session_id}", timeout=_TIMEOUT)
    _handle_response(resp)


# ── Leaderboard ───────────────────────────────────────────────────────────

def submit_leaderboard(
    car_name: str,
    track_name: str,
    lap_time_s: float,
    display_name: Optional[str] = None,
    session_id: Optional[str] = None,
) -> dict:
    """Submit an opt-in lap time to the community leaderboard."""
    payload = {
        "car_name": car_name,
        "track_name": track_name,
        "lap_time_s": lap_time_s,
        "display_name": display_name,
        "session_id": session_id,
    }
    resp = _session().post(f"{API_BASE}/leaderboard/submit",
                           json=payload, timeout=_TIMEOUT)
    return _handle_response(resp)


def get_leaderboard(car_name: str, track_name: str, limit: int = 25) -> dict:
    """Fetch top lap times for a car+track combo."""
    resp = _session().get(
        f"{API_BASE}/leaderboard/times",
        params={"car_name": car_name, "track_name": track_name, "limit": limit},
        timeout=_TIMEOUT,
    )
    return _handle_response(resp)


def get_leaderboard_standing(car_name: str, track_name: str) -> dict:
    """Return the authenticated user's rank and percentile."""
    resp = _session().get(
        f"{API_BASE}/leaderboard/my-standing",
        params={"car_name": car_name, "track_name": track_name},
        timeout=_TIMEOUT,
    )
    return _handle_response(resp)


# ── AI via backend (server-side Claude key) ───────────────────────────────

def stream_ai_recommendations(
    session_id: str,
    focus: Optional[str] = None,
    on_chunk: Optional[Callable[[str], None]] = None,
) -> str:
    """Stream AI recommendations. Calls on_chunk for each text token. Returns full text."""
    resp = _session().post(
        f"{API_BASE}/ai/recommendations",
        json={"session_id": session_id, "focus": focus},
        stream=True,
        timeout=120,
    )
    _handle_response_streaming(resp)
    return _consume_sse(resp, on_chunk)


def stream_ai_chat(
    session_id: str,
    message: str,
    history: list,
    on_chunk: Optional[Callable[[str], None]] = None,
) -> str:
    resp = _session().post(
        f"{API_BASE}/ai/chat",
        json={"session_id": session_id, "message": message, "history": history},
        stream=True,
        timeout=120,
    )
    _handle_response_streaming(resp)
    return _consume_sse(resp, on_chunk)


def stream_session_note(
    session_id: str,
    on_chunk: Optional[Callable[[str], None]] = None,
) -> str:
    resp = _session().post(
        f"{API_BASE}/ai/session-note",
        json={"session_id": session_id},
        stream=True,
        timeout=60,
    )
    _handle_response_streaming(resp)
    return _consume_sse(resp, on_chunk)


# ── Setup management ──────────────────────────────────────────────────────

def upload_setup(setup_path: str, car_name: Optional[str] = None,
                 track_name: Optional[str] = None) -> dict:
    filename = os.path.basename(setup_path)
    with open(setup_path, "rb") as f:
        resp = _session().post(
            f"{API_BASE}/setups",
            files={"file": (filename, f, "application/octet-stream")},
            params={"car_name": car_name, "track_name": track_name},
            timeout=_TIMEOUT,
        )
    return _handle_response(resp)


def list_setups(**kwargs) -> list:
    resp = _session().get(f"{API_BASE}/setups", params=kwargs, timeout=_TIMEOUT)
    return _handle_response(resp)


def diff_setups(setup_a_id: str, setup_b_id: str) -> dict:
    resp = _session().get(
        f"{API_BASE}/setups/diff",
        params={"setup_a": setup_a_id, "setup_b": setup_b_id},
        timeout=_TIMEOUT,
    )
    return _handle_response(resp)


# ── Background upload helper ──────────────────────────────────────────────

def upload_session_async(
    ibt_path: str,
    on_status: Optional[Callable[[str], None]] = None,
    on_complete: Optional[Callable[[dict], None]] = None,
    on_error: Optional[Callable[[str], None]] = None,
) -> threading.Thread:
    """Upload and process a session in a background thread."""

    def _worker():
        try:
            session_id = upload_session(ibt_path, on_progress=on_status)
            result = poll_session_status(session_id, on_progress=on_status)
            if on_complete:
                on_complete(result)
        except (CloudSyncError, AuthError, QuotaError) as exc:
            if on_error:
                on_error(str(exc))
        except Exception as exc:
            logger.exception("upload_session_async error")
            if on_error:
                on_error(f"Unexpected error: {exc}")

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    return t


# ── SSE helpers ───────────────────────────────────────────────────────────

def _handle_response_streaming(resp: requests.Response) -> None:
    if resp.status_code == 401:
        raise AuthError("Session expired")
    if resp.status_code == 429:
        raise QuotaError("AI quota exceeded")
    if not resp.ok:
        raise CloudSyncError(f"API error {resp.status_code}")


def _consume_sse(
    resp: requests.Response,
    on_chunk: Optional[Callable[[str], None]],
) -> str:
    full = []
    for line in resp.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload == "[DONE]":
            break
        try:
            obj = json.loads(payload)
            text = obj.get("text", "")
            if text:
                full.append(text)
                if on_chunk:
                    on_chunk(text)
        except json.JSONDecodeError:
            pass
    return "".join(full)
