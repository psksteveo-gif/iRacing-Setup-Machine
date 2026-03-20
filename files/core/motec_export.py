"""
Motec i2 Pro Compatible CSV Export

Exports iRacing telemetry channels to a CSV layout that Motec i2 Pro
can import via File > Import > CSV Data.

Reference format: Motec i2 CSV Import specification (header block + data rows).
"""

import os
import csv
from datetime import datetime
from typing import List, Tuple

from core.ibt_parser import TelemetryData


# (iRacing channel name, unit string, Motec display name)
_CHANNEL_MAP: List[Tuple[str, str, str]] = [
    ('SessionTime',       's',     'Time'),
    ('LapDistPct',        '%',     'Lap Distance Pct'),
    ('Speed',             'm/s',   'Speed'),
    ('Throttle',          '%',     'Throttle Pos'),
    ('Brake',             '%',     'Brake Pos'),
    ('SteeringWheelAngle','rad',   'Steering Angle'),
    ('Gear',              '',      'Gear'),
    ('RPM',               'rpm',   'Engine RPM'),
    ('FuelLevel',         'l',     'Fuel Level'),
    ('LatAccel',          'm/s²',  'Lateral Accel'),
    ('LongAccel',         'm/s²',  'Longitudinal Accel'),
    ('LFtempCL',          '°C',    'LF Tire Temp Inner'),
    ('LFtempCM',          '°C',    'LF Tire Temp Mid'),
    ('LFtempCR',          '°C',    'LF Tire Temp Outer'),
    ('RFtempCL',          '°C',    'RF Tire Temp Inner'),
    ('RFtempCM',          '°C',    'RF Tire Temp Mid'),
    ('RFtempCR',          '°C',    'RF Tire Temp Outer'),
    ('LRtempCL',          '°C',    'LR Tire Temp Inner'),
    ('LRtempCM',          '°C',    'LR Tire Temp Mid'),
    ('LRtempCR',          '°C',    'LR Tire Temp Outer'),
    ('RRtempCL',          '°C',    'RR Tire Temp Inner'),
    ('RRtempCM',          '°C',    'RR Tire Temp Mid'),
    ('RRtempCR',          '°C',    'RR Tire Temp Outer'),
    ('LFpress',           'psi',   'LF Tire Pressure'),
    ('RFpress',           'psi',   'RF Tire Pressure'),
    ('LRpress',           'psi',   'LR Tire Pressure'),
    ('RRpress',           'psi',   'RR Tire Pressure'),
    ('LFshockDefl',       'mm',    'LF Shock Travel'),
    ('RFshockDefl',       'mm',    'RF Shock Travel'),
    ('LRshockDefl',       'mm',    'LR Shock Travel'),
    ('RRshockDefl',       'mm',    'RR Shock Travel'),
]


def export_motec_csv(
    data: TelemetryData,
    path: str,
    lap_idx: int = -1,
) -> str:
    """
    Export telemetry to a Motec i2-compatible CSV file.

    Parameters
    ----------
    data    : TelemetryData from IBTParser
    path    : output .csv file path
    lap_idx : which lap to export; -1 exports the full session

    Returns
    -------
    str : the file path written
    """
    si = data.session_info

    # Determine sample slice
    session_time = data.get_channel('SessionTime')
    total = len(session_time) if session_time is not None else 0
    if total == 0:
        raise ValueError("No telemetry data available to export.")

    if (lap_idx >= 0
            and lap_idx < data.num_laps
            and len(data.lap_boundaries) > lap_idx + 1):
        s = data.lap_boundaries[lap_idx]
        e = data.lap_boundaries[lap_idx + 1]
    else:
        s, e = 0, total

    n = e - s
    if n <= 0:
        raise ValueError("Empty lap slice — nothing to export.")

    # Only include channels that are actually present in this file
    available = [
        (ch, unit, label)
        for ch, unit, label in _CHANNEL_MAP
        if data.get_channel(ch) is not None
    ]

    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    lap_desc = f"Lap {lap_idx + 1}" if lap_idx >= 0 else "Full Session"

    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)

        # ── Motec i2 header block ─────────────────────────────────────────
        w.writerow(['Format', 'Motec i2 Export'])
        w.writerow(['Venue', data.track_name])
        w.writerow(['Vehicle', data.car_name])
        w.writerow(['Driver', si.get('driver_name', 'Unknown')])
        w.writerow(['Session', si.get('session_type', 'Practice')])
        w.writerow(['Comment',
                    f'Exported from Optimal Sector  {timestamp}  {lap_desc}'])
        w.writerow([])

        # ── Channel descriptor rows ───────────────────────────────────────
        w.writerow([''] + [label for _, _, label in available])
        w.writerow(['Units'] + [unit for _, unit, _ in available])
        w.writerow(['Frequency'] + [str(data.tick_rate)] * len(available))
        w.writerow([])

        # ── Data rows ─────────────────────────────────────────────────────
        arrays = [data.get_channel(ch)[s:e] for ch, _, _ in available]
        for i in range(n):
            w.writerow([f'{arr[i]:.6g}' for arr in arrays])

    return path
