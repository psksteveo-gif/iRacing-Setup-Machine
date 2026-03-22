"""
Setup Recommendation Engine

Finds the best matching .sto base setup from the user's iRacing setups folder,
copies it as the starting point, and builds a human-readable adjustment checklist
from optimizer results so the user knows exactly what to change in the garage.
"""

import os
import glob
import shutil
import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict


# ── Parameter display mapping ─────────────────────────────────────────────────
# Maps optimizer parameter keys → (garage label, unit, effect hint)
# Labels match the exact text shown in the iRacing garage UI.
PARAM_DISPLAY = {
    'rear_wing':         ('Wing angle',              'click',  'Garage → Rear section. Higher = more rear downforce & drag, more understeer'),
    'front_wing':        ('Front wing angle',        'click',  'Garage → Front section. Higher = more front downforce, less understeer'),
    'rear_spring':       ('Rear Spring perch offset','click',  'Garage → Left/Right Rear. Higher offset = effectively stiffer, less rear grip'),
    'front_spring':      ('Front Spring perch offset','click', 'Garage → Left/Right Front. Higher offset = effectively stiffer, less front grip'),
    'rear_arb':          ('Rear ARB setting',        'click',  'Garage → Rear section. Higher = stiffer rear ARB, more oversteer'),
    'front_arb':         ('Front ARB setting',       'click',  'Garage → Front section. Higher = stiffer front ARB, more understeer'),
    'tire_pressure':     ('Starting pressure',        'psi',    'Garage → Tires tab. Adjust all four corners. Higher = less grip, quicker warm-up'),
    'ride_height_rear':  ('Rear Ride height',        'click',  'Garage → Left/Right Rear. Higher = more rear ride height, less rear aero'),
    'ride_height_front': ('Front Ride height',       'click',  'Garage → Left/Right Front. Higher = more front ride height, less front aero'),
    'brake_bias':        ('Brake pressure bias',     '%',      'Garage → In-Car Dials. Higher % = more front braking, risk of front lock'),
    'tc_level':          ('TC setting',              'level',  'Garage → In-Car Dials. Higher = more traction control intervention on exit'),
    'abs_level':         ('ABS setting',             'level',  'Garage → In-Car Dials. Higher = more ABS intervention under braking'),
}


@dataclass
class ChecklistItem:
    parameter: str        # optimizer key e.g. 'front_arb'
    label: str            # garage label e.g. 'Front ARB Setting'
    delta: float          # signed change amount
    unit: str             # 'click', 'psi', 'mm', '%', 'level'
    hint: str             # one-line effect description
    direction: str        # 'increase' | 'decrease'
    display: str          # formatted delta e.g. '+2 clicks'
    current_value: str = ''      # current value from IBT e.g. '1'
    recommended_value: str = ''  # recommended value e.g. '2'
    affects_keys: List[str] = None

    def __post_init__(self):
        if self.affects_keys is None:
            self.affects_keys = []


# Maps optimizer parameter keys → flat-dict keys produced by parsed_setup_from_ibt
PARAM_TO_SETUP_KEYS: Dict[str, List[str]] = {
    'front_arb':         ['Front ARB Setting'],
    'rear_arb':          ['Rear ARB Setting'],
    'front_spring':      ['LF Spring Perch Offset', 'RF Spring Perch Offset'],
    'rear_spring':       ['LR Spring Perch Offset', 'RR Spring Perch Offset'],
    'tire_pressure':     ['LF Starting Pressure', 'RF Starting Pressure',
                          'LR Starting Pressure', 'RR Starting Pressure'],
    'ride_height_front': ['LF Ride Height', 'RF Ride Height'],
    'ride_height_rear':  ['LR Ride Height', 'RR Ride Height'],
    'brake_bias':        ['Brake Pressure Bias'],
    'tc_level':          ['TC Setting'],
    'abs_level':         ['ABS Setting'],
    'rear_wing':         ['Rear Wing Angle'],
    'front_wing':        ['Front Wing Angle'],
}


@dataclass
class StoMatch:
    path: str
    filename: str
    score: float
    session_type: str   # 'race' | 'qualify' | 'endurance' | 'unknown'
    is_wet: bool


def find_sto_files(setups_dir: str, car_name: str) -> List[StoMatch]:
    """
    Scan the iRacing setups folder recursively for all .sto files.
    Deduplicates by resolved real path.
    """
    matches: List[StoMatch] = []
    seen: set = set()

    for path in glob.glob(os.path.join(setups_dir, '**', '*.sto'), recursive=True):
        if not os.path.isfile(path):
            continue
        # Use realpath for robust deduplication across Windows path styles
        norm = os.path.normcase(os.path.realpath(path))
        if norm in seen:
            continue
        seen.add(norm)
        filename = os.path.basename(path)
        matches.append(StoMatch(
            path=path,
            filename=filename,
            score=0.0,
            session_type=_detect_session_type(filename),
            is_wet='wet' in filename.lower(),
        ))

    return matches


def score_sto_matches(
    matches: List[StoMatch],
    car_name: str,
    track_name: str = '',
    session_type: str = 'race',
    prefer_dry: bool = True,
) -> List[StoMatch]:
    """Score and sort StoMatch list best-first."""
    for m in matches:
        score = 0.0
        fn = m.filename.lower()

        # Session type
        if m.session_type == session_type:
            score += 10.0
        elif m.session_type == 'unknown':
            score += 2.0

        # Wet/dry
        if prefer_dry and not m.is_wet:
            score += 5.0
        elif not prefer_dry and m.is_wet:
            score += 5.0

        # Track name token overlap
        if track_name:
            score += _token_overlap(track_name, m.filename) * 3.0

        # Car name token overlap
        score += _token_overlap(car_name, m.filename) * 2.0

        # 'safe' setups are conservative — good base for modifications
        if 'safe' in fn:
            score += 3.0

        m.score = score

    sorted_matches = sorted(matches, key=lambda m: m.score, reverse=True)

    # Deduplicate by filename — keep the highest-scored copy of each setup name
    seen_names: set = set()
    deduped = []
    for m in sorted_matches:
        key = m.filename.lower()
        if key not in seen_names:
            seen_names.add(key)
            deduped.append(m)

    return deduped


def copy_base_setup(src_path: str, dest_dir: str, dest_name: str) -> str:
    """Copy a .sto file to dest_dir/dest_name. Returns the destination path."""
    os.makedirs(dest_dir, exist_ok=True)
    if not dest_name.endswith('.sto'):
        dest_name += '.sto'
    dest_path = os.path.join(dest_dir, dest_name)
    shutil.copy2(src_path, dest_path)
    return dest_path


def get_car_setups_dir(src_path: str, setups_dir: str) -> str:
    """
    Walk up from src_path until the parent equals setups_dir.
    Returns the car-level directory (one level below setups_dir).
    Falls back to the directory containing src_path.
    """
    path = os.path.normcase(os.path.abspath(src_path))
    setups_abs = os.path.normcase(os.path.abspath(setups_dir))

    # src_path is a file — start from its directory
    current = os.path.dirname(path)
    while True:
        parent = os.path.dirname(current)
        if parent == setups_abs:
            return current          # current is the car-level dir
        if parent == current:       # reached filesystem root
            break
        current = parent

    return os.path.dirname(src_path)  # fallback


def find_car_folder(setups_dir: str, car_name: str) -> str:
    """
    Find the best-matching car subfolder in setups_dir for the given car_name.

    iRacing folder names differ from IBT car names (e.g. IBT 'Fia F4 2022'
    maps to folder 'fiaf4_2022').  We tokenise both and pick the folder with
    the highest overlap score.  Falls back to setups_dir itself if no folders
    exist yet.
    """
    if not car_name:
        return setups_dir

    def _tokens(s: str) -> set:
        return set(re.findall(r'[a-z0-9]+', s.lower()))

    car_tokens = _tokens(car_name)

    best_dir = setups_dir
    best_score = -1

    try:
        entries = [
            e for e in os.scandir(setups_dir)
            if e.is_dir()
        ]
    except OSError:
        return setups_dir

    for entry in entries:
        folder_tokens = _tokens(entry.name)
        overlap = len(car_tokens & folder_tokens)
        # Bonus: if any car token is a substring of the folder name or vice versa
        bonus = sum(
            1 for t in car_tokens
            if t in entry.name.lower() and len(t) >= 3
        )
        score = overlap + bonus * 0.5
        if score > best_score:
            best_score = score
            best_dir = entry.path

    return best_dir


def build_checklist(changes: List[dict], setup=None,
                    impact_predictions: Dict = None) -> List[ChecklistItem]:
    """
    Convert optimizer change dicts to human-readable ChecklistItems.
    If setup (ParsedSetup) is provided, populates current_value and
    recommended_value for each item using the IBT-extracted setup data.
    If impact_predictions is provided (dict of param -> ImpactPrediction),
    uses the detailed explanation as the hint instead of the static display hint.
    """
    impact_predictions = impact_predictions or {}
    items = []
    for ch in changes:
        param = ch.get('parameter', '')
        delta = ch.get('delta', 0.0)
        if param not in PARAM_DISPLAY or delta == 0:
            continue
        label, unit, static_hint = PARAM_DISPLAY[param]
        # Use dynamic explanation from impact prediction if available
        pred = impact_predictions.get(param)
        hint = pred.explanation if pred is not None else static_hint
        direction = 'increase' if delta > 0 else 'decrease'
        amount = abs(delta)
        unit_word = unit + ('s' if amount != 1 and unit in ('click', 'level') else '')
        sign = '+' if delta > 0 else ''
        display = f"{sign}{delta:g} {unit_word}"

        affects = PARAM_TO_SETUP_KEYS.get(param, [])
        current_value = ''
        recommended_value = ''

        if setup is not None and affects:
            # Find first key that exists in the setup flat dict
            for key in affects:
                if key in setup.flat:
                    current_value = setup.flat[key]
                    break
            # Apply delta to extract numeric part
            num, suffix = _extract_numeric(current_value)
            if num is not None:
                rec_num = num + delta
                recommended_value = (f"{rec_num:g} {suffix}".strip()
                                     if suffix else f"{rec_num:g}")

        items.append(ChecklistItem(
            parameter=param,
            label=label,
            delta=delta,
            unit=unit,
            hint=hint,
            direction=direction,
            display=display,
            current_value=current_value,
            recommended_value=recommended_value,
            affects_keys=affects,
        ))
    return items


def _extract_numeric(value_str: str) -> Tuple[Optional[float], str]:
    """Extract numeric value and unit suffix from strings like '1', '0.75 mm', '51.2%', '4 (ABS)'."""
    if not value_str:
        return None, ''
    m = re.match(r'^([+-]?\d+\.?\d*)\s*(.*)', str(value_str).strip())
    if m:
        try:
            return float(m.group(1)), m.group(2).strip()
        except ValueError:
            pass
    return None, value_str


# ── Internal helpers ──────────────────────────────────────────────────────────

def _slugify(s: str) -> str:
    return re.sub(r'[^a-z0-9]', '', s.lower())


def _detect_session_type(filename: str) -> str:
    fn = filename.lower()
    # endurance before race so '_e_' doesn't accidentally match race patterns
    if re.search(r'[_\-\.]e[_\-\.]|safeend|endur|_endo', fn):
        return 'endurance'
    if re.search(r'[_\-\.]q[_\-\.]|safeq|safe_q|_qual', fn):
        return 'qualify'
    if re.search(r'[_\-\.]r[_\-\.]|safer|safe_r|_race', fn):
        return 'race'
    return 'unknown'


def _token_overlap(a: str, b: str) -> int:
    """Count significant tokens (len >= 3) from a that appear anywhere in b."""
    a_tokens = {t.lower() for t in re.split(r'[\W_]+', a) if len(t) >= 3}
    b_lower = b.lower()
    return sum(1 for t in a_tokens if t in b_lower)
