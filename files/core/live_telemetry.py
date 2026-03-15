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
