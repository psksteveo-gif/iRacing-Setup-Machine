"""
Live Telemetry Monitor — connects to iRacing shared memory via pyirsdk.
Provides real-time telemetry data during active iRacing sessions.

Requires: pip install pyirsdk
"""

import threading
import logging
from dataclasses import dataclass, field
from typing import Optional, Callable, Dict, List

logger = logging.getLogger(__name__)


@dataclass
class LiveSample:
    """A single live telemetry snapshot from iRacing shared memory."""
    speed_ms: float = 0.0
    speed_kph: float = 0.0
    rpm: float = 0.0
    gear: int = 0
    throttle: float = 0.0
    brake: float = 0.0
    steering: float = 0.0
    fuel_level: float = 0.0
    fuel_pct: float = 0.0
    lap_dist_pct: float = 0.0
    lap: int = 0
    lap_time: float = 0.0
    last_lap: float = 0.0
    best_lap: float = 0.0
    session_time: float = 0.0
    session_remaining: float = -1.0
    lat_accel: float = 0.0
    long_accel: float = 0.0
    tire_temps: Dict[str, Dict[str, float]] = field(default_factory=dict)
    tire_pressures: Dict[str, float] = field(default_factory=dict)
    tire_wear: Dict[str, float] = field(default_factory=dict)
    # Track conditions
    track_temp_c: float = 0.0
    air_temp_c: float = 0.0
    # Live sector deltas
    lap_delta_to_best: float = 0.0
    lap_delta_to_optimal: float = 0.0
    lap_delta_valid: bool = False
    # Suspension travel (meters)
    shock_defl: Dict[str, float] = field(default_factory=dict)   # LF/RF/LR/RR
    shock_vel: Dict[str, float] = field(default_factory=dict)    # damper velocity m/s
    # Wheel slip angles (radians, + = understeer)
    slip_angle: Dict[str, float] = field(default_factory=dict)
    # Brake line pressures (Pa)
    brake_line_press: Dict[str, float] = field(default_factory=dict)
    # Tire wear (0=new, 1=worn) per zone
    tire_wear_detail: Dict[str, Dict[str, float]] = field(default_factory=dict)
    # Race position
    car_position: int = 0
    car_class_position: int = 0
    session_laps_remain: int = -1
    # All cars track position (for traffic detection)
    car_idx_lap_dist: Dict[int, float] = field(default_factory=dict)
    car_idx_lap: Dict[int, int] = field(default_factory=dict)
    # Driver coaching
    brake_bias_pct: float = 0.0
    tc_level: int = 0
    abs_level: int = 0
    shift_rpm: float = 0.0
    blink_rpm: float = 0.0
    shift_grind_rpm: float = 0.0
    steering_torque: float = 0.0
    clutch_pct: float = 0.0
    is_on_track: bool = False
    is_in_garage: bool = False
    # Driver inputs quality
    brake_abs_active: bool = False
    tc_active: bool = False
    is_connected: bool = False
    car_name: str = ""
    track_name: str = ""


class LiveTelemetryMonitor:
    """
    Polls iRacing shared memory at ~10 Hz and delivers LiveSample snapshots
    to registered callbacks.

    Usage::

        mon = LiveTelemetryMonitor()
        mon.add_callback(my_fn)   # my_fn(sample: LiveSample)
        mon.start()
        ...
        mon.stop()

    If pyirsdk is not installed, start() will immediately deliver a single
    disconnected sample and exit the worker thread gracefully.
    """

    def __init__(self, poll_hz: float = 10.0):
        self._callbacks: List[Callable[[LiveSample], None]] = []
        self._poll_interval = 1.0 / max(poll_hz, 1.0)
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._connected = False
        self._ir = None
        self._last_sample: Optional[LiveSample] = None
        self._sdk_missing = False  # set True if pyirsdk import fails

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def last_sample(self) -> Optional[LiveSample]:
        return self._last_sample

    @property
    def sdk_missing(self) -> bool:
        return self._sdk_missing

    def add_callback(self, fn: Callable[[LiveSample], None]):
        if fn not in self._callbacks:
            self._callbacks.append(fn)

    def remove_callback(self, fn: Callable[[LiveSample], None]):
        self._callbacks = [f for f in self._callbacks if f is not fn]

    def start(self):
        if self.is_running:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="LiveTelemetry")
        self._thread.start()
        logger.info("Live telemetry monitor started.")

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=3.0)
        self._connected = False
        logger.info("Live telemetry monitor stopped.")

    # ── Worker ────────────────────────────────────────────────────────────────

    def _run(self):
        try:
            import irsdk
        except ImportError:
            logger.warning(
                "pyirsdk not installed — live telemetry unavailable. "
                "Install with: pip install pyirsdk"
            )
            self._sdk_missing = True
            self._deliver(LiveSample(is_connected=False))
            return

        ir = irsdk.IRSDK()
        ir.startup()
        self._ir = ir
        prev_connected = False

        while not self._stop_event.is_set():
            try:
                ir.freeze_var_buffer_latest()
                connected = bool(ir.is_connected)
                if connected != prev_connected:
                    prev_connected = connected
                    self._connected = connected
                    if not connected:
                        self._deliver(LiveSample(is_connected=False))
                if connected:
                    sample = self._build_sample(ir)
                    self._last_sample = sample
                    self._deliver(sample)
            except Exception as e:
                logger.debug("Live telemetry read error: %s", e)
            self._stop_event.wait(self._poll_interval)

        try:
            ir.shutdown()
        except Exception:
            pass

    def _build_sample(self, ir) -> LiveSample:
        def g(key, default=0.0):
            try:
                v = ir[key]
                return v if v is not None else default
            except Exception:
                return default

        speed = float(g('Speed'))
        sample = LiveSample(
            speed_ms=speed,
            speed_kph=speed * 3.6,
            rpm=float(g('RPM')),
            gear=int(g('Gear', 0)),
            throttle=float(g('Throttle')),
            brake=float(g('Brake')),
            steering=float(g('SteeringWheelAngle')),
            fuel_level=float(g('FuelLevel')),
            fuel_pct=float(g('FuelLevelPct')),
            lap_dist_pct=float(g('LapDistPct')),
            lap=int(g('Lap', 0)),
            lap_time=float(g('LapCurrentLapTime')),
            last_lap=float(g('LapLastLapTime')),
            best_lap=float(g('LapBestLapTime')),
            session_time=float(g('SessionTime')),
            session_remaining=float(g('SessionTimeRemain', -1.0)),
            lat_accel=float(g('LatAccel')),
            long_accel=float(g('LongAccel')),
            is_connected=True,
        )

        for corner in ['LF', 'RF', 'LR', 'RR']:
            sample.tire_temps[corner] = {
                'inner': float(g(f'{corner}tempCL')),
                'mid':   float(g(f'{corner}tempCM')),
                'outer': float(g(f'{corner}tempCR')),
            }
            sample.tire_pressures[corner] = float(g(f'{corner}press'))
            # Tire wear (0.0 = new, 1.0 = fully worn)
            sample.tire_wear[corner] = float(g(f'{corner}wearL', 0.0))

        # Track conditions
        sample.track_temp_c = float(g('TrackTempCrew', 0.0))
        sample.air_temp_c   = float(g('AirTemp', 0.0))

        # Live sector delta channels
        sample.lap_delta_to_best    = float(g('LapDeltaToBestLap', 0.0))
        sample.lap_delta_to_optimal = float(g('LapDeltaToOptimalLap', 0.0))
        sample.lap_delta_valid      = bool(g('LapDeltaToBestLapOK', 0.0))

        # ── TIER 1: Suspension travel + damper velocity ─────────────────────
        for _c, _key in [('LF','LF'), ('RF','RF'), ('LR','LR'), ('RR','RR')]:
            sample.shock_defl[_c] = float(g(f'{_key}shockDefl', 0.0))
            sample.shock_vel[_c]  = float(g(f'{_key}shockVel', 0.0))

        # Wheel slip angles
        for _c, _key in [('LF','LF'), ('RF','RF'), ('LR','LR'), ('RR','RR')]:
            sample.slip_angle[_c] = float(g(f'WheelSlipAngle_{_key}', 0.0))

        # Brake line pressures
        for _c, _key in [('LF','LF'), ('RF','RF'), ('LR','LR'), ('RR','RR')]:
            sample.brake_line_press[_c] = float(g(f'{_key}brakeLinePress', 0.0))

        # Tire wear per zone
        for _c, _key in [('LF','LF'), ('RF','RF'), ('LR','LR'), ('RR','RR')]:
            sample.tire_wear_detail[_c] = {
                'L': float(g(f'{_key}wearL', 0.0)),
                'M': float(g(f'{_key}wearM', 0.0)),
                'R': float(g(f'{_key}wearR', 0.0)),
            }

        # ── TIER 2: Race position + strategy ───────────────────────────────
        sample.car_position       = int(g('PlayerCarPosition', 0))
        sample.car_class_position = int(g('PlayerCarClassPosition', 0))
        sample.session_laps_remain = int(g('SessionLapsRemain', -1))

        # All car track positions (traffic detection)
        try:
            _all_dist = ir['CarIdxLapDistPct']
            _all_laps = ir['CarIdxLapCompleted']
            if _all_dist is not None:
                for _i, _d in enumerate(_all_dist):
                    if _d is not None and _d >= 0:
                        sample.car_idx_lap_dist[_i] = float(_d)
            if _all_laps is not None:
                for _i, _l in enumerate(_all_laps):
                    if _l is not None:
                        sample.car_idx_lap[_i] = int(_l)
        except Exception:
            pass

        # ── TIER 3: Driver coaching channels ───────────────────────────────
        sample.brake_bias_pct   = float(g('dcBrakeBias', 0.0)) * 100.0
        sample.tc_level         = int(g('dcTractionControl', 0))
        sample.abs_level        = int(g('dcABS', 0))
        sample.shift_rpm        = float(g('PlayerCarSLShiftRPM', 0.0))
        sample.blink_rpm        = float(g('PlayerCarSLBlinkRPM', 0.0))
        sample.shift_grind_rpm  = float(g('ShiftGrindRPM', 0.0))
        sample.steering_torque  = float(g('SteeringWheelTorque', 0.0))
        sample.clutch_pct       = float(g('ClutchPct', 0.0))
        sample.is_on_track      = bool(g('IsOnTrackCar', 0))
        sample.is_in_garage     = bool(g('IsInGarage', 0))

        # Aid activity
        sample.brake_abs_active = bool(g('BrakeABSactive', 0))
        sample.tc_active        = bool(g('dcTractionControl', 0) > 0 and
                                       g('ThrottleRaw', g('Throttle')) > g('Throttle') + 0.02)

        try:
            si = ir.session_info
            if si:
                sample.car_name = (
                    si.get('DriverInfo', {})
                      .get('Drivers', [{}])[0]
                      .get('CarPath', '')
                )
                sample.track_name = (
                    si.get('WeekendInfo', {})
                      .get('TrackDisplayName', '')
                )
        except Exception:
            pass

        return sample

    def _deliver(self, sample: LiveSample):
        for fn in list(self._callbacks):
            try:
                fn(sample)
            except Exception as e:
                logger.debug("Live callback error: %s", e)


# ── Fuel tracker ──────────────────────────────────────────────────────────────

class FuelTracker:
    """
    Tracks per-lap fuel consumption from live SDK samples and estimates
    how many laps of fuel remain.

    Feed every LiveSample into update(); call laps_remaining() whenever needed.
    """

    _MAX_HISTORY = 5      # rolling window of lap fuel readings

    def __init__(self):
        self._lap_fuel: list[float] = []   # per-lap fuel consumed (litres)
        self._prev_fuel: float = -1.0
        self._prev_lap: int = -1

    def update(self, sample: LiveSample) -> None:
        """Call with every incoming LiveSample."""
        if not sample.is_connected:
            return
        lap = sample.lap
        fuel = sample.fuel_level
        # Detect lap crossing: lap number incremented
        if self._prev_lap > 0 and lap > self._prev_lap and self._prev_fuel > 0:
            used = self._prev_fuel - fuel
            if 0.05 < used < 25.0:     # sanity bounds (litres)
                self._lap_fuel.append(used)
                if len(self._lap_fuel) > self._MAX_HISTORY:
                    self._lap_fuel.pop(0)
        self._prev_lap = lap
        self._prev_fuel = fuel

    @property
    def avg_per_lap(self) -> float:
        """Average fuel consumption per lap (litres). 0.0 if not enough data."""
        return sum(self._lap_fuel) / len(self._lap_fuel) if self._lap_fuel else 0.0

    @property
    def laps_recorded(self) -> int:
        return len(self._lap_fuel)

    def laps_remaining(self, fuel_level: float) -> float:
        """Estimated laps remaining at current consumption rate."""
        avg = self.avg_per_lap
        if avg <= 0 or fuel_level <= 0:
            return 0.0
        return fuel_level / avg

    def reset(self) -> None:
        self._lap_fuel.clear()
        self._prev_fuel = -1.0
        self._prev_lap = -1
