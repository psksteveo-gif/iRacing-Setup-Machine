"""
Track Templates & Setup Baselines
Provides baseline setup templates for different car/track combinations.
Covers all iRacing road, oval, dirt, and rallycross venues.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class TrackInfo:
    name: str
    downforce_demand: str = "medium"    # "low", "medium", "high"
    tire_stress: str = "medium"         # "low", "medium", "high"
    surface: str = "paved"              # "paved", "dirt", "mixed"
    track_type: str = "road"            # "road", "oval", "rallycross", "street"
    notes: Optional[str] = None


@dataclass
class SetupTemplate:
    front_wing: Optional[str] = None
    rear_wing: Optional[str] = None
    tire_pressures_psi: Optional[Dict[str, float]] = None
    camber_deg: Optional[Dict[str, float]] = None
    spring_notes: Optional[str] = None
    arb_notes: Optional[str] = None
    ride_height_notes: Optional[str] = None
    damper_notes: Optional[str] = None
    brake_bias_pct: Optional[float] = None
    key_adjustments: Optional[List[str]] = None
    priority_notes: Optional[str] = None


# ── Track Database ────────────────────────────────────────────────────────────
# Covers all major iRacing venues.  Fuzzy-matched by _find_track().

_TRACKS: Dict[str, TrackInfo] = {
    # ── North America — Road Courses ──────────────────────────────────────
    "Sebring International Raceway": TrackInfo(
        "Sebring International Raceway", "medium", "high", notes=
        "Bumpy surface stresses tires and suspension. Softer springs help compliance."
    ),
    "Road America": TrackInfo(
        "Road America", "medium", "medium", notes=
        "Long track with varied speed corners. Balanced setup needed."
    ),
    "Road Atlanta": TrackInfo(
        "Road Atlanta", "medium", "high", notes=
        "Fast downhill esses into heavy braking. Rear stability critical."
    ),
    "Laguna Seca": TrackInfo(
        "Laguna Seca", "medium", "medium", notes=
        "The corkscrew demands good braking stability. Medium downforce."
    ),
    "Watkins Glen International": TrackInfo(
        "Watkins Glen International", "medium", "medium", notes=
        "Fast flowing layout. Good aero balance critical through esses."
    ),
    "Virginia International Raceway": TrackInfo(
        "Virginia International Raceway", "medium", "high", notes=
        "Technical with elevation changes. Tire management is key."
    ),
    "Circuit of the Americas": TrackInfo(
        "Circuit of the Americas", "high", "high", notes=
        "Long track with high-speed S-curves. High downforce and tire care needed."
    ),
    "Sonoma Raceway": TrackInfo(
        "Sonoma Raceway", "medium", "high", notes=
        "Elevation changes and tight turns. Good mechanical grip required."
    ),
    "Portland International Raceway": TrackInfo(
        "Portland International Raceway", "medium", "medium", notes=
        "Technical layout with chicane. Medium downforce, smooth inputs."
    ),
    "Lime Rock Park": TrackInfo(
        "Lime Rock Park", "medium", "high", notes=
        "Short track, constant action. High tire stress from non-stop cornering."
    ),
    "Long Beach Street Circuit": TrackInfo(
        "Long Beach Street Circuit", "high", "medium", "paved", "street", notes=
        "Tight street circuit with walls. High downforce, cautious approach."
    ),
    "Miami Homestead": TrackInfo(
        "Miami Homestead", "medium", "medium", notes=
        "Road course with oval banking. Versatile setup needed."
    ),
    "Willow Springs": TrackInfo(
        "Willow Springs", "medium", "high", notes=
        "Fast and flowing with big elevation. High tire degradation."
    ),
    "Summit Point": TrackInfo(
        "Summit Point", "medium", "medium", notes=
        "Short track, good for learning. Medium setup works well."
    ),
    "Mexico City": TrackInfo(
        "Mexico City", "medium", "medium", notes=
        "High altitude reduces aero grip. Slightly higher wing to compensate."
    ),
    # ── North America — Ovals ─────────────────────────────────────────────
    "Daytona International Speedway": TrackInfo(
        "Daytona International Speedway", "low", "medium", "paved", "oval", notes=
        "Long straights with banking. Low downforce setup, focus on top speed."
    ),
    "Indianapolis Motor Speedway": TrackInfo(
        "Indianapolis Motor Speedway", "low", "medium", "paved", "oval", notes=
        "Oval — low drag, focus on mechanical grip and tire management."
    ),
    "Phoenix Raceway": TrackInfo(
        "Phoenix Raceway", "medium", "high", "paved", "oval", notes=
        "Short oval with dogleg. Tire wear critical, manage stagger."
    ),
    "Pocono Raceway": TrackInfo(
        "Pocono Raceway", "low", "medium", "paved", "oval", notes=
        "Three distinct turns, each unique banking. Versatile setup."
    ),
    "Lakeland Speedway": TrackInfo(
        "Lakeland Speedway", "medium", "medium", "paved", "oval", notes=
        "Short oval for stock car beginners."
    ),
    "Southern National Motorsports Park": TrackInfo(
        "Southern National Motorsports Park", "medium", "medium", "paved", "oval", notes=
        "Short track oval. Tight racing, focus on corner exit."
    ),
    # ── Europe ────────────────────────────────────────────────────────────
    "Spa-Francorchamps": TrackInfo(
        "Spa-Francorchamps", "medium", "medium", notes=
        "Mix of high-speed and technical sections. Balanced aero approach."
    ),
    "Monza": TrackInfo(
        "Monza", "low", "medium", notes=
        "Ultimate low-downforce track. Minimize drag for straight-line speed."
    ),
    "Nürburgring GP": TrackInfo(
        "Nürburgring GP", "medium", "medium", notes=
        "Technical layout demanding good mechanical grip."
    ),
    "Nürburgring Combined": TrackInfo(
        "Nürburgring Combined", "high", "high", notes=
        "Nordschleife + GP circuit. Extreme elevation, bumps, and blind corners. Max downforce."
    ),
    "Nürburgring Nordschleife": TrackInfo(
        "Nürburgring Nordschleife", "high", "high", notes=
        "20+ km of extreme challenges. High downforce and forgiving suspension."
    ),
    "Silverstone Circuit": TrackInfo(
        "Silverstone Circuit", "high", "medium", notes=
        "High-speed corners demand downforce. Maggots-Becketts is the key."
    ),
    "Circuit de Barcelona-Catalunya": TrackInfo(
        "Circuit de Barcelona-Catalunya", "medium", "high", notes=
        "Tire degradation track. Manage rear tire stress in final sector."
    ),
    "Imola": TrackInfo(
        "Imola", "medium", "medium", notes=
        "Technical old-school circuit. Kerb riding important."
    ),
    "Le Mans 24h Circuit": TrackInfo(
        "Le Mans 24h Circuit", "low", "medium", notes=
        "Mulsanne straight demands low drag. Porsche curves need some downforce."
    ),
    "Zandvoort": TrackInfo(
        "Zandvoort", "high", "high", notes=
        "Banking in final turns, blind crests. High downforce, compliant suspension."
    ),
    "Oschersleben": TrackInfo(
        "Oschersleben", "medium", "medium", notes=
        "German club circuit. Medium settings, focus on traction zones."
    ),
    "Oulton Park": TrackInfo(
        "Oulton Park", "medium", "high", notes=
        "Undulating British circuit. Tire stress from constant elevation change."
    ),
    "Ledenon": TrackInfo(
        "Ledenon", "medium", "medium", notes=
        "Short French club track. Technical with elevation."
    ),
    # ── Asia / Oceania ────────────────────────────────────────────────────
    "Suzuka International Racing Course": TrackInfo(
        "Suzuka International Racing Course", "high", "high", notes=
        "Fast flowing corners need high downforce. S-curves stress front tires."
    ),
    "Okayama International Circuit": TrackInfo(
        "Okayama International Circuit", "medium", "medium", notes=
        "Short technical Japanese circuit. Good for learning car control."
    ),
    "Mount Panorama Circuit": TrackInfo(
        "Mount Panorama Circuit", "medium", "high", notes=
        "Elevation changes and concrete walls. Setup must handle bumps and camber."
    ),
    "Winton Motor Raceway": TrackInfo(
        "Winton Motor Raceway", "medium", "medium", notes=
        "Australian club circuit. Heavy braking areas, manage rear stability."
    ),
    "Adelaide Street Circuit": TrackInfo(
        "Adelaide Street Circuit", "high", "medium", "paved", "street", notes=
        "Tight street circuit. High downforce, low-speed grip focus."
    ),
    "Oran Park Raceway": TrackInfo(
        "Oran Park Raceway", "medium", "medium", notes=
        "Short Australian track. Good mechanical grip needed."
    ),
    # ── Rally Cross ───────────────────────────────────────────────────────
    "Phoenix Rallycross": TrackInfo(
        "Phoenix Rallycross", "medium", "high", "mixed", "rallycross", notes=
        "Mixed surface rallycross. Compliant suspension, lower pressures for dirt sections."
    ),
    "Winton Rallycross": TrackInfo(
        "Winton Rallycross", "medium", "high", "mixed", "rallycross", notes=
        "Australian rallycross with dirt/paved mix."
    ),
    "Daytona Rallycross": TrackInfo(
        "Daytona Rallycross", "medium", "medium", "mixed", "rallycross", notes=
        "Rallycross layout inside Daytona. Fast with jumps."
    ),
    # ── Dirt Ovals ────────────────────────────────────────────────────────
    "Wheatland Raceway": TrackInfo(
        "Wheatland Raceway", "low", "high", "dirt", "oval", notes=
        "Dirt oval — tire pressure and stagger dominate setup."
    ),
    "Wild West Motorsports Park": TrackInfo(
        "Wild West Motorsports Park", "low", "high", "dirt", "oval", notes=
        "Dirt oval with variable track conditions."
    ),
}


def _find_track(track_name: str) -> Optional[TrackInfo]:
    """Fuzzy-match a track name against the database.

    Tries exact match first, then searches for partial keyword overlap
    so that iRacing names like 'roadamerica full' match 'Road America'.
    """
    if not track_name:
        return None

    # 1. Exact match
    if track_name in _TRACKS:
        return _TRACKS[track_name]

    # 2. Case-insensitive exact
    lower = track_name.lower()
    for key, info in _TRACKS.items():
        if key.lower() == lower:
            return info

    # 3. Keyword overlap — normalise to comparable tokens
    def _tokens(s: str):
        return set(s.lower().replace('-', ' ').replace('_', ' ').split())

    query_tokens = _tokens(track_name)
    best_match = None
    best_score = 0
    for key, info in _TRACKS.items():
        key_tokens = _tokens(key)
        overlap = len(query_tokens & key_tokens)
        if overlap > best_score:
            best_score = overlap
            best_match = info

    return best_match if best_score >= 2 else None


# ── Template Database ─────────────────────────────────────────────────────────
# Templates for every car class × downforce level.

_TEMPLATES: Dict[str, Dict[str, SetupTemplate]] = {
    "gt3": {
        "low": SetupTemplate(
            front_wing="3-4 / 10", rear_wing="3-4 / 10",
            tire_pressures_psi={'LF': 27.0, 'RF': 27.0, 'LR': 26.0, 'RR': 26.0},
            camber_deg={'LF': -3.2, 'RF': -3.2, 'LR': -2.0, 'RR': -2.0},
            spring_notes="Stiffer springs for stability at high speed",
            arb_notes="Softer ARBs for mechanical grip in slow corners",
            ride_height_notes="Low front and rear for reduced drag",
            damper_notes="Stiffer bump to manage aero platform",
            brake_bias_pct=56.0,
            key_adjustments=["Minimize wing angles", "Lower ride height", "Stiffen springs"],
            priority_notes="Top speed is king — sacrifice corner speed for straight-line pace."
        ),
        "medium": SetupTemplate(
            front_wing="5 / 10", rear_wing="5 / 10",
            tire_pressures_psi={'LF': 27.5, 'RF': 27.5, 'LR': 26.5, 'RR': 26.5},
            camber_deg={'LF': -3.0, 'RF': -3.0, 'LR': -1.8, 'RR': -1.8},
            spring_notes="Medium springs — balance compliance and response",
            arb_notes="Medium front and rear ARBs",
            ride_height_notes="Standard ride height for balanced downforce",
            damper_notes="Balanced bump and rebound settings",
            brake_bias_pct=55.0,
            key_adjustments=["Balance front and rear downforce", "Tune ARBs for balance"],
            priority_notes="Balanced approach — work on mechanical grip and aero equally."
        ),
        "high": SetupTemplate(
            front_wing="7-8 / 10", rear_wing="7-8 / 10",
            tire_pressures_psi={'LF': 28.0, 'RF': 28.0, 'LR': 27.0, 'RR': 27.0},
            camber_deg={'LF': -3.5, 'RF': -3.5, 'LR': -2.2, 'RR': -2.2},
            spring_notes="Softer springs to work with high aero load",
            arb_notes="Stiffer ARBs to control body roll with downforce",
            ride_height_notes="Slightly higher to manage ground clearance under load",
            damper_notes="Softer bump for curb compliance",
            brake_bias_pct=54.5,
            key_adjustments=["Maximize wing angles", "Soften springs", "Manage tire temps"],
            priority_notes="Corner speed focus — accept straight-line deficit for faster turns."
        ),
    },
    "gt4": {
        "low": SetupTemplate(
            front_wing="N/A (fixed aero)", rear_wing="Low if adjustable",
            tire_pressures_psi={'LF': 27.5, 'RF': 27.5, 'LR': 26.5, 'RR': 26.5},
            camber_deg={'LF': -2.8, 'RF': -2.8, 'LR': -1.5, 'RR': -1.5},
            spring_notes="Stiffer for high-speed stability",
            arb_notes="Softer ARBs — less aero means more reliance on mechanical grip",
            ride_height_notes="Lowest legal setting to reduce drag",
            brake_bias_pct=56.0,
            key_adjustments=["Minimize drag", "Stiffen springs", "Focus on corner exit traction"],
            priority_notes="GT4 has limited aero — mechanical grip is everything."
        ),
        "medium": SetupTemplate(
            tire_pressures_psi={'LF': 28.0, 'RF': 28.0, 'LR': 27.0, 'RR': 27.0},
            camber_deg={'LF': -2.5, 'RF': -2.5, 'LR': -1.3, 'RR': -1.3},
            spring_notes="Medium springs for balance",
            arb_notes="Medium ARBs",
            brake_bias_pct=55.5,
            key_adjustments=["Balance mechanical grip", "Smooth driving inputs"],
            priority_notes="Balanced GT4 setup — let the car flow."
        ),
        "high": SetupTemplate(
            tire_pressures_psi={'LF': 28.5, 'RF': 28.5, 'LR': 27.5, 'RR': 27.5},
            camber_deg={'LF': -3.0, 'RF': -3.0, 'LR': -1.8, 'RR': -1.8},
            spring_notes="Softer springs for corner compliance",
            arb_notes="Stiffer to control roll",
            brake_bias_pct=55.0,
            key_adjustments=["Soften springs", "Stiffen ARBs", "Manage tire temps"],
            priority_notes="Maximize corner speed at high-downforce tracks."
        ),
    },
    "gtp": {
        "low": SetupTemplate(
            front_wing="Low setting", rear_wing="Low setting",
            tire_pressures_psi={'LF': 22.0, 'RF': 22.0, 'LR': 21.0, 'RR': 21.0},
            camber_deg={'LF': -3.5, 'RF': -3.5, 'LR': -2.0, 'RR': -2.0},
            spring_notes="Stiff springs for aero platform at speed",
            brake_bias_pct=58.0,
            key_adjustments=["Minimize drag", "Lower ride height", "Focus on straight-line speed"],
            priority_notes="LMDh/Hypercar — aero platform and top speed for Le Mans-type tracks."
        ),
        "medium": SetupTemplate(
            front_wing="Medium setting", rear_wing="Medium setting",
            tire_pressures_psi={'LF': 22.5, 'RF': 22.5, 'LR': 21.5, 'RR': 21.5},
            camber_deg={'LF': -3.2, 'RF': -3.2, 'LR': -1.8, 'RR': -1.8},
            brake_bias_pct=57.0,
            key_adjustments=["Balance aero platform with ride", "Tune hybrid deployment"],
            priority_notes="Balanced GTP setup for mixed circuits."
        ),
        "high": SetupTemplate(
            front_wing="High setting", rear_wing="High setting",
            tire_pressures_psi={'LF': 23.0, 'RF': 23.0, 'LR': 22.0, 'RR': 22.0},
            camber_deg={'LF': -3.8, 'RF': -3.8, 'LR': -2.3, 'RR': -2.3},
            brake_bias_pct=56.5,
            key_adjustments=["Max downforce", "Soften springs for compliance"],
            priority_notes="Maximum corner speed for technical circuits."
        ),
    },
    "gte": {
        "low": SetupTemplate(
            front_wing="Low setting", rear_wing="Low setting",
            tire_pressures_psi={'LF': 22.5, 'RF': 22.5, 'LR': 21.5, 'RR': 21.5},
            camber_deg={'LF': -3.3, 'RF': -3.3, 'LR': -1.8, 'RR': -1.8},
            brake_bias_pct=57.5,
            key_adjustments=["Reduce drag", "Stiffen springs for top speed stability"],
            priority_notes="GTE low-drag setup for long straights."
        ),
        "medium": SetupTemplate(
            tire_pressures_psi={'LF': 23.0, 'RF': 23.0, 'LR': 22.0, 'RR': 22.0},
            camber_deg={'LF': -3.0, 'RF': -3.0, 'LR': -1.6, 'RR': -1.6},
            brake_bias_pct=57.0,
            key_adjustments=["Balance aero and mechanical grip"],
            priority_notes="Balanced GTE setup."
        ),
        "high": SetupTemplate(
            tire_pressures_psi={'LF': 23.5, 'RF': 23.5, 'LR': 22.5, 'RR': 22.5},
            camber_deg={'LF': -3.5, 'RF': -3.5, 'LR': -2.0, 'RR': -2.0},
            brake_bias_pct=56.5,
            key_adjustments=["Maximize downforce", "Manage temps"],
            priority_notes="GTE high-downforce setup for technical layouts."
        ),
    },
    "lmp2": {
        "low": SetupTemplate(
            front_wing="Low setting", rear_wing="Low setting",
            tire_pressures_psi={'LF': 22.0, 'RF': 22.0, 'LR': 21.0, 'RR': 21.0},
            camber_deg={'LF': -3.5, 'RF': -3.5, 'LR': -2.0, 'RR': -2.0},
            brake_bias_pct=57.5,
            key_adjustments=["Reduce drag", "Lower ride height"],
            priority_notes="LMP2 low-drag for top speed."
        ),
        "medium": SetupTemplate(
            tire_pressures_psi={'LF': 22.5, 'RF': 22.5, 'LR': 21.5, 'RR': 21.5},
            camber_deg={'LF': -3.2, 'RF': -3.2, 'LR': -1.8, 'RR': -1.8},
            brake_bias_pct=57.0,
            key_adjustments=["Balance aero platform and ride height"],
            priority_notes="Balanced LMP2 setup."
        ),
        "high": SetupTemplate(
            tire_pressures_psi={'LF': 23.0, 'RF': 23.0, 'LR': 22.0, 'RR': 22.0},
            camber_deg={'LF': -3.8, 'RF': -3.8, 'LR': -2.3, 'RR': -2.3},
            brake_bias_pct=56.0,
            key_adjustments=["Maximize wing", "Soften springs for compliance"],
            priority_notes="Maximum cornering speed for technical tracks."
        ),
    },
    "prototype": {
        "low": SetupTemplate(
            tire_pressures_psi={'LF': 23.0, 'RF': 23.0, 'LR': 22.0, 'RR': 22.0},
            camber_deg={'LF': -3.0, 'RF': -3.0, 'LR': -1.5, 'RR': -1.5},
            brake_bias_pct=57.0,
            key_adjustments=["Reduce drag", "Stable aero platform"],
            priority_notes="Older prototype low-drag setup."
        ),
        "medium": SetupTemplate(
            tire_pressures_psi={'LF': 23.5, 'RF': 23.5, 'LR': 22.5, 'RR': 22.5},
            brake_bias_pct=56.5,
            key_adjustments=["Balance grip and stability"],
            priority_notes="Balanced prototype setup."
        ),
        "high": SetupTemplate(
            tire_pressures_psi={'LF': 24.0, 'RF': 24.0, 'LR': 23.0, 'RR': 23.0},
            brake_bias_pct=56.0,
            key_adjustments=["Max wing angles", "Soften springs"],
            priority_notes="Max downforce for technical tracks."
        ),
    },
    "formula": {
        "low": SetupTemplate(
            front_wing="Low setting", rear_wing="Low setting",
            tire_pressures_psi={'LF': 21.0, 'RF': 21.0, 'LR': 20.0, 'RR': 20.0},
            camber_deg={'LF': -3.5, 'RF': -3.5, 'LR': -2.0, 'RR': -2.0},
            spring_notes="Stiff springs for high-speed stability",
            arb_notes="Soft ARBs for kerb riding",
            ride_height_notes="Minimum legal ride height",
            damper_notes="Stiff bump, medium rebound",
            brake_bias_pct=57.0,
            key_adjustments=["Reduce wing angles", "Lower ride height", "Stiffen springs"],
            priority_notes="Minimize drag for top speed circuits."
        ),
        "medium": SetupTemplate(
            front_wing="Medium setting", rear_wing="Medium setting",
            tire_pressures_psi={'LF': 21.5, 'RF': 21.5, 'LR': 20.5, 'RR': 20.5},
            camber_deg={'LF': -3.2, 'RF': -3.2, 'LR': -1.8, 'RR': -1.8},
            spring_notes="Medium springs",
            arb_notes="Medium ARBs",
            ride_height_notes="Standard ride height",
            damper_notes="Balanced settings",
            brake_bias_pct=56.0,
            key_adjustments=["Balance aero and mechanical grip"],
            priority_notes="General-purpose formula car setup."
        ),
        "high": SetupTemplate(
            front_wing="High setting", rear_wing="High setting",
            tire_pressures_psi={'LF': 22.0, 'RF': 22.0, 'LR': 21.0, 'RR': 21.0},
            camber_deg={'LF': -3.8, 'RF': -3.8, 'LR': -2.3, 'RR': -2.3},
            spring_notes="Softer springs for aero compliance",
            arb_notes="Stiffer ARBs for roll control",
            ride_height_notes="Higher front for more front downforce",
            damper_notes="Softer bump for kerb compliance",
            brake_bias_pct=55.0,
            key_adjustments=["Max wing angles", "Soften springs", "Watch tire temps"],
            priority_notes="Maximum downforce for tight/technical circuits."
        ),
    },
    "super_formula": {
        "low": SetupTemplate(
            front_wing="Low setting", rear_wing="Low setting",
            tire_pressures_psi={'LF': 21.0, 'RF': 21.0, 'LR': 20.0, 'RR': 20.0},
            camber_deg={'LF': -3.5, 'RF': -3.5, 'LR': -2.0, 'RR': -2.0},
            brake_bias_pct=58.0,
            key_adjustments=["Minimize drag", "Stiff springs"],
            priority_notes="Super Formula low-drag setup."
        ),
        "medium": SetupTemplate(
            tire_pressures_psi={'LF': 21.5, 'RF': 21.5, 'LR': 20.5, 'RR': 20.5},
            brake_bias_pct=57.0,
            key_adjustments=["Balance downforce and drag"],
            priority_notes="Balanced Super Formula setup."
        ),
        "high": SetupTemplate(
            tire_pressures_psi={'LF': 22.0, 'RF': 22.0, 'LR': 21.0, 'RR': 21.0},
            brake_bias_pct=56.0,
            key_adjustments=["Max wing", "Soften springs for compliance"],
            priority_notes="Max downforce Super Formula for street/technical tracks."
        ),
    },
    "porsche_cup": {
        "low": SetupTemplate(
            front_wing="N/A (rear-engine aero)", rear_wing="Low setting",
            tire_pressures_psi={'LF': 27.0, 'RF': 27.0, 'LR': 26.0, 'RR': 26.0},
            camber_deg={'LF': -3.0, 'RF': -3.0, 'LR': -2.2, 'RR': -2.2},
            brake_bias_pct=52.0,
            key_adjustments=["Low wing", "Rear-engine balance — rear brake bias lower"],
            priority_notes="Rear-engine means more rear brake bias caution. Minimize drag."
        ),
        "medium": SetupTemplate(
            tire_pressures_psi={'LF': 27.5, 'RF': 27.5, 'LR': 26.5, 'RR': 26.5},
            camber_deg={'LF': -2.8, 'RF': -2.8, 'LR': -2.0, 'RR': -2.0},
            brake_bias_pct=51.5,
            key_adjustments=["Balance understeer/oversteer", "Smooth throttle application"],
            priority_notes="Balanced Porsche Cup setup. Respect the rear engine."
        ),
        "high": SetupTemplate(
            tire_pressures_psi={'LF': 28.0, 'RF': 28.0, 'LR': 27.0, 'RR': 27.0},
            camber_deg={'LF': -3.2, 'RF': -3.2, 'LR': -2.5, 'RR': -2.5},
            brake_bias_pct=51.0,
            key_adjustments=["High wing", "Softer rear springs", "Manage rear temps"],
            priority_notes="Max downforce for technical tracks. Watch rear tire temps."
        ),
    },
    "tcr": {
        "low": SetupTemplate(
            tire_pressures_psi={'LF': 28.0, 'RF': 28.0, 'LR': 27.0, 'RR': 27.0},
            camber_deg={'LF': -2.5, 'RF': -2.5, 'LR': -1.2, 'RR': -1.2},
            brake_bias_pct=58.0,
            key_adjustments=["FWD — manage front tire temps", "Reduce drag"],
            priority_notes="FWD touring car — front tires do all the work."
        ),
        "medium": SetupTemplate(
            tire_pressures_psi={'LF': 28.5, 'RF': 28.5, 'LR': 27.5, 'RR': 27.5},
            camber_deg={'LF': -2.3, 'RF': -2.3, 'LR': -1.0, 'RR': -1.0},
            brake_bias_pct=57.5,
            key_adjustments=["Balance front grip and rotation"],
            priority_notes="Balanced TCR setup."
        ),
        "high": SetupTemplate(
            tire_pressures_psi={'LF': 29.0, 'RF': 29.0, 'LR': 28.0, 'RR': 28.0},
            camber_deg={'LF': -2.8, 'RF': -2.8, 'LR': -1.3, 'RR': -1.3},
            brake_bias_pct=57.0,
            key_adjustments=["Maximize front grip", "Trail-brake to rotate"],
            priority_notes="TCR high-downforce. Front tires are the priority."
        ),
    },
    "v8_supercar": {
        "low": SetupTemplate(
            tire_pressures_psi={'LF': 26.0, 'RF': 26.0, 'LR': 25.0, 'RR': 25.0},
            camber_deg={'LF': -2.5, 'RF': -2.5, 'LR': -1.0, 'RR': -1.0},
            brake_bias_pct=56.0,
            key_adjustments=["Reduce drag", "Stiffen rear springs for stability"],
            priority_notes="V8 Supercar low drag for long straights."
        ),
        "medium": SetupTemplate(
            tire_pressures_psi={'LF': 26.5, 'RF': 26.5, 'LR': 25.5, 'RR': 25.5},
            brake_bias_pct=55.5,
            key_adjustments=["Balance mechanical grip with aero"],
            priority_notes="Balanced V8 Supercar setup."
        ),
        "high": SetupTemplate(
            tire_pressures_psi={'LF': 27.0, 'RF': 27.0, 'LR': 26.0, 'RR': 26.0},
            brake_bias_pct=55.0,
            key_adjustments=["Maximize downforce", "Soften springs for compliance"],
            priority_notes="V8 Supercar high-downforce for street circuits."
        ),
    },
    "stock": {
        "low": SetupTemplate(
            tire_pressures_psi={'LF': 30.0, 'RF': 30.0, 'LR': 29.0, 'RR': 29.0},
            spring_notes="Stiffer for high-speed oval stability",
            brake_bias_pct=60.0,
            key_adjustments=["Reduce drag", "Manage stagger", "Focus on tire wear"],
            priority_notes="Stock car — manage aero push and tire degradation."
        ),
        "medium": SetupTemplate(
            tire_pressures_psi={'LF': 31.0, 'RF': 31.0, 'LR': 30.0, 'RR': 30.0},
            brake_bias_pct=59.0,
            key_adjustments=["Balance push vs loose", "Tune track bar and wedge"],
            priority_notes="Balanced stock car setup."
        ),
        "high": SetupTemplate(
            tire_pressures_psi={'LF': 32.0, 'RF': 32.0, 'LR': 31.0, 'RR': 31.0},
            brake_bias_pct=58.0,
            key_adjustments=["More downforce for short tracks", "Stiffer sway bars"],
            priority_notes="Short track / road course stock car setup."
        ),
    },
    "rally_cross": {
        "low": SetupTemplate(
            tire_pressures_psi={'LF': 24.0, 'RF': 24.0, 'LR': 23.0, 'RR': 23.0},
            spring_notes="Soft springs for dirt section compliance",
            brake_bias_pct=55.0,
            key_adjustments=["Lower pressures for dirt grip", "Soft suspension"],
            priority_notes="Rallycross — compromise between dirt and tarmac."
        ),
        "medium": SetupTemplate(
            tire_pressures_psi={'LF': 25.0, 'RF': 25.0, 'LR': 24.0, 'RR': 24.0},
            brake_bias_pct=54.0,
            key_adjustments=["Balance dirt and paved sections"],
            priority_notes="Balanced rallycross setup."
        ),
        "high": SetupTemplate(
            tire_pressures_psi={'LF': 26.0, 'RF': 26.0, 'LR': 25.0, 'RR': 25.0},
            brake_bias_pct=53.0,
            key_adjustments=["More paved-focused", "Slightly stiffer springs"],
            priority_notes="Rallycross with more tarmac sections."
        ),
    },
    "dirt_oval": {
        "low": SetupTemplate(
            tire_pressures_psi={'LF': 14.0, 'RF': 14.0, 'LR': 14.0, 'RR': 14.0},
            spring_notes="Very soft — let the car work with the dirt",
            brake_bias_pct=50.0,
            key_adjustments=["Stagger is king", "Soft springs", "Left-side weight bias"],
            priority_notes="Dirt oval — stagger and weight distribution dominate."
        ),
        "medium": SetupTemplate(
            tire_pressures_psi={'LF': 15.0, 'RF': 15.0, 'LR': 15.0, 'RR': 15.0},
            brake_bias_pct=50.0,
            key_adjustments=["Balance stagger with track conditions"],
            priority_notes="Medium dirt oval setup."
        ),
        "high": SetupTemplate(
            tire_pressures_psi={'LF': 16.0, 'RF': 16.0, 'LR': 16.0, 'RR': 16.0},
            brake_bias_pct=50.0,
            key_adjustments=["Stiffer for slick/packed track conditions"],
            priority_notes="Packed dirt — slightly stiffer setup."
        ),
    },
    "road_rookie": {
        "low": SetupTemplate(
            tire_pressures_psi={'LF': 30.0, 'RF': 30.0, 'LR': 29.0, 'RR': 29.0},
            camber_deg={'LF': -1.5, 'RF': -1.5, 'LR': -1.0, 'RR': -1.0},
            brake_bias_pct=55.0,
            key_adjustments=["Keep it simple", "Focus on smooth inputs"],
            priority_notes="Beginner car — development work matters more than setup."
        ),
        "medium": SetupTemplate(
            tire_pressures_psi={'LF': 30.5, 'RF': 30.5, 'LR': 29.5, 'RR': 29.5},
            brake_bias_pct=54.0,
            key_adjustments=["Smooth inputs", "Consistent braking points"],
            priority_notes="Balanced rookie/beginner setup."
        ),
        "high": SetupTemplate(
            tire_pressures_psi={'LF': 31.0, 'RF': 31.0, 'LR': 30.0, 'RR': 30.0},
            brake_bias_pct=53.0,
            key_adjustments=["More aggressive camber", "Focus on rotation"],
            priority_notes="Aggressive rookie setup for technical tracks."
        ),
    },
    "sports_car": {
        "low": SetupTemplate(
            tire_pressures_psi={'LF': 28.0, 'RF': 28.0, 'LR': 27.0, 'RR': 27.0},
            camber_deg={'LF': -2.5, 'RF': -2.5, 'LR': -1.5, 'RR': -1.5},
            brake_bias_pct=56.0,
            key_adjustments=["Reduce drag", "Stable platform at speed"],
            priority_notes="Sports car — balance fun and speed."
        ),
        "medium": SetupTemplate(
            tire_pressures_psi={'LF': 28.5, 'RF': 28.5, 'LR': 27.5, 'RR': 27.5},
            brake_bias_pct=55.0,
            key_adjustments=["Balance grip and stability"],
            priority_notes="Balanced sports car setup."
        ),
        "high": SetupTemplate(
            tire_pressures_psi={'LF': 29.0, 'RF': 29.0, 'LR': 28.0, 'RR': 28.0},
            brake_bias_pct=54.0,
            key_adjustments=["More camber for cornering", "Softer springs"],
            priority_notes="Technical track sports car setup."
        ),
    },
}


def list_tracks() -> List[str]:
    """Return list of available track names."""
    return sorted(_TRACKS.keys())


def get_track_info(track_name: str) -> Optional[TrackInfo]:
    """Get track information including downforce demand and tire stress.

    Uses fuzzy matching so iRacing telemetry names (e.g. 'roadamerica full')
    resolve to the canonical entry ('Road America').
    """
    return _find_track(track_name)


def get_setup_template(car_class: str, track_name: str) -> SetupTemplate:
    """
    Get a baseline setup template for a car class at a specific track.
    car_class: e.g. 'gt3', 'gtp', 'formula', 'stock', 'rally_cross', etc.
    track_name: track name string (fuzzy-matched)
    """
    car_class = car_class.lower()
    if car_class not in _TEMPLATES:
        # Fall back to closest match or gt3
        car_class = "gt3"

    track_info = get_track_info(track_name)
    downforce = track_info.downforce_demand if track_info else "medium"

    templates = _TEMPLATES[car_class]
    return templates.get(downforce, templates["medium"])
