"""
iracing_client.py — iRacing Data API wrapper for Optimal Sector.

Wraps jasondilworth56/iracingdataapi to provide:
  - Singleton client with lazy auth (re-auths on 401 automatically)
  - Thread-safe credential fetch from OS keyring
  - Helper methods mapped to Optimal Sector's specific data needs
  - Graceful degradation when credentials are missing

The underlying iracingdataapi.client.irDataClient handles:
  - SHA256+base64 password hashing (iRacing's required format)
  - Cookie-based session management
  - Automatic re-authentication on 401
  - Rate limit tracking
  - OAuth2 token support (future path as iRacing migrates)

Usage:
    from core.iracing_client import get_ir_client, IRacingClientError
    try:
        client = get_ir_client()
        seasons = client.current_seasons_schedule()
        standings = client.season_driver_standings(season_id=12345)
    except IRacingClientError as e:
        # No credentials, auth failed, or API error
        logger.warning('iRacing API: %s', e)
"""

from __future__ import annotations
import logging
import threading
from typing import Optional

logger = logging.getLogger(__name__)


class IRacingClientError(Exception):
    """Raised when the iRacing Data API client cannot complete a request."""
    pass


class _IRacingClient:
    """
    Thread-safe wrapper around irDataClient.
    Lazy-initialises on first use, reads credentials from OS keyring.
    """

    def __init__(self):
        self._client = None
        self._lock   = threading.Lock()

    def _get_client(self):
        """Return an authenticated irDataClient, creating one if needed."""
        with self._lock:
            if self._client is not None:
                return self._client

        # Get credentials from keyring
        try:
            from core.config import get_iracing_credentials
            email, password = get_iracing_credentials()
        except Exception as e:
            raise IRacingClientError(
                f'Could not read iRacing credentials from keyring: {e}')

        if not email or not password:
            raise IRacingClientError(
                'iRacing credentials not set. '
                'Enter email and password in Settings → Weekly Prep.')

        try:
            from iracingdataapi.client import irDataClient
            client = irDataClient(username=email, password=password)
            with self._lock:
                self._client = client
            logger.info('iRacing Data API client authenticated for %s', email)
            return client
        except ImportError:
            raise IRacingClientError(
                'iracingdataapi package not installed. '
                'Run: pip install iracingdataapi pydantic')
        except Exception as e:
            raise IRacingClientError(f'iRacing authentication failed: {e}')

    def invalidate(self):
        """Force re-authentication on next use (e.g. after credential change)."""
        with self._lock:
            self._client = None

    # ── Schedule / Season ─────────────────────────────────────────────────────

    def current_seasons_schedule(self) -> list[dict]:
        """
        Return all currently active series with their weekly schedules.
        Maps to iracingdataapi.series_seasons(include_series=True).

        Returns list of dicts: {series_id, series_name, car_class_name,
        track_name, config_name, race_week_num, season_id}
        """
        try:
            client = self._get_client()
            seasons = client.series_seasons(include_series=True)
            if not seasons:
                return []

            results = []
            for s in (seasons if isinstance(seasons, list) else []):
                try:
                    series_id   = getattr(s, 'series_id', None) or s.get('series_id', 0)
                    series_name = getattr(s, 'series_name', None) or s.get('series_name', '')
                    season_id   = getattr(s, 'season_id', None)   or s.get('season_id', 0)

                    # car_class_name may be in nested series info
                    car_class = (getattr(s, 'car_class_name', None) or
                                 s.get('car_class_name', '') or
                                 getattr(s, 'series', {}).get('car_class_name', '')
                                 if isinstance(s, dict) else '')

                    # Schedules (weekly track rotation)
                    schedules = getattr(s, 'schedules', None) or s.get('schedules', [])
                    if schedules:
                        for week in schedules:
                            try:
                                track  = (getattr(week, 'track', None) or
                                          week.get('track', {}) if isinstance(week, dict) else {})
                                t_name = (getattr(track, 'track_name', None) or
                                          track.get('track_name', '') if isinstance(track, dict)
                                          else str(track))
                                c_name = (getattr(track, 'config_name', None) or
                                          track.get('config_name', '') if isinstance(track, dict)
                                          else '')
                                week_n = (getattr(week, 'race_week_num', 0) or
                                          week.get('race_week_num', 0) if isinstance(week, dict)
                                          else 0)
                                results.append({
                                    'series_id':      series_id,
                                    'season_id':      season_id,
                                    'series_name':    series_name,
                                    'car_class_name': car_class,
                                    'track_name':     t_name,
                                    'config_name':    c_name,
                                    'race_week_num':  week_n,
                                })
                            except Exception:
                                continue
                    else:
                        # Series with no schedule data — add a bare entry
                        results.append({
                            'series_id':      series_id,
                            'season_id':      season_id,
                            'series_name':    series_name,
                            'car_class_name': car_class,
                            'track_name':     '',
                            'config_name':    '',
                            'race_week_num':  0,
                        })
                except Exception:
                    continue

            logger.info('iRacing schedule: %d entries fetched', len(results))
            return results

        except IRacingClientError:
            raise
        except Exception as e:
            raise IRacingClientError(f'Schedule fetch failed: {e}')

    # ── Season Results / Leaderboard ──────────────────────────────────────────

    def season_driver_standings(self, season_id: int,
                                 car_class_id: int = 0) -> list[dict]:
        """
        Return top driver standings for a season.
        Maps to iracingdataapi.stats_season_driver_standings().

        Returns list of dicts: {cust_id, display_name, position,
        best_lap_time, points, starts}
        Sorted by position ascending.
        """
        try:
            client = self._get_client()
            # car_class_id=0 is not valid — use 1 as fallback for broad query
            cid = car_class_id if car_class_id > 0 else None
            if cid:
                raw = client.stats_season_driver_standings(
                    season_id=season_id, car_class_id=cid)
            else:
                # Try without car_class_id constraint
                raw = client.result_season_results(season_id=season_id)

            if not raw:
                return []

            results = []
            entries = raw if isinstance(raw, list) else raw.get('standings', [])
            for i, entry in enumerate(entries[:20]):
                try:
                    if hasattr(entry, '__dict__'):
                        d = vars(entry)
                    elif isinstance(entry, dict):
                        d = entry
                    else:
                        continue
                    results.append({
                        'position':      d.get('position', i + 1),
                        'display_name':  (d.get('display_name') or
                                          d.get('driver_name') or f'P{i+1}'),
                        'cust_id':       d.get('cust_id', 0),
                        'points':        d.get('points', 0),
                        'starts':        d.get('starts', 0),
                        'best_lap_time': d.get('best_lap_time', 0),
                    })
                except Exception:
                    continue

            return sorted(results, key=lambda x: x['position'])

        except IRacingClientError:
            raise
        except Exception as e:
            raise IRacingClientError(f'Standings fetch failed: {e}')

    def season_qual_results(self, season_id: int,
                             car_class_id: int = 0) -> list[dict]:
        """
        Top qualifying times for a season — best representation of
        pure lap time pace for leaderboard display.
        Maps to stats_season_qualify_results().
        """
        try:
            client = self._get_client()
            cid = car_class_id if car_class_id > 0 else 1
            raw = client.stats_season_qualify_results(
                season_id=season_id, car_class_id=cid)
            if not raw:
                return []

            results = []
            entries = raw if isinstance(raw, list) else raw.get('results', [])
            for i, entry in enumerate(entries[:10]):
                try:
                    d = vars(entry) if hasattr(entry, '__dict__') else (
                        entry if isinstance(entry, dict) else {})
                    results.append({
                        'position':     d.get('position', i + 1),
                        'display_name': d.get('display_name') or d.get('driver_name') or f'P{i+1}',
                        'best_lap_time': d.get('best_lap_time', 0),
                        'cust_id':      d.get('cust_id', 0),
                    })
                except Exception:
                    continue
            return sorted(results, key=lambda x: x['position'])

        except IRacingClientError:
            raise
        except Exception as e:
            raise IRacingClientError(f'Qual results fetch failed: {e}')

    # ── Member Stats ──────────────────────────────────────────────────────────

    def member_recent_races(self, cust_id: int = None) -> list[dict]:
        """
        Recent race results for a member (defaults to authenticated user).
        Maps to stats_member_recent_races().
        """
        try:
            client = self._get_client()
            raw = client.stats_member_recent_races(cust_id=cust_id)
            if not raw:
                return []
            entries = raw if isinstance(raw, list) else raw.get('races', [])
            results = []
            for entry in entries[:20]:
                d = vars(entry) if hasattr(entry, '__dict__') else (
                    entry if isinstance(entry, dict) else {})
                results.append({
                    'series_name': d.get('series_name', ''),
                    'track':       d.get('track', {}).get('track_name', '') if isinstance(
                                   d.get('track'), dict) else str(d.get('track', '')),
                    'finish_pos':  d.get('finish_position', 0),
                    'start_pos':   d.get('starting_position', 0),
                    'incidents':   d.get('incidents', 0),
                    'best_lap':    d.get('best_lap_time', 0),
                    'champ_pts':   d.get('champ_pts', 0),
                })
            return results
        except IRacingClientError:
            raise
        except Exception as e:
            raise IRacingClientError(f'Recent races fetch failed: {e}')


# ── Singleton accessor ─────────────────────────────────────────────────────────

_instance: Optional[_IRacingClient] = None
_instance_lock = threading.Lock()


def get_ir_client() -> _IRacingClient:
    """Return the singleton _IRacingClient. Creates it on first call."""
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = _IRacingClient()
    return _instance


def invalidate_ir_client():
    """Force re-auth on next use — call after credential change."""
    global _instance
    with _instance_lock:
        if _instance is not None:
            _instance.invalidate()
