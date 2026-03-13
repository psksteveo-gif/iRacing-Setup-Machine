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


class IBTParser:
    """Parse iRacing .ibt binary telemetry files."""

    def __init__(self, path: str):
        if not os.path.exists(path):
            raise FileNotFoundError(f"IBT file not found: {path}")
        self.path = path

    def parse(self) -> TelemetryData:
        """Parse an iRacing .ibt binary telemetry file into structured TelemetryData."""
        data = TelemetryData()
        try:
            file_size = os.path.getsize(self.path)
            if file_size > 500 * 1024 * 1024:  # 500 MB
                raise ValueError("IBT file exceeds maximum supported size (500 MB)")
            with open(self.path, 'rb') as f:
                raw = f.read()
            data = self._parse_binary(raw)
        except (ValueError, FileNotFoundError):
            raise
        except Exception as e:
            raise RuntimeError(f"Failed to parse IBT file: {e}")
        return data

    def _parse_binary(self, raw: bytes) -> TelemetryData:
        """Parse iRacing binary telemetry format."""
        data = TelemetryData()

        # iRacing IBT header structure
        if len(raw) < 112:
            raise ValueError("File too small to be a valid IBT file")

        # Read header
        version = struct.unpack_from('i', raw, 0)[0]
        status = struct.unpack_from('i', raw, 4)[0]
        tick_rate = struct.unpack_from('i', raw, 8)[0]
        session_info_offset = struct.unpack_from('i', raw, 12)[0]
        session_info_len = struct.unpack_from('i', raw, 16)[0]
        num_vars = struct.unpack_from('i', raw, 20)[0]
        var_header_offset = struct.unpack_from('i', raw, 24)[0]
        num_buf = struct.unpack_from('i', raw, 28)[0]
        buf_len = struct.unpack_from('i', raw, 32)[0]

        # Validate header offsets are within file bounds
        if session_info_offset < 0 or session_info_len < 0:
            raise ValueError("Invalid session info offset in IBT header")
        if session_info_offset + session_info_len > len(raw):
            raise ValueError("Session info extends beyond end of file")
        if num_vars < 0 or num_vars > 10000:
            raise ValueError("Suspicious number of variables in IBT header")
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
        if num_buf > 0:
            buf_offset_pos = 48
            buf_offset = struct.unpack_from('i', raw, buf_offset_pos)[0]
            total_samples = (len(raw) - buf_offset) // buf_len if buf_len > 0 else 0

            raw_buf = None
            for vh in var_headers:
                try:
                    type_map = {1: ('u1', 1), 2: ('u1', 1), 3: ('<i4', 4),
                                4: ('<u4', 4), 5: ('<f4', 4), 6: ('<f8', 8)}
                    np_dtype, sz = type_map.get(vh['type'], ('<f4', 4))
                    # Build array by reading each sample's value at the correct offset
                    offsets = buf_offset + np.arange(total_samples) * buf_len + vh['offset']
                    # Validate all offsets are within bounds
                    if total_samples > 0 and int(offsets[-1]) + sz > len(raw):
                        continue
                    raw_buf = np.frombuffer(raw, dtype=np.uint8)
                    # Extract bytes for all samples at once using stride tricks
                    byte_indices = (offsets[:, None] + np.arange(sz)[None, :]).ravel()
                    extracted = raw_buf[byte_indices].view(np.uint8).reshape(total_samples, sz)
                    channel_data = np.frombuffer(extracted.tobytes(), dtype=np_dtype).astype(np.float64)
                    data.set_channel(vh['name'], channel_data)
                except (KeyError, IndexError, ValueError, struct.error) as e:
                    logger.debug("Skipping channel %s: %s", vh.get('name', '?'), e)
                    continue
            del raw_buf, raw  # Free large buffers before lap derivation

        # Derive lap data from LapDistPct channel (primary), fallback to SessionTime gaps
        lap_dist = data.get_channel('LapDistPct')
        if lap_dist is not None and len(lap_dist) > 0:
            self._derive_laps(data, lap_dist)
        else:
            # Fallback: try LapCurrentLapTime resets, or SessionTime-based heuristic
            logger.warning("LapDistPct channel missing — using fallback lap detection.")
            self._derive_laps_fallback(data)

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
        for line in text.splitlines():
            line = line.strip()
            if ':' in line:
                key, _, val = line.partition(':')
                key = key.strip().lower().replace(' ', '_')
                val = val.strip()
                if key == 'drivercartpath':
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
        return info


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

    # Shock deflections
    for corner in ['LF', 'RF', 'LR', 'RR']:
        defl = 15 + 10 * np.sin(lap_dist * 2 * np.pi * 5) + rng.normal(0, 2, total)
        data.set_channel(f'{corner}shockDefl', defl)

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
