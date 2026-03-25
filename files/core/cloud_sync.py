"""
Cloud auth client for the desktop app.

Handles authentication (login, register, token refresh) and usage
info for the OptimalSector licensing backend.  All telemetry analysis
is performed locally; no IBT data is uploaded.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import requests

from .license import license_state

logger = logging.getLogger(__name__)

API_BASE = os.environ.get("IRACING_ADVISOR_API", "https://api.iracing-advisor.com")
_TIMEOUT = 30


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
