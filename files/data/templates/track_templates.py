"""
Track Templates & Setup Baselines
Provides baseline setup templates for different car/track combinations.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class TrackInfo:
    name: str
    downforce_demand: str = "medium"    # "low", "medium", "high"
    tire_stress: str = "medium"         # "low", "medium", "high"
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

_TRACKS: Dict[str, TrackInfo] = {
    "Sebring International Raceway": TrackInfo(
        "Sebring International Raceway", "medium", "high",
        "Bumpy surface stresses tires and suspension. Softer springs help compliance."
    ),
    "Daytona International Speedway": TrackInfo(
        "Daytona International Speedway", "low", "medium",
        "Long straights with banking. Low downforce setup, focus on top speed."
    ),
    "Spa-Francorchamps": TrackInfo(
        "Spa-Francorchamps", "medium", "medium",
        "Mix of high-speed and technical sections. Balanced aero approach."
    ),
    "Monza": TrackInfo(
        "Monza", "low", "medium",
        "Ultimate low-downforce track. Minimize drag for straight-line speed."
    ),
    "Nürburgring GP": TrackInfo(
        "Nürburgring GP", "medium", "medium",
        "Technical layout demanding good mechanical grip."
    ),
    "Suzuka International Racing Course": TrackInfo(
        "Suzuka International Racing Course", "high", "high",
        "Fast flowing corners need high downforce. S-curves stress front tires."
    ),
    "Circuit de Barcelona-Catalunya": TrackInfo(
        "Circuit de Barcelona-Catalunya", "medium", "high",
        "Tire degradation track. Manage rear tire stress in final sector."
    ),
    "Mount Panorama Circuit": TrackInfo(
        "Mount Panorama Circuit", "medium", "high",
        "Elevation changes and concrete walls. Setup must handle bumps and camber."
    ),
    "Watkins Glen International": TrackInfo(
        "Watkins Glen International", "medium", "medium",
        "Fast flowing layout. Good aero balance critical through esses."
    ),
    "Road America": TrackInfo(
        "Road America", "medium", "medium",
        "Long track with varied speed corners. Balanced setup needed."
    ),
    "Indianapolis Motor Speedway": TrackInfo(
        "Indianapolis Motor Speedway", "low", "medium",
        "Oval — low drag, focus on mechanical grip and tire management."
    ),
    "Laguna Seca": TrackInfo(
        "Laguna Seca", "medium", "medium",
        "The corkscrew demands good braking stability. Medium downforce."
    ),
    "Silverstone Circuit": TrackInfo(
        "Silverstone Circuit", "high", "medium",
        "High-speed corners demand downforce. Maggots-Becketts is the key."
    ),
    "Imola": TrackInfo(
        "Imola", "medium", "medium",
        "Technical old-school circuit. Kerb riding important."
    ),
    "Le Mans 24h Circuit": TrackInfo(
        "Le Mans 24h Circuit", "low", "medium",
        "Mulsanne straight demands low drag. Porsche curves need some downforce."
    ),
}

# ── Template Database ─────────────────────────────────────────────────────────

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
}


def list_tracks() -> List[str]:
    """Return list of available track names."""
    return sorted(_TRACKS.keys())


def get_track_info(track_name: str) -> Optional[TrackInfo]:
    """Get track information including downforce demand and tire stress."""
    return _TRACKS.get(track_name)


def get_setup_template(car_class: str, track_name: str) -> SetupTemplate:
    """
    Get a baseline setup template for a car class at a specific track.
    car_class: 'gt3' or 'formula'
    track_name: track name string
    """
    car_class = car_class.lower()
    if car_class not in _TEMPLATES:
        car_class = "gt3"

    track_info = get_track_info(track_name)
    downforce = track_info.downforce_demand if track_info else "medium"

    templates = _TEMPLATES[car_class]
    return templates.get(downforce, templates["medium"])
