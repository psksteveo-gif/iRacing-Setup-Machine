"""
iRacing IBT Telemetry Parser
Reads iRacing .ibt binary telemetry files into structured TelemetryData objects.
Also provides a demo data generator for testing without real telemetry files.
"""

import os
import struct
import logging
import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


@dataclass
class TelemetryData:
    """Structured telemetry data from an iRacing session."""
    car_name: str = ""
    track_name: str = ""
    num_laps: int = 0
    lap_times: List[float] = field(default_factory=list)
    lap_boundaries: List[int] = field(default_factory=list)   # sample indices
    tick_rate: int = 60
    session_info: Dict[str, Any] = field(default_factory=dict)
    _channels: Dict[str, np.ndarray] = field(default_factory=dict, repr=False)

    def get_channel(self, name: str) -> Optional[np.ndarray]:
        return self._channels.get(name)

    def set_channel(self, name: str, data: np.ndarray):
        self._channels[name] = data

    @property
    def channel_names(self) -> List[str]:
        return list(self._channels.keys())

    @property
    def is_fixed_setup(self) -> bool:
        """True when the session was run in a fixed-setup series/event."""
        return bool(self.session_info.get('is_fixed_setup', False))


class IBTParser:
    """Parse iRacing .ibt binary telemetry files."""

    def __init__(self, path: str):
        if not os.path.exists(path):
            raise FileNotFoundError(f"IBT file not found: {path}")
        self.path = path

    # Thresholds for pre-load warnings (checked before reading the file)
    MIN_VALID_SIZE   = 112        # bytes — smaller than this can't hold a valid header
    WARN_SIZE_MB     = 200        # show a "large file" notice above this
    MAX_SIZE_MB      = 500        # hard reject above this

    def file_size_mb(self) -> float:
        """Return file size in MB without reading the file."""
        try:
            return os.path.getsize(self.path) / (1024 * 1024)
        except OSError:
            return 0.0

    def parse(self) -> TelemetryData:
        """Parse an iRacing .ibt binary telemetry file into structured TelemetryData."""
        import time
        data = TelemetryData()
        try:
            t0 = time.perf_counter()
            file_size = os.path.getsize(self.path)

            # Zero-length file
            if file_size == 0:
                raise ValueError(
                    "The IBT file is empty (0 bytes). "
                    "This usually means iRacing crashed before writing any telemetry. "
                    "Try loading a different session."
                )

            # Too small to be valid
            if file_size < self.MIN_VALID_SIZE:
                raise ValueError(
                    f"The IBT file is too small to be valid ({file_size} bytes). "
                    "The session may have ended immediately after starting."
                )

            # Hard size limit
            if file_size > self.MAX_SIZE_MB * 1024 * 1024:
                raise ValueError(
                    f"IBT file is {file_size / (1024*1024):.0f} MB — "
                    f"maximum supported size is {self.MAX_SIZE_MB} MB. "
                    "For endurance sessions, trim the file or load in segments."
                )

            t1 = time.perf_counter()
            try:
                with open(self.path, 'rb') as f:
                    raw = f.read()
            except PermissionError:
                raise ValueError(
                    "Cannot read the IBT file — it may be locked by iRacing. "
                    "Close iRacing or wait for the session to fully save, then try again."
                )
            except OSError as e:
                raise ValueError(f"Could not read IBT file: {e}")

            t2 = time.perf_counter()
            data = self._parse_binary(raw)
            t3 = time.perf_counter()
            logger.info(
                "IBTParser timings: size check=%.3fs, read=%.3fs, parse=%.3fs, total=%.3fs",
                t1-t0, t2-t1, t3-t2, t3-t0,
            )
        except (ValueError, FileNotFoundError):
            raise
        except Exception as e:
            raise RuntimeError(
                f"Failed to parse IBT file: {e}\n\n"
                "The file may be corrupted, incomplete, or from an unsupported iRacing version."
            )
        return data

    def _parse_binary(self, raw: bytes) -> TelemetryData:
        """Parse iRacing binary telemetry format."""
        data = TelemetryData()

        # iRacing IBT header structure
        if len(raw) < 112:
            raise ValueError("File too small to be a valid IBT file")

        # Read header — iRacing SDK irsdk_header layout:
        #   0: ver, 4: status, 8: tickRate, 12: sessionInfoUpdate (skip),
        #  16: sessionInfoLen, 20: sessionInfoOffset, 24: numVars,
        #  28: varHeaderOffset, 32: numBuf, 36: bufLen, 40-47: pad[2]
        #  48+: varBuf[4]  (each 16 bytes: tickCount, offset, pad[2])
        version = struct.unpack_from('i', raw, 0)[0]
        status = struct.unpack_from('i', raw, 4)[0]
        tick_rate = struct.unpack_from('i', raw, 8)[0]
        # offset 12 = sessionInfoUpdate (a rolling counter — not the offset)
        session_info_len = struct.unpack_from('i', raw, 16)[0]
        session_info_offset = struct.unpack_from('i', raw, 20)[0]
        num_vars = struct.unpack_from('i', raw, 24)[0]
        var_header_offset = struct.unpack_from('i', raw, 28)[0]
        num_buf = struct.unpack_from('i', raw, 32)[0]
        buf_len = struct.unpack_from('i', raw, 36)[0]
        logger.info(f"IBT header: version={version}, status={status}, tick_rate={tick_rate}, session_info_offset={session_info_offset}, session_info_len={session_info_len}, num_vars={num_vars}, var_header_offset={var_header_offset}, num_buf={num_buf}, buf_len={buf_len}")

        # Validate header offsets are within file bounds
        if session_info_offset < 0 or session_info_len < 0:
            raise ValueError("Invalid session info offset in IBT header")
        if session_info_offset + session_info_len > len(raw):
            raise ValueError("Session info extends beyond end of file")
        if num_vars < 0 or num_vars > 5000:
            raise ValueError(
                f"Invalid IBT header: num_vars={num_vars} is out of range. "
                f"(ver={version}, status={status}, tick_rate={tick_rate}, "
                f"session_info_offset={session_info_offset}, buf_len={buf_len})"
            )
        if var_header_offset < 0 or var_header_offset > len(raw):
            raise ValueError("Invalid variable header offset in IBT header")

        data.tick_rate = tick_rate if tick_rate > 0 else 60

        # Parse session info YAML
        if session_info_offset > 0 and session_info_len > 0:
            try:
                info_bytes = raw[session_info_offset:session_info_offset + session_info_len]
                info_str = info_bytes.decode('latin-1', errors='ignore').rstrip('\x00')
                data.session_info = self._parse_session_yaml(info_str)
                data.car_name = data.session_info.get('car_name', 'Unknown Car')
                data.track_name = data.session_info.get('track_name', 'Unknown Track')
            except Exception as e:
                logger.warning("Failed to parse session info YAML: %s", e)

        # Parse variable headers
        var_headers = []
        for i in range(num_vars):
            offset = var_header_offset + i * 144
            if offset + 144 > len(raw):
                logger.warning("IBT header truncated: only %d of %d variables fit in file", i, num_vars)
                break
            var_type = struct.unpack_from('i', raw, offset)[0]
            var_offset = struct.unpack_from('i', raw, offset + 4)[0]
            var_count = struct.unpack_from('i', raw, offset + 8)[0]
            name = raw[offset + 16:offset + 48].decode('latin-1').rstrip('\x00')
            var_headers.append({
                'type': var_type, 'offset': var_offset,
                'count': var_count, 'name': name.strip()
            })

        # Read data buffers
        if num_buf > 0 and buf_len > 0:
            # varBuf[0] starts at offset 48: {tickCount(4), offset(4), pad[2](8)}
            # The actual data start offset is at byte 52 (varBuf[0].offset)
            buf_offset = struct.unpack_from('i', raw, 52)[0]
            if buf_offset <= 0 or buf_offset >= len(raw):
                raise ValueError(f"Invalid data buffer offset: {buf_offset}")
            total_samples = (len(raw) - buf_offset) // buf_len
            if total_samples <= 0:
                raise ValueError(f"No data samples found (buf_offset={buf_offset}, buf_len={buf_len}, file_size={len(raw)})")

            # Build one contiguous (total_samples × buf_len) byte matrix — parse each
            # variable by slicing the appropriate columns.  This is ~10-50× faster than
            # the previous per-variable fancy-indexing approach.
            # iRacing SDK irsdk_VarType: 0=char, 1=bool, 2=int32, 3=bitField(u32),
            #                           4=float32, 5=double(f64)
            type_map = {0: ('u1',  1),   # char
                        1: ('u1',  1),   # bool
                        2: ('<i4', 4),   # int32
                        3: ('<u4', 4),   # bitField / uint32
                        4: ('<f4', 4),   # float32
                        5: ('<f8', 8)}
            raw_matrix = np.frombuffer(raw, dtype=np.uint8,
                                       offset=buf_offset,
                                       count=total_samples * buf_len
                                       ).reshape(total_samples, buf_len)
            for vh in var_headers:
                try:
                    np_dtype, sz = type_map.get(vh['type'], ('<f4', 4))
                    vo = vh['offset']
                    if vo < 0 or vo + sz > buf_len:
                        continue
                    # Direct view into the raw matrix — no copy.
                    # Stride trick: view each row's [vo:vo+sz] bytes as the
                    # target dtype, then squeeze the sub-element axis away.
                    col_view = raw_matrix[:, vo:vo + sz]
                    if col_view.flags['C_CONTIGUOUS']:
                        channel_data = col_view.view(np_dtype).reshape(-1).astype(np.float64)
                    else:
                        # Fallback: single contiguous copy only when needed
                        channel_data = np.ascontiguousarray(col_view).view(np_dtype).reshape(-1).astype(np.float64)
                    data.set_channel(vh['name'], channel_data)
                except (KeyError, IndexError, ValueError, struct.error) as e:
                    logger.debug("Skipping channel %s: %s", vh.get('name', '?'), e)
            del raw_matrix, raw  # Free large buffers before lap derivation

        # Derive lap data from LapDistPct channel (primary), fallback to SessionTime gaps
        lap_dist = data.get_channel('LapDistPct')
        if lap_dist is not None and len(lap_dist) > 0:
            self._derive_laps(data, lap_dist)
        else:
            # Fallback: try LapCurrentLapTime resets, or SessionTime-based heuristic
            logger.warning("LapDistPct channel missing — using fallback lap detection.")
            self._derive_laps_fallback(data)

        # ── Channel sanity checks ──────────────────────────────────────────
        # Clip known channels to physical limits so downstream analysis is never
        # fed garbage values from corrupted or truncated IBT data.
        _CHANNEL_CLAMPS = {
            'Throttle':        (0.0, 1.0),
            'Brake':           (0.0, 1.0),
            'Clutch':          (0.0, 1.0),
            'SteeringWheelAngle': (-10.0, 10.0),  # radians; >10 rad is physically impossible
            'Speed':           (0.0, 150.0),       # m/s — ~540 kph; faster is sensor noise
            'RPM':             (0.0, 30000.0),
            'Gear':            (-1.0, 8.0),
            'LapDistPct':      (0.0, 1.0),
            'FuelLevel':       (0.0, 1000.0),      # litres
            'WaterTemp':       (0.0, 200.0),       # °C
            'OilTemp':         (0.0, 300.0),       # °C
            'LatAccel':        (-100.0, 100.0),    # m/s²
            'LongAccel':       (-100.0, 100.0),
            'VertAccel':       (-100.0, 100.0),
        }
        _clamped = 0
        for ch_name, (lo, hi) in _CHANNEL_CLAMPS.items():
            ch = data.get_channel(ch_name)
            if ch is None:
                continue
            out_of_range = np.sum((ch < lo) | (ch > hi))
            if out_of_range > 0:
                data.set_channel(ch_name, np.clip(ch, lo, hi))
                _clamped += out_of_range
                logger.debug("Clamped %d out-of-range values in channel %s [%s, %s]",
                             out_of_range, ch_name, lo, hi)
        if _clamped:
            logger.warning("IBT sanity check clamped %d total values across channels — "
                           "file may be partially corrupted.", _clamped)

        return data

    # LapDistPct must drop by more than this between consecutive samples
    # to indicate a lap boundary (start/finish line crossing).
    LAP_RESET_THRESHOLD = 0.5

    def _derive_laps(self, data: TelemetryData, lap_dist: np.ndarray):
        """Find lap boundaries from LapDistPct resets."""
        boundaries = [0]
        for i in range(1, len(lap_dist)):
            if lap_dist[i] < lap_dist[i - 1] - self.LAP_RESET_THRESHOLD:
                boundaries.append(i)
        boundaries.append(len(lap_dist))

        session_time = data.get_channel('SessionTime')
        lap_last = data.get_channel('LapLastLapTime')
        lap_times = []
        for i in range(len(boundaries) - 1):
            official_time = None
            # Prefer iRacing's official LapLastLapTime recorded at the crossing point.
            # At boundaries[i+1] the S/F line was just crossed and LapLastLapTime updates
            # to the time of the lap that just completed (lap i).
            # Skip the last segment — it's an incomplete lap with no crossing event.
            if lap_last is not None and i + 1 < len(boundaries) - 1:
                b_end = boundaries[i + 1]
                # LapLastLapTime holds the PREVIOUS lap's time until the crossing,
                # then updates to the newly completed lap's time at or just after
                # the boundary sample.  Detect the value change to get the new time.
                prev_val = float(lap_last[b_end - 1]) if b_end > 0 else -1.0
                for k in range(b_end, min(b_end + 5, len(lap_last))):
                    lt = float(lap_last[k])
                    if lt > 0 and lt != prev_val:
                        official_time = lt
                        break

            if official_time is not None:
                lap_times.append(official_time)
            elif session_time is not None:
                t0 = session_time[boundaries[i]]
                t1 = session_time[boundaries[i + 1] - 1]
                lap_times.append(t1 - t0)
            else:
                samples = boundaries[i + 1] - boundaries[i]
                lap_times.append(samples / max(data.tick_rate, 1))

        data.lap_boundaries = boundaries
        data.lap_times = lap_times
        data.num_laps = len(lap_times)

    def _derive_laps_fallback(self, data: TelemetryData):
        """Fallback lap detection using LapCurrentLapTime resets or fixed-length splits."""
        lap_cur = data.get_channel('LapCurrentLapTime')
        session_time = data.get_channel('SessionTime')

        if lap_cur is not None and len(lap_cur) > 100:
            # Detect resets in LapCurrentLapTime (drops by > 5 seconds)
            boundaries = [0]
            for i in range(1, len(lap_cur)):
                if lap_cur[i] < lap_cur[i - 1] - 5.0:
                    boundaries.append(i)
            boundaries.append(len(lap_cur))
        elif session_time is not None and len(session_time) > 100:
            # Last resort: split into ~90-second chunks
            total_time = session_time[-1] - session_time[0]
            est_lap = 90.0
            boundaries = [0]
            for i in range(1, len(session_time)):
                if session_time[i] - session_time[boundaries[-1]] >= est_lap:
                    boundaries.append(i)
            boundaries.append(len(session_time))
        else:
            return

        lap_times = []
        for i in range(len(boundaries) - 1):
            if session_time is not None:
                t0 = session_time[boundaries[i]]
                t1 = session_time[boundaries[i + 1] - 1]
                lap_times.append(t1 - t0)
            else:
                samples = boundaries[i + 1] - boundaries[i]
                lap_times.append(samples / max(data.tick_rate, 1))

        data.lap_boundaries = boundaries
        data.lap_times = lap_times
        data.num_laps = len(lap_times)

    def _parse_session_yaml(self, text: str) -> Dict[str, Any]:
        """Extract key values from iRacing session YAML."""
        info: Dict[str, Any] = {}
        # Collect all Drivers entries by CarIdx, resolve player after full parse.
        # DriverCarIdx can appear before OR after the Drivers list depending on session
        # type, so we can't rely on parse order.
        _driver_car_idx: int = -1
        _drivers: Dict[int, Dict] = {}   # caridx → {screen_name, path, is_pace, is_ai}
        _cur_car_idx: int = -1

        for line in text.splitlines():
            line = line.strip()
            if ':' in line:
                key, _, val = line.partition(':')
                key = key.strip()
                if key.startswith('-'):   # strip YAML list-item marker e.g. "- CarIdx"
                    key = key[1:].strip()
                key = key.lower().replace(' ', '_')
                val = val.strip()
                if key == 'drivercaridx':
                    try:
                        _driver_car_idx = int(val)
                    except ValueError:
                        pass
                elif key == 'caridx':
                    try:
                        _cur_car_idx = int(val)
                    except ValueError:
                        _cur_car_idx = -1
                    if _cur_car_idx >= 0 and _cur_car_idx not in _drivers:
                        _drivers[_cur_car_idx] = {'screen_name': '', 'path': '',
                                                   'is_pace': False, 'is_ai': False}
                elif _cur_car_idx >= 0:
                    entry = _drivers.get(_cur_car_idx, {})
                    if key == 'carscreenname' and val and not entry.get('screen_name'):
                        entry['screen_name'] = val
                        _drivers[_cur_car_idx] = entry
                    elif key == 'carpath' and val and not entry.get('path'):
                        entry['path'] = val.split('/')[-1] if '/' in val else val
                        _drivers[_cur_car_idx] = entry
                    elif key == 'carispacecar':
                        entry['is_pace'] = val == '1'
                        _drivers[_cur_car_idx] = entry
                    elif key == 'carisai':
                        entry['is_ai'] = val == '1'
                        _drivers[_cur_car_idx] = entry
                if key == 'drivercartpath' and val and 'car_name' not in info:
                    # Legacy key (older SDK versions)
                    info['car_name'] = val.split('/')[-1] if '/' in val else val
                elif key == 'trackdisplayname':
                    info['track_name'] = val
                elif key == 'trackconfigname' and val:
                    info.setdefault('track_name', '')
                    if info['track_name']:
                        info['track_name'] += f' - {val}'
                elif key == 'airtemp':
                    try: info['air_temp_c'] = float(val.split()[0])
                    except (ValueError, IndexError): pass
                elif key == 'tracktemp':
                    try: info['track_temp_c'] = float(val.split()[0])
                    except (ValueError, IndexError): pass
                elif key == 'drivername':
                    info['driver_name'] = val
                elif key == 'sessiontype':
                    info['session_type'] = val
                elif key == 'tracklength':
                    try: info['track_length_km'] = float(val.split()[0])
                    except (ValueError, IndexError): pass
                elif key == 'driverfuelmaximum' or key == 'fuelcapacity':
                    try: info['fuel_capacity_l'] = float(val.split()[0])
                    except (ValueError, IndexError): pass
                elif key == 'weathertype':
                    info['weather_type'] = val
                elif key == 'windspeed':
                    try: info['wind_speed_ms'] = float(val.split()[0])
                    except (ValueError, IndexError): pass
                elif key == 'winddirection':
                    try: info['wind_direction_deg'] = float(val.split()[0])
                    except (ValueError, IndexError): pass
                elif key == 'skies':
                    info['skies'] = val
                elif key == 'sessionlaps':
                    info['session_laps'] = val
                elif key == 'sessiontime':
                    info['session_time_limit'] = val
        # Store the player's car index so downstream code can identify their ResultsPositions entry
        if _driver_car_idx >= 0:
            info['driver_car_idx'] = _driver_car_idx
        # Extract CarSetup block
        try:
            car_setup = self._extract_car_setup(text)
            if car_setup:
                info['car_setup'] = car_setup
        except Exception as e:
            logger.debug("CarSetup extraction skipped: %s", e)

        # Extract WeekendInfo (track city, country, turns, pit speed)
        try:
            wi = self._extract_yaml_block(text, 'WeekendInfo')
            if wi:
                if 'TrackCity' in wi:       info['track_city']       = wi['TrackCity']
                if 'TrackCountry' in wi:    info['track_country']    = wi['TrackCountry']
                if 'TrackNumTurns' in wi:
                    try: info['track_num_turns'] = int(wi['TrackNumTurns'])
                    except (ValueError, TypeError): pass
                if 'TrackPitSpeedLimit' in wi:
                    raw_ps = str(wi['TrackPitSpeedLimit']).split()[0]
                    try: info['pit_speed_limit'] = float(raw_ps)
                    except ValueError: pass
                if 'EventType' in wi:       info['event_type']       = wi['EventType']
                if 'Season' in wi:          info['season']           = wi['Season']
                if 'RaceWeek' in wi:
                    try: info['race_week'] = int(wi['RaceWeek'])
                    except (ValueError, TypeError): pass
        except Exception as e:
            logger.debug("WeekendInfo extraction skipped: %s", e)

        # Extract WeekendOptions — IsFixedSetup flag
        try:
            wo = self._extract_yaml_block(text, 'WeekendOptions')
            if wo and 'IsFixedSetup' in wo:
                info['is_fixed_setup'] = bool(int(wo['IsFixedSetup']))
            else:
                info.setdefault('is_fixed_setup', False)
        except Exception as e:
            info.setdefault('is_fixed_setup', False)
            logger.debug("WeekendOptions extraction skipped: %s", e)

        # Extract SplitTimeInfo → real iRacing sector boundaries
        try:
            sti = self._extract_yaml_block(text, 'SplitTimeInfo')
            if sti and 'Sectors' in sti and isinstance(sti['Sectors'], list):
                splits = []
                for sec in sti['Sectors']:
                    if isinstance(sec, dict) and 'SectorStartPct' in sec:
                        try: splits.append(float(sec['SectorStartPct']))
                        except (ValueError, TypeError): pass
                if splits:
                    info['iracing_sector_splits'] = sorted(splits)
        except Exception as e:
            logger.debug("SplitTimeInfo extraction skipped: %s", e)

        # Extract DriverInfo → player iRating, license, car number
        try:
            di = self._extract_yaml_block(text, 'DriverInfo')
            if di:
                driver_car_idx = di.get('DriverCarIdx', _driver_car_idx)
                drivers_list = di.get('Drivers', [])
                if isinstance(drivers_list, list):
                    player = next(
                        (d for d in drivers_list
                         if isinstance(d, dict) and d.get('CarIdx') == driver_car_idx),
                        drivers_list[0] if drivers_list else None
                    )
                    if player and isinstance(player, dict):
                        if 'IRating' in player:
                            try: info['irating'] = int(player['IRating'])
                            except (ValueError, TypeError): pass
                        if 'LicString' in player:
                            info['license_string'] = str(player['LicString'])
                        if 'LicLevel' in player:
                            try: info['lic_level'] = int(player['LicLevel'])
                            except (ValueError, TypeError): pass
                        if 'CarNumber' in player:
                            info['car_number'] = str(player['CarNumber'])
                        if 'TeamName' in player and player['TeamName']:
                            info['team_name'] = str(player['TeamName'])
                        if 'IsSpectator' in player:
                            info['is_spectator'] = bool(int(player.get('IsSpectator', 0)))
        except Exception as e:
            logger.debug("DriverInfo extraction skipped: %s", e)

        # Extract SessionInfo → ResultsPositions for the active session
        try:
            si = self._extract_yaml_block(text, 'SessionInfo')
            if si and 'Sessions' in si and isinstance(si['Sessions'], list):
                # Find the last session that has results
                results = None
                for sess in reversed(si['Sessions']):
                    if isinstance(sess, dict) and 'ResultsPositions' in sess:
                        rp = sess['ResultsPositions']
                        if isinstance(rp, list) and rp:
                            results = rp
                            info['results_session_type'] = sess.get('SessionType', '')
                            break
                if results:
                    parsed_results = []
                    for entry in results:
                        if not isinstance(entry, dict): continue
                        try:
                            parsed_results.append({
                                'position':       int(entry.get('Position', 0)),
                                'class_position': int(entry.get('ClassPosition', 0)),
                                'car_idx':        int(entry.get('CarIdx', -1)),
                                'fastest_time':   float(entry.get('FastestTime', 0)),
                                'last_time':      float(entry.get('LastTime', 0)),
                                'laps':           int(entry.get('Laps', 0)),
                                'laps_complete':  int(entry.get('LapsComplete', 0)),
                                'reason_out':     str(entry.get('ReasonOutStr', 'Running')),
                            })
                        except (TypeError, ValueError):
                            continue
                    if parsed_results:
                        info['results_positions'] = parsed_results
        except Exception as e:
            logger.debug("SessionInfo results extraction skipped: %s", e)

        # Resolve player car name from collected drivers
        if 'car_name' not in info and _drivers:
            # Priority: DriverCarIdx match → first non-pace non-AI → first non-pace
            candidate = None
            if _driver_car_idx >= 0:
                candidate = _drivers.get(_driver_car_idx)
            if candidate is None:
                candidate = next((d for d in _drivers.values()
                                  if not d['is_pace'] and not d['is_ai']), None)
            if candidate is None:
                candidate = next((d for d in _drivers.values()
                                  if not d['is_pace']), None)
            if candidate:
                info['car_name'] = candidate['screen_name'] or candidate['path'] or 'Unknown Car'
        return info


    def _extract_yaml_block(self, text: str, key: str) -> Optional[Dict[str, Any]]:
        """
        Extract any top-level YAML block by key name.
        Returns the parsed dict for that block, or None if not found.
        """
        import yaml
        marker = f'\n{key}:'
        start = text.find(marker)
        if start == -1:
            if text.startswith(f'{key}:'):
                start = -1
            else:
                return None
        start = start + 1 if start >= 0 else 0
        lines = text[start:].splitlines()
        block = [lines[0]]
        for line in lines[1:]:
            if line and not line[0].isspace() and ':' in line:
                break
            block.append(line)
        try:
            parsed = yaml.safe_load('\n'.join(block))
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            return None

    def _extract_car_setup(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Extract the CarSetup section from iRacing session YAML.
        Returns a nested dict or None if not found.
        """
        # Locate the CarSetup top-level key
        start = text.find('\nCarSetup:')
        if start == -1:
            if text.startswith('CarSetup:'):
                start = -1   # offset correction below
            else:
                return None
        start = start + 1 if start >= 0 else 0  # skip leading \n

        # Collect lines belonging to CarSetup (until next zero-indented key)
        lines = text[start:].splitlines()
        block = [lines[0]]
        for line in lines[1:]:
            if line and not line[0].isspace() and ':' in line:
                break
            block.append(line)

        # Parse the block with PyYAML (values stay as strings due to units)
        import yaml
        try:
            parsed = yaml.safe_load('\n'.join(block))
        except yaml.YAMLError:
            parsed = None

        if isinstance(parsed, dict):
            return parsed.get('CarSetup')
        return None


def load_demo_data() -> TelemetryData:
    """Generate realistic demo telemetry data for testing."""
    rng = np.random.RandomState(42)
    data = TelemetryData(
        car_name="ferrari_296_gt3",
        track_name="Sebring International Raceway",
        tick_rate=60,
        session_info={
            'track_temp_c': 38.5, 'air_temp_c': 28.0,
            'driver_name': 'Demo Driver', 'session_type': 'Practice',
            'track_length_km': 6.019, 'fuel_capacity_l': 120.0,
            'weather_type': 'Sunny', 'skies': 'Clear',
            'wind_speed_ms': 3.2, 'wind_direction_deg': 180.0,
        },
    )

    num_laps = 8
    samples_per_lap = 5400  # 90 sec * 60 Hz
    total = num_laps * samples_per_lap

    # Track position resets each lap
    lap_dist = np.tile(np.linspace(0, 0.999, samples_per_lap), num_laps)

    # Session time
    session_time = np.linspace(0, num_laps * 90, total)

    # Speed — varies with track position
    base_speed = 50 + 30 * np.sin(lap_dist * 2 * np.pi * 3)
    speed = base_speed + rng.normal(0, 2, total)
    speed = np.clip(speed, 15, 85)

    # Throttle & Brake (inverse of each other, roughly)
    throttle = np.clip(0.5 + 0.5 * np.sin(lap_dist * 2 * np.pi * 6) + rng.normal(0, 0.05, total), 0, 1)
    brake = np.clip(0.5 - 0.5 * np.sin(lap_dist * 2 * np.pi * 6) + rng.normal(0, 0.05, total), 0, 1)
    brake[throttle > 0.3] *= 0.1

    # Steering
    steering = 0.3 * np.sin(lap_dist * 2 * np.pi * 4) + rng.normal(0, 0.02, total)

    # Accelerations
    lat_accel = 1.5 * np.sin(lap_dist * 2 * np.pi * 4) + rng.normal(0, 0.2, total)
    long_accel = -0.8 * brake + 0.5 * throttle + rng.normal(0, 0.1, total)

    # Gear
    gear = np.clip((speed / 15).astype(int), 1, 6)

    # RPM
    rpm = 3000 + speed * 80 + rng.normal(0, 200, total)

    # Fuel (decreasing)
    fuel = np.linspace(45, 45 - num_laps * 3.2, total)

    # Tire temps — realistic ranges
    base_temp = 85
    for corner, offset in [('LF', 0), ('RF', 2), ('LR', -3), ('RR', -1)]:
        inner = base_temp + offset + 5 * np.sin(lap_dist * 2 * np.pi) + rng.normal(0, 1, total)
        mid = base_temp + offset + rng.normal(0, 1, total)
        outer = base_temp + offset - 3 + 3 * np.cos(lap_dist * 2 * np.pi) + rng.normal(0, 1, total)
        data.set_channel(f'{corner}tempCL', inner)
        data.set_channel(f'{corner}tempCM', mid)
        data.set_channel(f'{corner}tempCR', outer)

    # Tire pressures
    for corner, base_psi in [('LF', 24.5), ('RF', 24.5), ('LR', 23.0), ('RR', 23.0)]:
        press = base_psi + rng.normal(0, 0.3, total) + np.linspace(0, 1.5, total)
        data.set_channel(f'{corner}press', press)

    # Shock deflections + velocities (iRacing shockVel is in m/s)
    for corner, stiffness in [('LF', 1.0), ('RF', 1.0), ('LR', 0.9), ('RR', 0.9)]:
        defl = 15 + 10 * np.sin(lap_dist * 2 * np.pi * 5) + rng.normal(0, 2, total)
        # Convert mm gradient → m/s: (mm/sample * Hz) / 1000
        vel  = (np.gradient(defl) * 60) / 1000.0 + rng.normal(0, 0.02, total)
        # Inject kerb spike events (>0.30 m/s threshold)
        for spike_lap in [2, 5]:
            spike_idx = spike_lap * samples_per_lap + samples_per_lap // 3
            if spike_idx < total:
                vel[spike_idx] = 0.55 * stiffness
        data.set_channel(f'{corner}shockDefl', defl)
        data.set_channel(f'{corner}shockVel',  vel)

    # Wheel speeds (slight slip relative to body speed)
    for corner in ['LF', 'RF', 'LR', 'RR']:
        slip_noise = rng.normal(0, 0.02, total)
        wheel_spd = speed * (1 + slip_noise)
        # Inject a lockup event on lap 3
        lockup_start = 3 * samples_per_lap + samples_per_lap // 4
        lockup_end   = lockup_start + 30
        if lockup_end < total:
            wheel_spd[lockup_start:lockup_end] *= 0.7  # locked = slower than car
        data.set_channel(f'{corner}speed', wheel_spd)

    # Roll and Pitch (radians — small angles)
    roll  = 0.04 * np.sin(lat_accel * 0.5) + rng.normal(0, 0.005, total)
    pitch = -0.03 * long_accel / 10.0 + rng.normal(0, 0.003, total)
    data.set_channel('Roll',  roll)
    data.set_channel('Pitch', pitch)

    # Brake bias — one adjustment mid-session
    brake_bias = np.full(total, 0.545)
    mid = total // 2
    brake_bias[mid:] = 0.540
    data.set_channel('dcBrakeBias', brake_bias)

    # VertAccel (for kerb detection) — spikes at lap-dist ~0.3 and ~0.7
    vert_accel = rng.normal(9.81, 0.5, total)
    for lap_i in range(num_laps):
        for pct_offset in [0.3, 0.72]:
            ki = lap_i * samples_per_lap + int(pct_offset * samples_per_lap)
            if ki < total:
                vert_accel[ki] += rng.choice([18.0, 22.0])  # kerb spike
    data.set_channel('VertAccel', vert_accel)

    # PlayerTrackSurface — mostly on-track (5), brief off-track on lap 4
    surface = np.full(total, 5, dtype=float)
    ot_start = 4 * samples_per_lap + samples_per_lap // 2
    surface[ot_start:ot_start + 60] = 1.0   # off-track
    data.set_channel('PlayerTrackSurface', surface)

    # Set core channels
    data.set_channel('LapDistPct', lap_dist)
    data.set_channel('SessionTime', session_time)
    data.set_channel('Speed', speed)
    data.set_channel('Throttle', throttle)
    data.set_channel('Brake', brake)
    data.set_channel('SteeringWheelAngle', steering)
    data.set_channel('LatAccel', lat_accel)
    data.set_channel('LongAccel', long_accel)
    data.set_channel('Gear', gear.astype(float))
    data.set_channel('RPM', rpm)
    data.set_channel('FuelLevel', fuel)

    # Lap data
    data.lap_boundaries = [i * samples_per_lap for i in range(num_laps + 1)]
    base_time = 91.5
    data.lap_times = [base_time + rng.normal(0, 0.4) - i * 0.05 for i in range(num_laps)]
    data.num_laps = num_laps

    return data
