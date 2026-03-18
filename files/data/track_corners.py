"""
Track Corner Maps & Sector Split Points
=======================================
Named corner definitions and real sector boundaries for all supported iRacing tracks.

Corner format:
    Each entry is a dict with:
        "name"       : Human-readable corner name (e.g., "Eau Rouge / Raidillon")
        "start_pct"  : LapDistPct where the braking zone begins (0.0–1.0)
        "apex_pct"   : LapDistPct of the geometric apex (approximate)
        "end_pct"    : LapDistPct where the driver is back on full throttle
        "type"       : "hairpin" | "chicane" | "medium" | "fast" | "complex"
        "priority"   : int 1–3 (1 = highest lap-time importance)

Sector format:
    List of 1–3 floats in (0.0, 1.0) representing split points.
    Two values → three sectors (e.g., [0.33, 0.67]).
    Matches iRacing's in-game sector display wherever possible.

All LapDistPct values are calibrated to the iRacing track layouts.
Values are approximate (±1–2% accuracy) because iRacing does not expose
true sector split points through the IBT telemetry API.
"""

from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Data types (kept simple — no dataclasses so this file stays data-only)
# ---------------------------------------------------------------------------

CornerEntry = Dict   # {"name", "start_pct", "apex_pct", "end_pct", "type", "priority"}
TrackMap = Dict      # {"corners": List[CornerEntry], "sectors": List[float]}


# ---------------------------------------------------------------------------
# Track database
# Keys must fuzzy-match the names used in track_templates.py
# ---------------------------------------------------------------------------

TRACK_MAPS: Dict[str, TrackMap] = {

    # ── Spa-Francorchamps ────────────────────────────────────────────────
    "Spa-Francorchamps": {
        "sectors": [0.29, 0.60],   # S1: La Source→Eau Rouge exit  S2: Kemmel→Pouhon  S3: Bus Stop→finish
        "corners": [
            {"name": "La Source",              "start_pct": 0.02,  "apex_pct": 0.04,  "end_pct": 0.06,  "type": "hairpin",  "priority": 2},
            {"name": "Eau Rouge / Raidillon",  "start_pct": 0.08,  "apex_pct": 0.12,  "end_pct": 0.16,  "type": "fast",     "priority": 1},
            {"name": "Raidillon Exit",         "start_pct": 0.16,  "apex_pct": 0.19,  "end_pct": 0.22,  "type": "fast",     "priority": 2},
            {"name": "Les Combes T1",          "start_pct": 0.29,  "apex_pct": 0.31,  "end_pct": 0.33,  "type": "medium",   "priority": 2},
            {"name": "Les Combes T2",          "start_pct": 0.33,  "apex_pct": 0.35,  "end_pct": 0.37,  "type": "medium",   "priority": 2},
            {"name": "Malmedy",                "start_pct": 0.41,  "apex_pct": 0.43,  "end_pct": 0.45,  "type": "medium",   "priority": 3},
            {"name": "Rivage Hairpin",         "start_pct": 0.48,  "apex_pct": 0.50,  "end_pct": 0.52,  "type": "hairpin",  "priority": 2},
            {"name": "Pouhon",                 "start_pct": 0.58,  "apex_pct": 0.61,  "end_pct": 0.65,  "type": "fast",     "priority": 1},
            {"name": "Fagnes Chicane",         "start_pct": 0.71,  "apex_pct": 0.73,  "end_pct": 0.75,  "type": "chicane",  "priority": 3},
            {"name": "Stavelot",               "start_pct": 0.79,  "apex_pct": 0.81,  "end_pct": 0.83,  "type": "medium",   "priority": 2},
            {"name": "Bus Stop Chicane T1",    "start_pct": 0.90,  "apex_pct": 0.92,  "end_pct": 0.94,  "type": "chicane",  "priority": 1},
            {"name": "Bus Stop Chicane T2",    "start_pct": 0.94,  "apex_pct": 0.95,  "end_pct": 0.97,  "type": "chicane",  "priority": 1},
        ],
    },

    # ── Sebring ──────────────────────────────────────────────────────────
    "Sebring International Raceway": {
        "sectors": [0.30, 0.62],   # S1: start→T10  S2: T10→T15  S3: T15→finish
        "corners": [
            {"name": "Turn 1",        "start_pct": 0.02,  "apex_pct": 0.04,  "end_pct": 0.06,  "type": "medium",   "priority": 2},
            {"name": "Turn 3",        "start_pct": 0.08,  "apex_pct": 0.10,  "end_pct": 0.12,  "type": "medium",   "priority": 3},
            {"name": "Turn 5",        "start_pct": 0.14,  "apex_pct": 0.16,  "end_pct": 0.18,  "type": "medium",   "priority": 3},
            {"name": "Turn 7",        "start_pct": 0.21,  "apex_pct": 0.23,  "end_pct": 0.25,  "type": "hairpin",  "priority": 2},
            {"name": "Turn 10",       "start_pct": 0.30,  "apex_pct": 0.32,  "end_pct": 0.35,  "type": "medium",   "priority": 2},
            {"name": "Turn 13",       "start_pct": 0.45,  "apex_pct": 0.47,  "end_pct": 0.49,  "type": "hairpin",  "priority": 2},
            {"name": "Turn 15",       "start_pct": 0.60,  "apex_pct": 0.62,  "end_pct": 0.64,  "type": "medium",   "priority": 3},
            {"name": "Turn 17",       "start_pct": 0.72,  "apex_pct": 0.75,  "end_pct": 0.80,  "type": "fast",     "priority": 1},
        ],
    },

    # ── Road America ─────────────────────────────────────────────────────
    "Road America": {
        "sectors": [0.27, 0.60],   # S1: start→Canada Corner  S2: Carousel area  S3: Kink→finish
        "corners": [
            {"name": "Turn 1",                "start_pct": 0.03,  "apex_pct": 0.05,  "end_pct": 0.08,  "type": "hairpin",  "priority": 1},
            {"name": "Turn 3 (Kettle Bottom)","start_pct": 0.13,  "apex_pct": 0.15,  "end_pct": 0.18,  "type": "fast",     "priority": 1},
            {"name": "Turn 5",                "start_pct": 0.21,  "apex_pct": 0.23,  "end_pct": 0.25,  "type": "medium",   "priority": 2},
            {"name": "Turn 6 (Carousel)",     "start_pct": 0.28,  "apex_pct": 0.32,  "end_pct": 0.36,  "type": "complex",  "priority": 2},
            {"name": "Canada Corner (T12)",   "start_pct": 0.50,  "apex_pct": 0.53,  "end_pct": 0.56,  "type": "fast",     "priority": 1},
            {"name": "Turn 13 (Hairpin)",     "start_pct": 0.63,  "apex_pct": 0.65,  "end_pct": 0.67,  "type": "hairpin",  "priority": 2},
            {"name": "The Kink",              "start_pct": 0.77,  "apex_pct": 0.79,  "end_pct": 0.82,  "type": "fast",     "priority": 1},
            {"name": "Turn 14 Chicane",       "start_pct": 0.89,  "apex_pct": 0.91,  "end_pct": 0.94,  "type": "chicane",  "priority": 2},
        ],
    },

    # ── Road Atlanta ─────────────────────────────────────────────────────
    "Road Atlanta": {
        "sectors": [0.35, 0.70],
        "corners": [
            {"name": "Turn 1",          "start_pct": 0.02,  "apex_pct": 0.04,  "end_pct": 0.06,  "type": "medium",   "priority": 2},
            {"name": "Turn 2 (Esses)",  "start_pct": 0.09,  "apex_pct": 0.12,  "end_pct": 0.17,  "type": "complex",  "priority": 1},
            {"name": "Turn 4",          "start_pct": 0.20,  "apex_pct": 0.22,  "end_pct": 0.24,  "type": "fast",     "priority": 1},
            {"name": "Turn 5 (Flat)",   "start_pct": 0.26,  "apex_pct": 0.28,  "end_pct": 0.31,  "type": "fast",     "priority": 1},
            {"name": "Turn 10a",        "start_pct": 0.55,  "apex_pct": 0.58,  "end_pct": 0.61,  "type": "hairpin",  "priority": 1},
            {"name": "Turn 10b",        "start_pct": 0.62,  "apex_pct": 0.64,  "end_pct": 0.66,  "type": "medium",   "priority": 2},
            {"name": "Turn 12",         "start_pct": 0.80,  "apex_pct": 0.82,  "end_pct": 0.84,  "type": "medium",   "priority": 2},
        ],
    },

    # ── Laguna Seca ──────────────────────────────────────────────────────
    "Laguna Seca": {
        "sectors": [0.33, 0.66],
        "corners": [
            {"name": "Turn 1",                 "start_pct": 0.02,  "apex_pct": 0.04,  "end_pct": 0.07,  "type": "medium",   "priority": 2},
            {"name": "T2 Andretti Hairpin",    "start_pct": 0.12,  "apex_pct": 0.15,  "end_pct": 0.18,  "type": "hairpin",  "priority": 1},
            {"name": "Turn 3",                 "start_pct": 0.22,  "apex_pct": 0.24,  "end_pct": 0.26,  "type": "medium",   "priority": 3},
            {"name": "Turn 4",                 "start_pct": 0.31,  "apex_pct": 0.33,  "end_pct": 0.36,  "type": "medium",   "priority": 3},
            {"name": "Turn 5",                 "start_pct": 0.40,  "apex_pct": 0.42,  "end_pct": 0.44,  "type": "medium",   "priority": 3},
            {"name": "Turn 6",                 "start_pct": 0.48,  "apex_pct": 0.50,  "end_pct": 0.52,  "type": "medium",   "priority": 3},
            {"name": "The Corkscrew (T8a–8b)", "start_pct": 0.60,  "apex_pct": 0.64,  "end_pct": 0.68,  "type": "complex",  "priority": 1},
            {"name": "Turn 9",                 "start_pct": 0.72,  "apex_pct": 0.74,  "end_pct": 0.76,  "type": "medium",   "priority": 2},
            {"name": "Turn 11 (Rainey Curve)", "start_pct": 0.84,  "apex_pct": 0.87,  "end_pct": 0.91,  "type": "fast",     "priority": 1},
        ],
    },

    # ── Watkins Glen ─────────────────────────────────────────────────────
    "Watkins Glen International": {
        "sectors": [0.38, 0.68],   # S1: start→esses  S2: boot section  S3: toe→finish
        "corners": [
            {"name": "Turn 1",            "start_pct": 0.02,  "apex_pct": 0.04,  "end_pct": 0.07,  "type": "medium",   "priority": 1},
            {"name": "T2–T4 Esses",       "start_pct": 0.10,  "apex_pct": 0.18,  "end_pct": 0.24,  "type": "complex",  "priority": 1},
            {"name": "Turn 5 (The Toe)",  "start_pct": 0.36,  "apex_pct": 0.38,  "end_pct": 0.41,  "type": "medium",   "priority": 2},
            {"name": "Turn 6",            "start_pct": 0.44,  "apex_pct": 0.46,  "end_pct": 0.48,  "type": "medium",   "priority": 2},
            {"name": "Turn 7",            "start_pct": 0.52,  "apex_pct": 0.54,  "end_pct": 0.56,  "type": "medium",   "priority": 3},
            {"name": "Turn 9",            "start_pct": 0.60,  "apex_pct": 0.62,  "end_pct": 0.65,  "type": "medium",   "priority": 3},
            {"name": "Turn 10",           "start_pct": 0.68,  "apex_pct": 0.70,  "end_pct": 0.73,  "type": "hairpin",  "priority": 2},
            {"name": "The Boot T11",      "start_pct": 0.79,  "apex_pct": 0.82,  "end_pct": 0.86,  "type": "fast",     "priority": 2},
        ],
    },

    # ── Virginia International Raceway ───────────────────────────────────
    "Virginia International Raceway": {
        "sectors": [0.32, 0.65],
        "corners": [
            {"name": "Turn 1 Hairpin",        "start_pct": 0.02,  "apex_pct": 0.04,  "end_pct": 0.07,  "type": "hairpin",  "priority": 1},
            {"name": "Turn 2",                "start_pct": 0.10,  "apex_pct": 0.12,  "end_pct": 0.14,  "type": "medium",   "priority": 3},
            {"name": "Roller Coaster T4–T6",  "start_pct": 0.20,  "apex_pct": 0.27,  "end_pct": 0.33,  "type": "complex",  "priority": 2},
            {"name": "Turn 8 Hairpin",        "start_pct": 0.44,  "apex_pct": 0.46,  "end_pct": 0.49,  "type": "hairpin",  "priority": 2},
            {"name": "Oak Tree Turn (T13)",   "start_pct": 0.76,  "apex_pct": 0.79,  "end_pct": 0.83,  "type": "fast",     "priority": 1},
            {"name": "Turn 14",               "start_pct": 0.88,  "apex_pct": 0.90,  "end_pct": 0.92,  "type": "medium",   "priority": 2},
        ],
    },

    # ── Circuit of the Americas ──────────────────────────────────────────
    "Circuit of the Americas": {
        "sectors": [0.30, 0.62],
        "corners": [
            {"name": "Turn 1",              "start_pct": 0.02,  "apex_pct": 0.04,  "end_pct": 0.07,  "type": "hairpin",  "priority": 1},
            {"name": "S1 Complex T3–T9",    "start_pct": 0.08,  "apex_pct": 0.16,  "end_pct": 0.24,  "type": "complex",  "priority": 1},
            {"name": "Turn 10",             "start_pct": 0.27,  "apex_pct": 0.29,  "end_pct": 0.31,  "type": "hairpin",  "priority": 2},
            {"name": "Turn 11",             "start_pct": 0.34,  "apex_pct": 0.36,  "end_pct": 0.38,  "type": "medium",   "priority": 2},
            {"name": "Turn 12 (fast left)", "start_pct": 0.49,  "apex_pct": 0.52,  "end_pct": 0.56,  "type": "fast",     "priority": 1},
            {"name": "Turn 13",             "start_pct": 0.58,  "apex_pct": 0.60,  "end_pct": 0.62,  "type": "medium",   "priority": 2},
            {"name": "T14–T15 (Stadium)",   "start_pct": 0.63,  "apex_pct": 0.67,  "end_pct": 0.71,  "type": "complex",  "priority": 2},
            {"name": "Turn 16",             "start_pct": 0.74,  "apex_pct": 0.76,  "end_pct": 0.78,  "type": "medium",   "priority": 3},
            {"name": "T18–T19–T20",         "start_pct": 0.85,  "apex_pct": 0.90,  "end_pct": 0.96,  "type": "complex",  "priority": 2},
        ],
    },

    # ── Sonoma Raceway ───────────────────────────────────────────────────
    "Sonoma Raceway": {
        "sectors": [0.35, 0.68],
        "corners": [
            {"name": "Turn 1",              "start_pct": 0.02,  "apex_pct": 0.04,  "end_pct": 0.07,  "type": "medium",   "priority": 2},
            {"name": "T2–T3 Esses",         "start_pct": 0.10,  "apex_pct": 0.14,  "end_pct": 0.18,  "type": "complex",  "priority": 2},
            {"name": "Turn 4 Hairpin",      "start_pct": 0.26,  "apex_pct": 0.28,  "end_pct": 0.31,  "type": "hairpin",  "priority": 1},
            {"name": "Turn 6",              "start_pct": 0.42,  "apex_pct": 0.44,  "end_pct": 0.46,  "type": "medium",   "priority": 3},
            {"name": "Carousel (T7)",       "start_pct": 0.52,  "apex_pct": 0.58,  "end_pct": 0.64,  "type": "complex",  "priority": 1},
            {"name": "Turn 9",              "start_pct": 0.70,  "apex_pct": 0.72,  "end_pct": 0.74,  "type": "medium",   "priority": 3},
            {"name": "T10–T11 (final)",     "start_pct": 0.83,  "apex_pct": 0.87,  "end_pct": 0.92,  "type": "complex",  "priority": 2},
        ],
    },

    # ── Portland International Raceway ───────────────────────────────────
    "Portland International Raceway": {
        "sectors": [0.32, 0.65],
        "corners": [
            {"name": "T1–T2 Chicane",    "start_pct": 0.02,  "apex_pct": 0.05,  "end_pct": 0.09,  "type": "chicane",  "priority": 1},
            {"name": "Turn 3",           "start_pct": 0.14,  "apex_pct": 0.16,  "end_pct": 0.18,  "type": "medium",   "priority": 3},
            {"name": "Turn 7 Hairpin",   "start_pct": 0.32,  "apex_pct": 0.34,  "end_pct": 0.37,  "type": "hairpin",  "priority": 1},
            {"name": "Turn 8",           "start_pct": 0.40,  "apex_pct": 0.42,  "end_pct": 0.44,  "type": "medium",   "priority": 3},
            {"name": "Turn 10",          "start_pct": 0.52,  "apex_pct": 0.54,  "end_pct": 0.56,  "type": "medium",   "priority": 2},
            {"name": "Turn 11",          "start_pct": 0.62,  "apex_pct": 0.64,  "end_pct": 0.66,  "type": "hairpin",  "priority": 2},
            {"name": "T12 (final)",      "start_pct": 0.88,  "apex_pct": 0.91,  "end_pct": 0.94,  "type": "medium",   "priority": 2},
        ],
    },

    # ── Lime Rock Park ───────────────────────────────────────────────────
    "Lime Rock Park": {
        "sectors": [0.35, 0.70],
        "corners": [
            {"name": "Big Bend (T1)",      "start_pct": 0.04,  "apex_pct": 0.07,  "end_pct": 0.12,  "type": "medium",   "priority": 1},
            {"name": "Turn 2 (Downhill)",  "start_pct": 0.22,  "apex_pct": 0.25,  "end_pct": 0.28,  "type": "medium",   "priority": 2},
            {"name": "Bottom Sweeper T3",  "start_pct": 0.35,  "apex_pct": 0.40,  "end_pct": 0.46,  "type": "fast",     "priority": 2},
            {"name": "Uphill Hairpin T5",  "start_pct": 0.62,  "apex_pct": 0.65,  "end_pct": 0.68,  "type": "hairpin",  "priority": 1},
            {"name": "Turn 6 (final)",     "start_pct": 0.82,  "apex_pct": 0.85,  "end_pct": 0.89,  "type": "medium",   "priority": 2},
        ],
    },

    # ── Long Beach ───────────────────────────────────────────────────────
    "Long Beach Street Circuit": {
        "sectors": [0.30, 0.65],
        "corners": [
            {"name": "T1 Shoreline Drive", "start_pct": 0.02,  "apex_pct": 0.05,  "end_pct": 0.08,  "type": "hairpin",  "priority": 1},
            {"name": "Turn 2",             "start_pct": 0.12,  "apex_pct": 0.14,  "end_pct": 0.16,  "type": "medium",   "priority": 3},
            {"name": "Turn 4",             "start_pct": 0.28,  "apex_pct": 0.30,  "end_pct": 0.33,  "type": "medium",   "priority": 2},
            {"name": "T5–T6 (hairpin)",    "start_pct": 0.36,  "apex_pct": 0.40,  "end_pct": 0.44,  "type": "hairpin",  "priority": 2},
            {"name": "Turn 8",             "start_pct": 0.55,  "apex_pct": 0.57,  "end_pct": 0.59,  "type": "medium",   "priority": 3},
            {"name": "T9 (Queen's Hpin)",  "start_pct": 0.65,  "apex_pct": 0.68,  "end_pct": 0.71,  "type": "hairpin",  "priority": 1},
            {"name": "Turn 11",            "start_pct": 0.78,  "apex_pct": 0.80,  "end_pct": 0.82,  "type": "medium",   "priority": 2},
        ],
    },

    # ── Willow Springs ───────────────────────────────────────────────────
    "Willow Springs": {
        "sectors": [0.40, 0.72],
        "corners": [
            {"name": "Turn 1",         "start_pct": 0.03,  "apex_pct": 0.06,  "end_pct": 0.09,  "type": "medium",   "priority": 2},
            {"name": "Turn 2",         "start_pct": 0.14,  "apex_pct": 0.16,  "end_pct": 0.19,  "type": "medium",   "priority": 2},
            {"name": "Turn 3",         "start_pct": 0.24,  "apex_pct": 0.26,  "end_pct": 0.28,  "type": "fast",     "priority": 2},
            {"name": "Turn 5",         "start_pct": 0.42,  "apex_pct": 0.44,  "end_pct": 0.47,  "type": "medium",   "priority": 2},
            {"name": "Turn 8",         "start_pct": 0.60,  "apex_pct": 0.63,  "end_pct": 0.66,  "type": "medium",   "priority": 2},
            {"name": "Turn 9 (fast R)","start_pct": 0.70,  "apex_pct": 0.77,  "end_pct": 0.84,  "type": "fast",     "priority": 1},
        ],
    },

    # ── Mexico City ──────────────────────────────────────────────────────
    "Mexico City": {
        "sectors": [0.28, 0.58],
        "corners": [
            {"name": "Peralta T1",       "start_pct": 0.02,  "apex_pct": 0.04,  "end_pct": 0.07,  "type": "medium",   "priority": 2},
            {"name": "Turn 3",           "start_pct": 0.12,  "apex_pct": 0.14,  "end_pct": 0.16,  "type": "medium",   "priority": 3},
            {"name": "Horquilla (T4)",   "start_pct": 0.20,  "apex_pct": 0.22,  "end_pct": 0.25,  "type": "hairpin",  "priority": 2},
            {"name": "Eses T6–T9",       "start_pct": 0.32,  "apex_pct": 0.38,  "end_pct": 0.44,  "type": "complex",  "priority": 2},
            {"name": "Turn 11",          "start_pct": 0.48,  "apex_pct": 0.50,  "end_pct": 0.52,  "type": "medium",   "priority": 3},
            {"name": "Peralada (T17)",   "start_pct": 0.76,  "apex_pct": 0.82,  "end_pct": 0.90,  "type": "fast",     "priority": 1},
        ],
    },

    # ── Spa-Francorchamps already done above ─────────────────────────────

    # ── Monza ────────────────────────────────────────────────────────────
    "Monza": {
        "sectors": [0.28, 0.60],   # S1: start→Curva Grande  S2: Lesmo/Ascari  S3: Parabolica→finish
        "corners": [
            {"name": "T1 Chicane (Prima)",    "start_pct": 0.04,  "apex_pct": 0.06,  "end_pct": 0.09,  "type": "chicane",  "priority": 1},
            {"name": "T2 Chicane (Seconda)",  "start_pct": 0.09,  "apex_pct": 0.11,  "end_pct": 0.14,  "type": "chicane",  "priority": 1},
            {"name": "Curva Grande",          "start_pct": 0.18,  "apex_pct": 0.20,  "end_pct": 0.23,  "type": "fast",     "priority": 2},
            {"name": "T4 Chicane (Variante)", "start_pct": 0.30,  "apex_pct": 0.32,  "end_pct": 0.36,  "type": "chicane",  "priority": 1},
            {"name": "Lesmo 1",               "start_pct": 0.44,  "apex_pct": 0.46,  "end_pct": 0.48,  "type": "medium",   "priority": 2},
            {"name": "Lesmo 2",               "start_pct": 0.50,  "apex_pct": 0.52,  "end_pct": 0.54,  "type": "medium",   "priority": 2},
            {"name": "Ascari Chicane",        "start_pct": 0.62,  "apex_pct": 0.66,  "end_pct": 0.70,  "type": "chicane",  "priority": 2},
            {"name": "Parabolica",            "start_pct": 0.82,  "apex_pct": 0.87,  "end_pct": 0.94,  "type": "medium",   "priority": 1},
        ],
    },

    # ── Nürburgring GP ───────────────────────────────────────────────────
    "Nürburgring GP": {
        "sectors": [0.30, 0.65],
        "corners": [
            {"name": "T1 (Mercedes Arena)",  "start_pct": 0.03,  "apex_pct": 0.05,  "end_pct": 0.08,  "type": "medium",   "priority": 1},
            {"name": "T2–T6 (Arena complex)","start_pct": 0.10,  "apex_pct": 0.18,  "end_pct": 0.26,  "type": "complex",  "priority": 1},
            {"name": "T7 (Einfahrt)",        "start_pct": 0.32,  "apex_pct": 0.34,  "end_pct": 0.36,  "type": "medium",   "priority": 2},
            {"name": "T8 (Ford Kurve)",      "start_pct": 0.50,  "apex_pct": 0.52,  "end_pct": 0.55,  "type": "medium",   "priority": 2},
            {"name": "T11 (Veedol)",         "start_pct": 0.72,  "apex_pct": 0.74,  "end_pct": 0.76,  "type": "medium",   "priority": 3},
            {"name": "T13 (Dunlop Hpin)",    "start_pct": 0.84,  "apex_pct": 0.86,  "end_pct": 0.88,  "type": "hairpin",  "priority": 2},
        ],
    },

    # ── Silverstone ──────────────────────────────────────────────────────
    "Silverstone Circuit": {
        "sectors": [0.32, 0.68],
        "corners": [
            {"name": "Copse (T1)",              "start_pct": 0.02,  "apex_pct": 0.04,  "end_pct": 0.07,  "type": "fast",     "priority": 1},
            {"name": "Maggots–Becketts–Chapel", "start_pct": 0.12,  "apex_pct": 0.20,  "end_pct": 0.28,  "type": "complex",  "priority": 1},
            {"name": "Stowe (T14)",             "start_pct": 0.47,  "apex_pct": 0.49,  "end_pct": 0.52,  "type": "medium",   "priority": 2},
            {"name": "Vale (T15)",              "start_pct": 0.54,  "apex_pct": 0.57,  "end_pct": 0.60,  "type": "medium",   "priority": 2},
            {"name": "Club Corner (T16)",       "start_pct": 0.63,  "apex_pct": 0.66,  "end_pct": 0.70,  "type": "medium",   "priority": 2},
            {"name": "Abbey (T1–new)",          "start_pct": 0.74,  "apex_pct": 0.76,  "end_pct": 0.78,  "type": "fast",     "priority": 2},
            {"name": "Brooklands",              "start_pct": 0.80,  "apex_pct": 0.82,  "end_pct": 0.84,  "type": "medium",   "priority": 3},
            {"name": "Luffield",                "start_pct": 0.88,  "apex_pct": 0.91,  "end_pct": 0.94,  "type": "medium",   "priority": 2},
        ],
    },

    # ── Barcelona ────────────────────────────────────────────────────────
    "Circuit de Barcelona-Catalunya": {
        "sectors": [0.28, 0.60],
        "corners": [
            {"name": "Turn 1",           "start_pct": 0.02,  "apex_pct": 0.04,  "end_pct": 0.07,  "type": "medium",   "priority": 1},
            {"name": "Turn 2",           "start_pct": 0.09,  "apex_pct": 0.11,  "end_pct": 0.13,  "type": "fast",     "priority": 2},
            {"name": "Turn 3 (long R)",  "start_pct": 0.15,  "apex_pct": 0.19,  "end_pct": 0.24,  "type": "fast",     "priority": 1},
            {"name": "Turn 4",           "start_pct": 0.27,  "apex_pct": 0.29,  "end_pct": 0.31,  "type": "medium",   "priority": 2},
            {"name": "Turn 5 (right)",   "start_pct": 0.35,  "apex_pct": 0.38,  "end_pct": 0.41,  "type": "fast",     "priority": 2},
            {"name": "Turn 9 (hairpin)", "start_pct": 0.54,  "apex_pct": 0.58,  "end_pct": 0.64,  "type": "hairpin",  "priority": 1},
            {"name": "T10 Braking",      "start_pct": 0.69,  "apex_pct": 0.71,  "end_pct": 0.73,  "type": "medium",   "priority": 2},
            {"name": "T11–T14",          "start_pct": 0.76,  "apex_pct": 0.82,  "end_pct": 0.88,  "type": "complex",  "priority": 2},
            {"name": "T15–T16 Chicane",  "start_pct": 0.90,  "apex_pct": 0.93,  "end_pct": 0.96,  "type": "chicane",  "priority": 2},
        ],
    },

    # ── Imola ────────────────────────────────────────────────────────────
    "Imola": {
        "sectors": [0.32, 0.62],
        "corners": [
            {"name": "Tamburello Chicane",  "start_pct": 0.02,  "apex_pct": 0.05,  "end_pct": 0.09,  "type": "chicane",  "priority": 1},
            {"name": "Villeneuve",          "start_pct": 0.13,  "apex_pct": 0.15,  "end_pct": 0.17,  "type": "medium",   "priority": 2},
            {"name": "Tosa Hairpin",        "start_pct": 0.22,  "apex_pct": 0.24,  "end_pct": 0.27,  "type": "hairpin",  "priority": 2},
            {"name": "Acque Minerali",      "start_pct": 0.35,  "apex_pct": 0.39,  "end_pct": 0.44,  "type": "complex",  "priority": 2},
            {"name": "Piratella",           "start_pct": 0.52,  "apex_pct": 0.55,  "end_pct": 0.59,  "type": "fast",     "priority": 1},
            {"name": "Variante Alta",       "start_pct": 0.64,  "apex_pct": 0.68,  "end_pct": 0.72,  "type": "chicane",  "priority": 2},
            {"name": "Rivazza 1",           "start_pct": 0.80,  "apex_pct": 0.82,  "end_pct": 0.85,  "type": "hairpin",  "priority": 1},
            {"name": "Rivazza 2",           "start_pct": 0.86,  "apex_pct": 0.88,  "end_pct": 0.90,  "type": "medium",   "priority": 2},
        ],
    },

    # ── Le Mans ──────────────────────────────────────────────────────────
    "Le Mans 24h Circuit": {
        "sectors": [0.30, 0.62],   # S1: start→Ford Chicanes  S2: Mulsanne→Porsche  S3: Porsche→finish
        "corners": [
            {"name": "Dunlop Chicane",     "start_pct": 0.02,  "apex_pct": 0.04,  "end_pct": 0.07,  "type": "chicane",  "priority": 2},
            {"name": "Dunlop Curve",       "start_pct": 0.09,  "apex_pct": 0.11,  "end_pct": 0.13,  "type": "medium",   "priority": 2},
            {"name": "Ford Chicane T9",    "start_pct": 0.28,  "apex_pct": 0.30,  "end_pct": 0.33,  "type": "chicane",  "priority": 1},
            {"name": "Ford Chicane T11",   "start_pct": 0.34,  "apex_pct": 0.36,  "end_pct": 0.39,  "type": "chicane",  "priority": 1},
            {"name": "Mulsanne Corner",    "start_pct": 0.49,  "apex_pct": 0.52,  "end_pct": 0.55,  "type": "hairpin",  "priority": 1},
            {"name": "Indianapolis",       "start_pct": 0.63,  "apex_pct": 0.65,  "end_pct": 0.68,  "type": "medium",   "priority": 2},
            {"name": "Arnage Hairpin",     "start_pct": 0.72,  "apex_pct": 0.74,  "end_pct": 0.77,  "type": "hairpin",  "priority": 2},
            {"name": "Porsche Curves",     "start_pct": 0.82,  "apex_pct": 0.88,  "end_pct": 0.94,  "type": "complex",  "priority": 1},
        ],
    },

    # ── Zandvoort ────────────────────────────────────────────────────────
    "Zandvoort": {
        "sectors": [0.30, 0.65],
        "corners": [
            {"name": "Tarzan (T1)",             "start_pct": 0.02,  "apex_pct": 0.05,  "end_pct": 0.08,  "type": "hairpin",  "priority": 1},
            {"name": "Gerlachbocht (T2)",        "start_pct": 0.12,  "apex_pct": 0.14,  "end_pct": 0.16,  "type": "medium",   "priority": 2},
            {"name": "Hugenholtz banked (T3)",   "start_pct": 0.22,  "apex_pct": 0.26,  "end_pct": 0.30,  "type": "fast",     "priority": 1},
            {"name": "Scheivlak (T7)",           "start_pct": 0.44,  "apex_pct": 0.46,  "end_pct": 0.48,  "type": "medium",   "priority": 2},
            {"name": "Hugenholtzbocht (T8)",     "start_pct": 0.54,  "apex_pct": 0.56,  "end_pct": 0.59,  "type": "medium",   "priority": 2},
            {"name": "Arie Luyendijk banked",    "start_pct": 0.74,  "apex_pct": 0.80,  "end_pct": 0.86,  "type": "fast",     "priority": 1},
            {"name": "Hans Ernst (T14)",         "start_pct": 0.88,  "apex_pct": 0.90,  "end_pct": 0.93,  "type": "medium",   "priority": 2},
        ],
    },

    # ── Daytona Road Course ───────────────────────────────────────────────
    "Daytona International Speedway": {
        "sectors": [0.33, 0.66],
        "corners": [
            {"name": "T1 (Bus Stop)",   "start_pct": 0.04,  "apex_pct": 0.07,  "end_pct": 0.12,  "type": "chicane",  "priority": 1},
            {"name": "T3 Infield",      "start_pct": 0.22,  "apex_pct": 0.24,  "end_pct": 0.27,  "type": "medium",   "priority": 2},
            {"name": "T5–T6 Infield",   "start_pct": 0.34,  "apex_pct": 0.38,  "end_pct": 0.43,  "type": "complex",  "priority": 2},
            {"name": "Oval T1–T2",      "start_pct": 0.56,  "apex_pct": 0.62,  "end_pct": 0.68,  "type": "fast",     "priority": 2},
            {"name": "Oval T3–T4",      "start_pct": 0.76,  "apex_pct": 0.82,  "end_pct": 0.88,  "type": "fast",     "priority": 2},
        ],
    },

    # ── Indianapolis Road Course ──────────────────────────────────────────
    "Indianapolis Motor Speedway": {
        "sectors": [0.30, 0.62],
        "corners": [
            {"name": "T1 (Turn 1 Infield)",  "start_pct": 0.04,  "apex_pct": 0.06,  "end_pct": 0.09,  "type": "medium",   "priority": 2},
            {"name": "T2–T6 Infield",        "start_pct": 0.12,  "apex_pct": 0.20,  "end_pct": 0.28,  "type": "complex",  "priority": 1},
            {"name": "Pit Straight Kink",    "start_pct": 0.35,  "apex_pct": 0.37,  "end_pct": 0.39,  "type": "fast",     "priority": 3},
            {"name": "Oval T1 (banked)",     "start_pct": 0.50,  "apex_pct": 0.57,  "end_pct": 0.64,  "type": "fast",     "priority": 2},
            {"name": "Oval T3 (banked)",     "start_pct": 0.75,  "apex_pct": 0.82,  "end_pct": 0.89,  "type": "fast",     "priority": 2},
        ],
    },

    # ── Nürburgring Nordschleife ──────────────────────────────────────────
    "Nürburgring Nordschleife": {
        "sectors": [0.22, 0.58],   # S1: start→Schwedenkreuz  S2: Bergwerk→Pflanzgarten  S3: Schwalbenschwanz→finish
        "corners": [
            {"name": "Einfahrt Brücke",     "start_pct": 0.02,  "apex_pct": 0.04,  "end_pct": 0.06,  "type": "medium",   "priority": 2},
            {"name": "Hatzenbach",          "start_pct": 0.07,  "apex_pct": 0.10,  "end_pct": 0.14,  "type": "complex",  "priority": 2},
            {"name": "Hocheichen",          "start_pct": 0.17,  "apex_pct": 0.19,  "end_pct": 0.21,  "type": "medium",   "priority": 2},
            {"name": "Quiddelbacher Höhe",  "start_pct": 0.25,  "apex_pct": 0.27,  "end_pct": 0.29,  "type": "fast",     "priority": 2},
            {"name": "Flugplatz",           "start_pct": 0.34,  "apex_pct": 0.36,  "end_pct": 0.39,  "type": "fast",     "priority": 1},
            {"name": "Schwedenkreuz",       "start_pct": 0.43,  "apex_pct": 0.45,  "end_pct": 0.47,  "type": "fast",     "priority": 1},
            {"name": "Aremberg",            "start_pct": 0.50,  "apex_pct": 0.52,  "end_pct": 0.54,  "type": "medium",   "priority": 2},
            {"name": "Fuchsröhre",          "start_pct": 0.57,  "apex_pct": 0.60,  "end_pct": 0.64,  "type": "fast",     "priority": 1},
            {"name": "Adenauer Forst",      "start_pct": 0.67,  "apex_pct": 0.70,  "end_pct": 0.73,  "type": "complex",  "priority": 2},
            {"name": "Metzgesfeld",         "start_pct": 0.75,  "apex_pct": 0.77,  "end_pct": 0.79,  "type": "medium",   "priority": 3},
            {"name": "Bergwerk",            "start_pct": 0.80,  "apex_pct": 0.82,  "end_pct": 0.84,  "type": "medium",   "priority": 2},
            {"name": "Kesselchen",          "start_pct": 0.86,  "apex_pct": 0.88,  "end_pct": 0.91,  "type": "fast",     "priority": 1},
            {"name": "Karussell",           "start_pct": 0.92,  "apex_pct": 0.94,  "end_pct": 0.96,  "type": "complex",  "priority": 1},
        ],
    },

    # ── Miami International Autodrome ────────────────────────────────────
    "Miami International Autodrome": {
        "sectors": [0.30, 0.65],   # S1: start→stadium entry  S2: stadium complex  S3: return straight→finish
        "corners": [
            {"name": "Turn 1",              "start_pct": 0.02,  "apex_pct": 0.04,  "end_pct": 0.07,  "type": "hairpin",  "priority": 1},
            {"name": "Turn 2",              "start_pct": 0.10,  "apex_pct": 0.12,  "end_pct": 0.14,  "type": "medium",   "priority": 2},
            {"name": "Turn 3",              "start_pct": 0.17,  "apex_pct": 0.19,  "end_pct": 0.21,  "type": "medium",   "priority": 3},
            {"name": "Turn 4 (fast left)",  "start_pct": 0.24,  "apex_pct": 0.26,  "end_pct": 0.29,  "type": "fast",     "priority": 2},
            {"name": "T6–T7 Complex",       "start_pct": 0.34,  "apex_pct": 0.38,  "end_pct": 0.42,  "type": "complex",  "priority": 2},
            {"name": "Turn 11 (hairpin)",   "start_pct": 0.52,  "apex_pct": 0.55,  "end_pct": 0.58,  "type": "hairpin",  "priority": 1},
            {"name": "Turn 13",             "start_pct": 0.62,  "apex_pct": 0.64,  "end_pct": 0.66,  "type": "medium",   "priority": 2},
            {"name": "Turn 14 (hairpin)",   "start_pct": 0.69,  "apex_pct": 0.71,  "end_pct": 0.74,  "type": "hairpin",  "priority": 1},
            {"name": "T15–T16 chicane",     "start_pct": 0.78,  "apex_pct": 0.81,  "end_pct": 0.84,  "type": "chicane",  "priority": 2},
            {"name": "Turn 17 (final)",     "start_pct": 0.90,  "apex_pct": 0.93,  "end_pct": 0.96,  "type": "medium",   "priority": 2},
        ],
    },

    # ── Motorsport Arena Oschersleben ────────────────────────────────────
    "Motorsport Arena Oschersleben": {
        "sectors": [0.32, 0.66],
        "corners": [
            {"name": "Motodrom (T1)",       "start_pct": 0.02,  "apex_pct": 0.05,  "end_pct": 0.08,  "type": "hairpin",  "priority": 1},
            {"name": "Turn 2",              "start_pct": 0.12,  "apex_pct": 0.14,  "end_pct": 0.16,  "type": "medium",   "priority": 2},
            {"name": "T3–T4 Esses",         "start_pct": 0.20,  "apex_pct": 0.24,  "end_pct": 0.28,  "type": "complex",  "priority": 2},
            {"name": "Turn 6",              "start_pct": 0.35,  "apex_pct": 0.37,  "end_pct": 0.39,  "type": "medium",   "priority": 3},
            {"name": "Turn 8 hairpin",      "start_pct": 0.48,  "apex_pct": 0.50,  "end_pct": 0.53,  "type": "hairpin",  "priority": 2},
            {"name": "Turn 9",              "start_pct": 0.57,  "apex_pct": 0.59,  "end_pct": 0.61,  "type": "medium",   "priority": 2},
            {"name": "T10–T11 chicane",     "start_pct": 0.68,  "apex_pct": 0.72,  "end_pct": 0.76,  "type": "chicane",  "priority": 2},
            {"name": "Turn 12 (final)",     "start_pct": 0.88,  "apex_pct": 0.91,  "end_pct": 0.94,  "type": "medium",   "priority": 2},
        ],
    },

    # ── Summit Point Raceway ─────────────────────────────────────────────
    "Summit Point Raceway": {
        "sectors": [0.33, 0.66],
        "corners": [
            {"name": "Turn 1",              "start_pct": 0.02,  "apex_pct": 0.04,  "end_pct": 0.07,  "type": "medium",   "priority": 2},
            {"name": "Turn 2",              "start_pct": 0.11,  "apex_pct": 0.13,  "end_pct": 0.15,  "type": "medium",   "priority": 3},
            {"name": "Turn 3 hairpin",      "start_pct": 0.20,  "apex_pct": 0.22,  "end_pct": 0.25,  "type": "hairpin",  "priority": 1},
            {"name": "Back sweeper",        "start_pct": 0.35,  "apex_pct": 0.40,  "end_pct": 0.46,  "type": "fast",     "priority": 1},
            {"name": "Turn 7",              "start_pct": 0.55,  "apex_pct": 0.57,  "end_pct": 0.59,  "type": "medium",   "priority": 2},
            {"name": "Turn 8 hairpin",      "start_pct": 0.65,  "apex_pct": 0.67,  "end_pct": 0.70,  "type": "hairpin",  "priority": 2},
            {"name": "Turn 10 (final)",     "start_pct": 0.85,  "apex_pct": 0.88,  "end_pct": 0.92,  "type": "medium",   "priority": 2},
        ],
    },
}

# ---------------------------------------------------------------------------
# Lookup helpers
# ---------------------------------------------------------------------------

def _fuzzy_match(track_name: str) -> Optional[str]:
    """Return the closest TRACK_MAPS key for *track_name*, or None."""
    if track_name in TRACK_MAPS:
        return track_name
    lower = track_name.lower()
    for key in TRACK_MAPS:
        if key.lower() in lower or lower in key.lower():
            return key
    # Partial word match
    words = [w for w in lower.split() if len(w) > 3]
    for key in TRACK_MAPS:
        key_lower = key.lower()
        if any(w in key_lower for w in words):
            return key
    return None


def get_track_map(track_name: str) -> Optional[TrackMap]:
    """Return the TrackMap for *track_name*, or None if not found."""
    key = _fuzzy_match(track_name)
    return TRACK_MAPS.get(key) if key else None


def get_sectors(track_name: str) -> List[float]:
    """
    Return sector split points as LapDistPct fractions.
    Falls back to equal 3-sector split [0.333, 0.667] if track not found.
    """
    tm = get_track_map(track_name)
    if tm and tm.get("sectors"):
        return tm["sectors"]
    return [1 / 3, 2 / 3]


def get_named_corners(track_name: str) -> List[CornerEntry]:
    """
    Return the ordered list of named corner entries for *track_name*.
    Returns an empty list if the track is not in the database.
    """
    tm = get_track_map(track_name)
    if tm:
        return tm.get("corners", [])
    return []


def resolve_corner_name(track_name: str, apex_pct: float, tolerance: float = 0.06) -> str:
    """
    Given a detected corner apex at *apex_pct*, return the best-matching
    named corner name, or a generic "T<n>" label if no match is within
    *tolerance* (in LapDistPct units).
    """
    corners = get_named_corners(track_name)
    if not corners:
        return ""
    best_name = ""
    best_dist = float("inf")
    for i, c in enumerate(corners):
        dist = abs(c["apex_pct"] - apex_pct)
        if dist < best_dist:
            best_dist = dist
            best_name = c["name"]
    if best_dist <= tolerance:
        return best_name
    return ""


def sector_name(track_name: str, sector_idx: int) -> str:
    """Human-readable sector label, e.g. 'S1 (0–29%)'."""
    splits = get_sectors(track_name)
    boundaries = [0.0] + splits + [1.0]
    s = boundaries[sector_idx]
    e = boundaries[sector_idx + 1]
    return f"S{sector_idx + 1} ({s*100:.0f}–{e*100:.0f}%)"
