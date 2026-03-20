"""Single source of truth for Optimal Sector version information."""

VERSION = "3.3.3"
APP_NAME = "Optimal Sector"
APP_AUTHOR = "SpicySteveO Gaming LLC"
APP_URL = "https://github.com/psksteveo-gif/iRacing-Setup-Machine"
COPYRIGHT = "Copyright © 2024-2026 SpicySteveO Gaming LLC. All rights reserved."

# Ordered newest-first — each entry: (version_str, [(emoji, headline), ...])
CHANGELOG: list[tuple[str, list[tuple[str, str]]]] = [
    ("3.3.3", [
        ("🪟", "Window title shows loaded car & track — always know what session is active"),
        ("🛡",  "Window off-screen recovery — restored position clamped to visible screen area"),
        ("📂", "Config & logs moved to %APPDATA%\\OptimalSector\\ (legacy location auto-migrated)"),
        ("🔁", "API retry logic — transient Claude API errors retried with exponential backoff"),
        ("🩺", "IBT channel sanity checks — out-of-range telemetry values clamped automatically"),
        ("⚡", "Zero-length & corrupt IBT files rejected early with clear error messages"),
        ("📏", "File size warning for IBT files over 200 MB; hard reject over 500 MB"),
    ]),
    ("3.3.2", [
        ("🔔", "What's New dialog — see release notes on every update"),
        ("🤝", "Partnership Features panel — tracks iRacing integration roadmap"),
        ("📡", "Auto-Load on Session End — detects new IBT files while iRacing is open"),
    ]),
    ("3.3.1", [
        ("📊", "History: session type badge + color-coded lap delta vs previous session"),
        ("🏁", "Session mode (Race/Qualifying/Endurance) selector on Optimizer & AI tabs"),
        ("⚙",  "Optimizer fitness function tuned per stint mode (tire wear, complexity)"),
        ("🤖", "AI prompt now includes qualifying/race/endurance-specific setup guidance"),
        ("🔍", "Detected car class shown in Optimizer and AI tabs; warning when unknown"),
    ]),
    ("3.3.0", [
        ("🏎",  "Renamed to Optimal Sector"),
        ("🏁", "Oval & dirt setup parameters — stagger, wedge, track bar, bite bar, etc."),
        ("🌍", "Corner database expanded: 27 → 48 tracks including ovals and dirt ovals"),
        ("🧬", "Class-aware GA optimizer — separate parameter sets per car class"),
    ]),
    ("3.2.0", [
        ("📡", "Full IBT channel expansion — all iRacing SDK channels available"),
        ("🗂",  "YAML data mining — extracts CarSetup blocks from IBT session info"),
        ("🎨", "UI scaling and layout fixes across all tabs"),
    ]),
    ("3.1.0", [
        ("🗺",  "Track maps on Issues tab with corner markers"),
        ("🚗", "Car/track coverage fixes — more cars auto-classified correctly"),
        ("⚖",  "Setup recommendation engine with detailed garage notes"),
    ]),
]
