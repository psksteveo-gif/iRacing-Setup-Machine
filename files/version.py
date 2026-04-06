"""Single source of truth for Optimal Sector version information."""

VERSION = "3.17.0"
APP_NAME = "Optimal Sector"
APP_AUTHOR = "SpicySteveO Gaming LLC"
APP_URL = "https://optimalsector.com"
COPYRIGHT = "Copyright © 2024-2026 SpicySteveO Gaming LLC. All rights reserved."

# Ordered newest-first — each entry: (version_str, [(emoji, headline), ...])
CHANGELOG: list[tuple[str, list[tuple[str, str]]]] = [
    ("3.17.0", [
        ("🌧", "Weather & Track Condition Engine — every setup delta now adjusted for temperature, humidity, track state, time of day, and wind"),
        ("🌡", "Tire pressure corrections: ±0.11 psi per 10°F air temp change + track temp delta"),
        ("💨", "Air density → aero: ISA formula, hot/high-altitude tracks get automatic wing step additions"),
        ("🏁", "Track condition classification: Dry Rubbered/Green/Cold/Hot, Damp, Wet, Very Wet"),
        ("⏱", "Time-of-day awareness: Dawn/Morning/Midday/Afternoon/Evening/Night — grip and rubber notes"),
        ("🎛", "Dashboard weather chip: condition, grip%, pressure correction, time-of-day note"),
        ("🔧", "Recommend dialog: full weather adjustment panel before setup changes"),
    ]),
    ("3.16.0", [
        ("🔒", "Feature gating: 3 free AI calls/session, Pro subscription unlocks unlimited"),
        ("📈", "Setup Learning DB: records outcome of applied changes, scales future magnitudes"),
        ("🧠", "Knowledge base extended with bump stop, exit understeer, wear camber, hydraulic physics"),
    ]),
    ("3.15.0", [
        ("📡", "Complete signal coverage: 68/67 setup-relevant iRacing SDK channels (101%)"),
        ("🛞", "Brake hydraulic discrepancy detection — flags hardware issues vs setup issues"),
        ("💥", "Bump stop detection from spring vs shock deflection ratio"),
        ("🌀", "Steering torque + yaw rate as confirmation signals for US/OS diagnosis"),
        ("🏎", "Speed sector aero rules — differentiates high-DF vs low-DF tracks"),
    ]),
    ("3.14.0", [
        ("⚙", "Per-car-class rule thresholds: GT3/GT4/GTP/LMP2/TCR/Formula calibrated separately"),
        ("🔬", "Exit understeer, tire wear ratios, ride heights fed into AI prompt"),
    ]),
    ("3.13.0", [
        ("🛞", "Tire wear camber rules — outer/inner wear ratio as ground truth for camber"),
        ("🚗", "Exit understeer detection from throttle + lateral G trace"),
        ("📐", "Actual ride height extraction from LFrideHeight channels"),
    ]),
    ("3.12.0", [
        ("⚡", "IBT parse 40-60% faster — zero-copy channel extraction"),
        ("🤖", "AI latency 60-80% lower — Anthropic prompt caching for 18K-char knowledge base"),
        ("📺", "OBS overlay 66% fewer canvas ops — sparkline throttled to 3Hz"),
        ("🎮", "Live dashboard 66% fewer widget reconfigs — UI throttled to 4Hz"),
    ]),
    ("3.11.0", [
        ("🎙", "Pre-session briefing — AI generates 2-sentence brief when iRacing session detected"),
    ]),
    ("3.10.0", [
        ("🎯", "Guided Coaching Flow — works through issues one at a time with AI expansion"),
    ]),
    ("3.9.0", [
        ("🎧", "Voice coaching — post-lap AI tips spoken aloud via pyttsx3"),
        ("📊", "Compare tab: per-corner speed table, AI comparison brief, 24 channels"),
    ]),
    ("3.8.0", [
        ("🔄", "Weekly Series Prep tab — fetches current iRacing schedule via Data API"),
        ("📋", "Settings: subscription section, iRacing EULA compliance note"),
    ]),
    ("3.7.0", [
        ("📡", "SDK Tiers 1-3: shock defl/vel, slip angles, brake hydraulics, body motion"),
        ("📊", "Dashboard confidence chip — analysis quality shown on every session load"),
    ]),
]
