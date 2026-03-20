"""
iRacing Setup File Parser & Exporter
Parses .htm setup exports from iRacing garage and writes modified setups back.

iRacing exports setups as HTML tables. We parse these into structured dicts,
allow modifications, and write back a compatible .htm file iRacing can import.
"""

import re
import os
import json
import html as html_mod
import logging
import tempfile
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class SetupSection:
    name: str
    params: Dict[str, str] = field(default_factory=dict)  # param_name -> value string


@dataclass
class ParsedSetup:
    car: str = ""
    track: str = ""
    filename: str = ""
    raw_html: str = ""
    sections: List[SetupSection] = field(default_factory=list)
    flat: Dict[str, str] = field(default_factory=dict)  # flattened key->value
    parsed_at: str = ""

    def get(self, key: str, default: str = "") -> str:
        return self.flat.get(key, default)

    def set(self, key: str, value: str):
        self.flat[key] = value
        for sec in self.sections:
            if key in sec.params:
                sec.params[key] = value
                return

    def to_dict(self) -> dict:
        return {
            'car': self.car,
            'track': self.track,
            'filename': self.filename,
            'sections': [{'name': s.name, 'params': s.params} for s in self.sections],
            'parsed_at': self.parsed_at,
        }


class SetupParser:
    """Parse iRacing .htm setup export files."""

    MAX_SETUP_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

    def parse_file(self, filepath: str) -> ParsedSetup:
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Setup file not found: {filepath}")
        file_size = os.path.getsize(filepath)
        if file_size > self.MAX_SETUP_FILE_SIZE:
            raise ValueError("Setup file exceeds maximum supported size (10 MB)")
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                html = f.read()
        except PermissionError:
            raise PermissionError(f"Cannot read setup file — it may be locked by iRacing: {filepath}")
        except OSError as e:
            raise OSError(f"Could not read setup file: {e}")
        return self.parse_html(html, filepath)

    def parse_html(self, html: str, filepath: str = "") -> ParsedSetup:
        setup = ParsedSetup(
            filename=os.path.basename(filepath),
            raw_html=html,
            parsed_at=datetime.now().isoformat(),
        )

        # Extract car and track from title or headers
        title_match = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
        if title_match:
            title = self._strip_tags(title_match.group(1))
            setup.car = title.strip()

        # Find track info
        track_match = re.search(r'Track[:\s]+([^\n<]+)', html, re.IGNORECASE)
        if track_match:
            setup.track = track_match.group(1).strip()

        # Parse all tables in the HTML
        table_pattern = re.compile(r'<table[^>]*>(.*?)</table>', re.DOTALL | re.IGNORECASE)
        row_pattern = re.compile(r'<tr[^>]*>(.*?)</tr>', re.DOTALL | re.IGNORECASE)
        cell_pattern = re.compile(r'<t[dh][^>]*>(.*?)</t[dh]>', re.DOTALL | re.IGNORECASE)
        heading_pattern = re.compile(r'<h[1-4][^>]*>(.*?)</h[1-4]>', re.DOTALL | re.IGNORECASE)

        current_section = None
        sections = []

        # Get all headings and tables in document order
        elements = []
        for m in re.finditer(r'(<h[1-4][^>]*>.*?</h[1-4]>|<table[^>]*>.*?</table>)', html, re.DOTALL | re.IGNORECASE):
            elements.append((m.start(), m.group(0)))

        for _, elem in elements:
            if re.match(r'<h[1-4]', elem, re.IGNORECASE):
                section_name = self._strip_tags(elem).strip()
                if section_name:
                    current_section = SetupSection(name=section_name)
                    sections.append(current_section)
            else:
                # It's a table
                if current_section is None:
                    current_section = SetupSection(name="General")
                    sections.append(current_section)

                rows = row_pattern.findall(elem)
                for row in rows:
                    cells = [self._strip_tags(c).strip() for c in cell_pattern.findall(row)]
                    cells = [c for c in cells if c]  # remove empty
                    if len(cells) >= 2:
                        key = cells[0]
                        val = cells[1]
                        if key and not key.lower().startswith('parameter'):
                            current_section.params[key] = val
                            setup.flat[key] = val

        # If no structured sections found, do a flat key:value extraction
        if not sections:
            sections = self._flat_extract(html)
            for sec in sections:
                setup.flat.update(sec.params)

        setup.sections = sections

        # Try to extract car name from setup parameters
        for key in ['Car', 'CarPath', 'CarName']:
            if key in setup.flat:
                setup.car = setup.flat[key]
                break

        return setup

    def _flat_extract(self, html: str) -> List[SetupSection]:
        """Fallback: extract all visible text key-value pairs."""
        sec = SetupSection(name="Setup Parameters")
        text = self._strip_tags(html)
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        for i in range(len(lines) - 1):
            line = lines[i]
            if ':' in line:
                k, _, v = line.partition(':')
                sec.params[k.strip()] = v.strip()
        return [sec]

    def _strip_tags(self, html: str) -> str:
        return re.sub(r'<[^>]+>', '', html).replace('&nbsp;', ' ').replace('&amp;', '&').strip()


def _probe_writable(dirname: str) -> None:
    """
    Confirm a directory is writable before attempting a full export.
    Raises PermissionError with a user-friendly message if not.
    """
    probe = os.path.join(dirname, ".writetest_optisector")
    try:
        with open(probe, "w") as f:
            f.write("")
        os.unlink(probe)
    except PermissionError:
        raise PermissionError(
            f"Cannot write to this folder — it may be read-only or locked by iRacing:\n{dirname}"
        )
    except OSError as e:
        raise OSError(f"Cannot write to export folder: {e}")


class SetupExporter:
    """
    Export a ParsedSetup back to iRacing-compatible .htm format.
    Also supports JSON export for history tracking.
    """

    def export_htm(self, setup: ParsedSetup, output_path: str, changes: Optional[Dict[str, str]] = None):
        """
        Write a setup .htm file. If changes dict provided, applies them first.
        """
        if changes:
            for k, v in changes.items():
                setup.set(k, v)

        html = self._generate_html(setup)
        dirname = os.path.dirname(output_path) or '.'
        os.makedirs(dirname, exist_ok=True)
        _probe_writable(dirname)
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8',
                                             dir=dirname, delete=False, suffix='.tmp') as tmp:
                tmp.write(html)
                tmp_path = tmp.name
            os.replace(tmp_path, output_path)
        except PermissionError:
            raise PermissionError(
                f"Cannot write setup file — the destination may be locked or read-only:\n{output_path}")
        except OSError as e:
            raise OSError(f"Could not write setup file: {e}")
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
        logger.info("Setup exported (htm): %s", output_path)
        return output_path

    def export_json(self, setup: ParsedSetup, output_path: str):
        """Export setup as JSON for history tracking."""
        dirname = os.path.dirname(output_path) or '.'
        os.makedirs(dirname, exist_ok=True)
        _probe_writable(dirname)
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8',
                                             dir=dirname, delete=False, suffix='.tmp') as tmp:
                json.dump(setup.to_dict(), tmp, indent=2)
                tmp_path = tmp.name
            os.replace(tmp_path, output_path)
        except PermissionError:
            raise PermissionError(
                f"Cannot write setup JSON — destination may be read-only:\n{output_path}")
        except OSError as e:
            raise OSError(f"Could not write setup JSON: {e}")
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
        logger.info("Setup exported (json): %s", output_path)

    def _generate_html(self, setup: ParsedSetup) -> str:
        """Generate a clean HTML setup file compatible with iRacing import."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        esc = html_mod.escape
        sections_html = ""
        for sec in setup.sections:
            if not sec.params:
                continue
            rows = ""
            for param, val in sec.params.items():
                rows += f"""
        <tr>
          <td class="param">{esc(param)}</td>
          <td class="value">{esc(val)}</td>
        </tr>"""
            sections_html += f"""
  <h3>{esc(sec.name)}</h3>
  <table>
    <tr><th>Parameter</th><th>Value</th></tr>{rows}
  </table>"""

        return f"""<!DOCTYPE html>
<html>
<head>
  <title>{esc(setup.car)} Setup</title>
  <meta charset="utf-8">
  <style>
    body {{ font-family: Arial, sans-serif; font-size: 12px; background: #fff; color: #000; margin: 20px; }}
    h2 {{ color: #c00; border-bottom: 2px solid #c00; padding-bottom: 4px; }}
    h3 {{ color: #333; margin-top: 16px; border-bottom: 1px solid #ccc; }}
    table {{ border-collapse: collapse; width: 100%; margin-bottom: 12px; }}
    th {{ background: #333; color: #fff; padding: 4px 8px; text-align: left; }}
    td {{ padding: 3px 8px; border-bottom: 1px solid #eee; }}
    td.param {{ color: #555; width: 55%; }}
    td.value {{ font-weight: bold; color: #000; }}
    tr:hover td {{ background: #f5f5f5; }}
    .meta {{ color: #888; font-size: 11px; margin-bottom: 16px; }}
  </style>
</head>
<body>
  <h2>{esc(setup.car)} — Setup Sheet</h2>
  <p class="meta">Track: {esc(setup.track)} &nbsp;|&nbsp; Generated: {esc(now)} &nbsp;|&nbsp; Optimal Sector</p>
  {sections_html}
</body>
</html>"""


class StoWriter:
    """
    Write a ParsedSetup as a native iRacing .sto file.

    iRacing .sto files are YAML-like structured text files used internally by
    the iRacing simulator.  The format is:

        CarCode=<car_code>
        TrackName=<track_name>
        SetupName=<name>
        <SectionName>:
         <param>=<value>
         ...

    Because the exact binary structure varies by car, this writer produces a
    "portable text .sto" — a valid human-readable format iRacing accepts when
    placed in the correct garage folder.

    Usage::
        writer = StoWriter()
        path = writer.write(setup, "/path/to/setups/mysetup.sto")
    """

    def write(
        self,
        setup: ParsedSetup,
        output_path: str,
        setup_name: Optional[str] = None,
        changes: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        Write the setup to *output_path* as a .sto file.
        If *changes* is provided, those key→value pairs are applied before writing.
        Returns the output path.
        """
        if changes:
            for k, v in changes.items():
                setup.set(k, v)

        content = self._generate_sto(setup, setup_name)
        dirname = os.path.dirname(os.path.abspath(output_path))
        os.makedirs(dirname, exist_ok=True)
        _probe_writable(dirname)
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', newline="\n",
                                             dir=dirname, delete=False, suffix='.tmp') as tmp:
                tmp.write(content)
                tmp_path = tmp.name
            os.replace(tmp_path, output_path)
        except PermissionError:
            raise PermissionError(
                f"Cannot write .sto file — destination may be locked by iRacing:\n{output_path}")
        except OSError as e:
            raise OSError(f"Could not write .sto file: {e}")
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
        logger.info("Setup exported (sto): %s", output_path)
        return output_path

    def _generate_sto(self, setup: ParsedSetup, setup_name: Optional[str] = None) -> str:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        name = setup_name or (
            os.path.splitext(os.path.basename(setup.filename))[0] if setup.filename else "setup"
        )
        lines: list[str] = [
            f"# iRacing Setup — generated by Optimal Sector",
            f"# {now}",
            f"",
            f"CarCode={self._sanitise(setup.car)}",
            f"TrackName={self._sanitise(setup.track)}",
            f"SetupName={self._sanitise(name)}",
            f"",
        ]

        for sec in setup.sections:
            if not sec.params:
                continue
            # Section header
            lines.append(f"{self._sanitise(sec.name)}:")
            for param, value in sec.params.items():
                safe_param = self._sanitise(param)
                safe_val = self._sanitise(str(value))
                lines.append(f" {safe_param}={safe_val}")
            lines.append("")

        return "\n".join(lines)

    @staticmethod
    def _sanitise(s: str) -> str:
        """Strip characters that break the .sto format."""
        return re.sub(r"[\r\n\x00]", " ", str(s)).strip()

    @staticmethod
    def default_sto_path(setup: ParsedSetup, base_dir: Optional[str] = None) -> str:
        """
        Return the default iRacing garage setups folder path for a given setup.
        Uses Windows registry to locate iRacing documents folder (handles D: drives,
        OneDrive redirects, and custom install paths).
        """
        car = re.sub(r"[^\w\-_]", "_", setup.car or "car").lower()
        if base_dir is None:
            from core.file_watcher import _get_iracing_docs
            base_dir = os.path.join(_get_iracing_docs(), "setups", car)
        os.makedirs(base_dir, exist_ok=True)
        stem = re.sub(r"[^\w\-_ ]", "_", setup.filename or "setup").rstrip(".htmHTM").strip("_")
        if not stem:
            stem = "exported_setup"
        return os.path.join(base_dir, f"{stem}.sto")


class SetupDiffer:
    """Compare two setups and return a list of changed parameters."""

    def diff(self, setup_a: ParsedSetup, setup_b: ParsedSetup) -> List[Dict]:
        changes = []
        all_keys = set(setup_a.flat.keys()) | set(setup_b.flat.keys())
        for key in sorted(all_keys):
            val_a = setup_a.flat.get(key, "—")
            val_b = setup_b.flat.get(key, "—")
            if val_a != val_b:
                changes.append({
                    'param': key,
                    'before': val_a,
                    'after': val_b,
                })
        return changes


def create_demo_setup(car: str = "ferrari_296_gt3", track: str = "Sebring") -> ParsedSetup:
    """Generate a realistic demo setup for testing."""
    setup = ParsedSetup(car=car, track=track, filename="demo_setup.htm",
                        parsed_at=datetime.now().isoformat())

    setup.sections = [
        SetupSection("Tires", {
            "LF Cold Pressure": "30.5 psi",
            "RF Cold Pressure": "30.5 psi",
            "LR Cold Pressure": "29.0 psi",
            "RR Cold Pressure": "29.0 psi",
        }),
        SetupSection("Alignment", {
            "LF Camber":       "-3.0 deg",
            "RF Camber":       "-3.0 deg",
            "LR Camber":       "-1.8 deg",
            "RR Camber":       "-1.8 deg",
            "Front Toe":       "0.0 mm (toe-out)",
            "Rear Toe":        "+1.5 mm (toe-in)",
        }),
        SetupSection("Suspension", {
            "LF Spring Rate":  "80 N/mm",
            "RF Spring Rate":  "80 N/mm",
            "LR Spring Rate":  "70 N/mm",
            "RR Spring Rate":  "70 N/mm",
            "Front ARB":       "Medium (4/7)",
            "Rear ARB":        "Medium-stiff (5/7)",
            "LF Ride Height":  "62 mm",
            "RF Ride Height":  "62 mm",
            "LR Ride Height":  "78 mm",
            "RR Ride Height":  "78 mm",
            "LF Slow Bump":    "6 clicks",
            "RF Slow Bump":    "6 clicks",
            "LR Slow Bump":    "5 clicks",
            "RR Slow Bump":    "5 clicks",
            "LF Fast Bump":    "4 clicks",
            "RF Fast Bump":    "4 clicks",
            "LR Fast Bump":    "3 clicks",
            "RR Fast Bump":    "3 clicks",
            "LF Slow Rebound": "8 clicks",
            "RF Slow Rebound": "8 clicks",
            "LR Slow Rebound": "7 clicks",
            "RR Slow Rebound": "7 clicks",
        }),
        SetupSection("Aerodynamics", {
            "Front Wing Angle": "5 / 10",
            "Rear Wing Angle":  "5 / 10",
            "Brake Duct (Front)": "50%",
            "Brake Duct (Rear)":  "30%",
        }),
        SetupSection("Brakes", {
            "Brake Bias":       "55.0% front",
            "Brake Pressure":   "95%",
            "ABS Setting":      "4",
        }),
        SetupSection("Differential", {
            "Diff Preload":     "50 Nm",
            "Coast Ramp":       "0 deg",
            "Power Ramp":       "45 deg",
        }),
    ]

    for sec in setup.sections:
        setup.flat.update(sec.params)

    return setup


# ── Label helpers ─────────────────────────────────────────────────────────────

# CamelCase → human label overrides for known iRacing parameter names
_LABEL_MAP = {
    'ArbSetting':        'ARB Setting',
    'AbsSetting':        'ABS Setting',
    'TcSetting':         'TC Setting',
    'ToeIn':             'Toe-in',
    'SpringPerchOffset': 'Spring Perch Offset',
    'RideHeight':        'Ride Height',
    'CornerWeight':      'Corner Weight',
    'StartingPressure':  'Starting Pressure',
    'LastHotPressure':   'Last Hot Pressure',
    'TreadRemaining':    'Tread Remaining',
    'LastTempsOMI':      'Last Temps O-M-I',
    'LastTempsIMO':      'Last Temps I-M-O',
    'BrakePressureBias': 'Brake Pressure Bias',
    'CrossWeight':       'Cross Weight',
    'ThrottleSetting':   'Throttle Setting',
    'DisplayPage':       'Display Page',
    'TcMode':            'TC Mode',
    'FrontBrakePadMu':   'Brake Pad Mu',   # section prefix already says Front
    'RearBrakePadMu':    'Brake Pad Mu',   # section prefix already says Rear
    'FuelLevel':         'Fuel Level',
    'FuelLowWarning':    'Fuel Low Warning',
    'FrontWeight':       'Weight',
    'WingAngle':         'Wing Angle',
    'TireType':          'Tire Type',
    'Camber':            'Camber',
    'UpdateCount':       None,   # skip this key
}

_SECTION_PREFIX = {
    'Front':      'Front',
    'LeftFront':  'LF',
    'RightFront': 'RF',
    'LeftRear':   'LR',
    'RightRear':  'RR',
    'InCarDials': '',
    'Rear':       'Rear',
}

_SECTION_LABEL = {
    'Front':      'Front',
    'LeftFront':  'Left Front',
    'RightFront': 'Right Front',
    'LeftRear':   'Left Rear',
    'RightRear':  'Right Rear',
    'InCarDials': 'In-Car Dials',
    'Rear':       'Rear',
}


def _ibt_key_label(camel: str, prefix: str) -> Optional[str]:
    """Convert a CamelCase IBT key + prefix to a display label, or None to skip."""
    label = _LABEL_MAP.get(camel)
    if label is None and camel in _LABEL_MAP:
        return None   # explicit skip
    if label is None:
        # Generic CamelCase → spaced title
        label = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', camel)
    if prefix:
        return f"{prefix} {label}"
    return label


def parsed_setup_from_ibt(car_setup: dict,
                           car_name: str = '',
                           track_name: str = '') -> 'ParsedSetup':
    """
    Convert an IBT CarSetup dict (from ibt_parser session_info['car_setup'])
    into a ParsedSetup with sections matching the iRacing garage layout.
    """
    setup = ParsedSetup(
        car=car_name,
        track=track_name,
        filename='(loaded from IBT telemetry)',
        parsed_at=datetime.now().isoformat(),
    )

    # ── Tires ──────────────────────────────────────────────────────────────
    tires = car_setup.get('Tires', {})
    if tires:
        tire_params: Dict[str, str] = {}
        # Tire type first
        tt = tires.get('TireType', {})
        if isinstance(tt, dict) and tt.get('TireType'):
            tire_params['Tire Type'] = str(tt['TireType'])
        elif isinstance(tt, str):
            tire_params['Tire Type'] = tt
        # Per-corner data
        for corner_key, prefix in [('LeftFront','LF'), ('RightFront','RF'),
                                    ('LeftRear','LR'), ('RightRear','RR')]:
            corner = tires.get(corner_key, {})
            if not isinstance(corner, dict):
                continue
            for k, v in corner.items():
                lbl = _LABEL_MAP.get(k) or re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', k)
                if lbl:
                    tire_params[f"{prefix} {lbl}"] = str(v)
        if tire_params:
            sec = SetupSection('Tires', tire_params)
            setup.sections.append(sec)
            setup.flat.update(tire_params)

    # ── Chassis ────────────────────────────────────────────────────────────
    chassis = car_setup.get('Chassis', {})
    if isinstance(chassis, dict):
        section_order = ['Front', 'LeftFront', 'RightFront',
                         'InCarDials', 'LeftRear', 'RightRear', 'Rear']
        for sec_key in section_order:
            sec_data = chassis.get(sec_key, {})
            if not isinstance(sec_data, dict) or not sec_data:
                continue
            prefix = _SECTION_PREFIX.get(sec_key, sec_key)
            params: Dict[str, str] = {}
            for k, v in sec_data.items():
                label = _ibt_key_label(k, prefix)
                if label:
                    params[label] = str(v)
            if params:
                sec_label = _SECTION_LABEL.get(sec_key, sec_key)
                sec = SetupSection(sec_label, params)
                setup.sections.append(sec)
                setup.flat.update(params)

    return setup


if __name__ == "__main__":
    setup = create_demo_setup()
    print(f"Car: {setup.car}")
    print(f"Track: {setup.track}")
    for sec in setup.sections:
        print(f"\n--- {sec.name} ---")
        for k, v in sec.params.items():
            print(f"  {k}: {v}")
