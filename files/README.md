# 🏎 iRacing Setup Advisor

> Professional telemetry analysis and setup optimization for iRacing — powered by AI.

![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue)
![License MIT](https://img.shields.io/badge/License-MIT-green)
![Platform Windows](https://img.shields.io/badge/Platform-Windows-lightgrey)

## What It Does

iRacing Setup Advisor loads your `.ibt` telemetry files and provides instant, actionable analysis across 12 specialized tabs:

| Tab | Purpose |
|-----|---------|
| **Dashboard** | At-a-glance session overview with balance gauges and tire heatmap |
| **Telemetry** | Interactive charts (speed, temps, G-forces, track map, replay) |
| **Issues** | Prioritized problems with severity ratings and fix recommendations |
| **Driver** | Driving style metrics — trail braking, coast time, steering smoothness |
| **Sectors** | Sector-by-sector analysis with theoretical best lap calculation |
| **Stint & Tires** | Tire degradation, pressure recommendations, multi-stint comparison |
| **Lap Times** | Raw vs fuel-corrected times with trend analysis |
| **Setup Files** | Parse, edit, diff, and export iRacing .htm setup files |
| **AI Advisor** | Claude-powered natural language recommendations (streaming) |
| **Templates** | Track-specific baseline setups for GT3 and Formula cars |
| **History** | Track setup changes across sessions with automatic rotation |
| **Compare** | Side-by-side session comparison with telemetry overlay and CSV export |

## Key Features

- **Binary IBT parsing** — reads all iRacing telemetry channels at 60Hz
- **AI recommendations** — Claude analyzes your data and provides coaching tips
- **Track map visualization** — 2D colored maps using GPS or reconstructed path
- **Lap replay** — animate through telemetry with live readouts
- **Multi-stint detection** — auto-detects pit stops and compares performance
- **Fuel strategy planner** — pit stop calculator with race planning
- **PDF & CSV export** — professional reports for sharing and review
- **Drag-and-drop** — drop .ibt or .htm files directly onto the app
- **No cloud dependency** — all analysis runs locally (AI is optional)

## Installation

### Pre-built Installer (Recommended)

1. Download `iRacingSetupAdvisor_Setup.exe` from the latest release
2. Run the installer — no Python needed
3. Launch from Start Menu or Desktop shortcut

### From Source

```bash
# Clone the repo
git clone https://github.com/iRacingSetupMachine/iRacing-Setup-Advisor.git
cd iRacing-Setup-Advisor/files

# Install dependencies
pip install -r requirements.txt

# Run
python main.py
```

### Build Standalone Executable

```powershell
# From the files/ directory
.\build.ps1
```

Requires [PyInstaller](https://pyinstaller.org/) and optionally [Inno Setup 6](https://jrsoftware.org/isinfo.php) for the Windows installer.

## AI Setup (Optional)

The AI Advisor tab uses Claude (Anthropic) for natural language recommendations. To enable:

1. Get an API key from [console.anthropic.com](https://console.anthropic.com/)
2. Open **Settings** (⚙) in the app
3. Paste your API key — it's stored in your OS credential manager (keyring), never in plaintext

The app works fully without an API key — AI is an optional enhancement.

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+O` | Open IBT file |
| `Ctrl+D` | Load demo session |
| `Ctrl+E` | Export CSV |
| `Ctrl+P` | Export PDF |
| `Ctrl+B` | Batch load IBT files |
| `Ctrl+Q` | Quit |

## Requirements

- **OS:** Windows 10/11
- **Python:** 3.10+ (if running from source)
- **RAM:** 4 GB minimum, 8 GB recommended
- **Display:** 1280×720 minimum

## Dependencies

| Package | Purpose |
|---------|---------|
| customtkinter | Modern dark-themed GUI |
| matplotlib | Charts and visualizations |
| numpy | Numerical analysis |
| anthropic | Claude AI API client |
| reportlab | PDF report generation |
| keyring | Secure API key storage |
| tkinterdnd2 | Drag-and-drop support |

## Project Structure

```
files/
├── main.py                  # GUI application (entry point)
├── version.py               # Version info
├── requirements.txt         # Python dependencies
├── build.ps1                # Build automation
├── iRacingSetupAdvisor.spec # PyInstaller config
├── installer.iss            # Inno Setup installer
├── core/
│   ├── ibt_parser.py        # Binary .ibt file reader
│   ├── analysis_engine.py   # Issue detection & scoring
│   ├── advanced_analysis.py # Sectors, fuel, stint, history
│   ├── driving_style.py     # Driver technique analysis
│   ├── car_classifier.py    # Car class detection
│   ├── ai_advisor.py        # Claude AI integration
│   ├── setup_parser.py      # .htm setup file parser
│   └── pdf_report.py        # PDF export
└── data/
    └── templates/
        └── track_templates.py  # Track database & setup baselines
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

MIT License — see [LICENSE](LICENSE) for details.

## Disclaimer

This software is not affiliated with, endorsed by, or connected to iRacing.com Motorsport Simulations, LLC. iRacing® is a registered trademark of iRacing.com. All telemetry data belongs to the user.
