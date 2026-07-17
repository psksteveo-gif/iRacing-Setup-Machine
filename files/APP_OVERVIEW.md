# Optimal Sector — Application Overview

> **Version:** 3.3.4
> **Developer:** SpicySteveO Gaming LLC
> **Platform:** Windows 10 / 11
> **Stack:** Python 3.12+ · CustomTkinter · Matplotlib · NumPy · Anthropic Claude API
> **Last Updated:** 2026-03-20

---

## Table of Contents

1. [What Is Optimal Sector?](#1-what-is-optimal-sector)
2. [Who Is It For?](#2-who-is-it-for)
3. [How It Works — End-to-End Flow](#3-how-it-works--end-to-end-flow)
4. [Application Architecture](#4-application-architecture)
5. [Module Reference](#5-module-reference)
6. [Feature Deep Dive — Every Tab](#6-feature-deep-dive--every-tab)
7. [AI Integration](#7-ai-integration)
8. [IBT Telemetry Parser](#8-ibt-telemetry-parser)
9. [Setup File System](#9-setup-file-system)
10. [Genetic Algorithm Optimizer](#10-genetic-algorithm-optimizer)
11. [Licensing and Authentication](#11-licensing-and-authentication)
12. [Configuration and Storage](#12-configuration-and-storage)
13. [Build and Packaging](#13-build-and-packaging)
14. [Key Design Decisions](#14-key-design-decisions)

---

## 1. What Is Optimal Sector?

Optimal Sector is a commercial Windows desktop application for iRacing sim racers. It ingests the binary `.ibt` telemetry files that iRacing records during every session and turns them into structured, actionable intelligence — covering driving technique, car setup, tire strategy, fuel planning, and AI-generated coaching recommendations.

The core value proposition is this: after every session a driver has a `.ibt` file sitting in `Documents\iRacing\telemetry`. That file contains 60 Hz recordings of every sensor in the car — throttle, brake, steering, speed, all four tire temperatures, G-forces, fuel level, sector splits, and more. Without a tool like Optimal Sector, that data is invisible. With it, the driver gets an instant diagnosis of what went wrong and what to change.

**The app works entirely offline.** AI features require an Anthropic API key but every analysis tab functions without one. There is no mandatory cloud dependency.

---

## 2. Who Is It For?

| User Type | How They Use It |
|-----------|----------------|
| **Club / amateur racers** | Load a session after a race, read the Issues tab for setup advice, ask AI Advisor for plain-English coaching |
| **League / serious competitors** | Compare sessions across weeks, track setup history, use the Optimizer to find objectively better setup parameters |
| **GT3 / Formula enthusiasts** | Use Track Templates for baseline setups, use the Setup Diff view to track changes per event |
| **Endurance teams** | Use Stint & Tires for tire degradation forecasting and multi-driver fuel strategy planning |
| **Coaches** | Export PDF reports, use Compare tab to overlay two drivers' telemetry |

---

## 3. How It Works — End-to-End Flow

```
iRacing Session
      │
      ▼
  .ibt file
  (binary, 60 Hz)
      │
      ▼
┌─────────────────────┐
│    IBT Parser        │  Reads header, variable definitions, buffer data.
│  (ibt_parser.py)    │  Extracts: car name, track name, all sensor channels,
│                     │  session info YAML, setup dict, session type.
└─────────────────────┘
      │
      ├──► Raw channel arrays (NumPy)  →  Telemetry tab (charts, replay)
      │
      ├──► Lap detection               →  Lap Times tab, Sectors tab
      │
      ├──► Analysis engine             →  Issues tab (scored problem list)
      │
      ├──► Driving style analyzer      →  Driver tab (technique metrics)
      │
      ├──► Sector analyzer             →  Sectors tab (sector splits, theoretical best)
      │
      ├──► Stint analyzer              →  Stint & Tires tab
      │
      ├──► Fuel strategy analyzer      →  Fuel Strategy tab
      │
      ├──► Session YAML → ParsedSetup  →  Setup Files tab (current setup)
      │
      └──► All of above                →  AI Advisor, Optimizer (use analyzed data as context)
```

Every heavy operation (parsing, analysis, AI calls) runs on a **daemon background thread**. The UI never freezes. Results are dispatched back to the main thread via `self.after(0, callback)`.

---

## 4. Application Architecture

### Entry Point

`main.py` — a single 5,000+ line file containing the `App` class (subclass of `ctk.CTk`). This is intentional: CustomTkinter's tab/widget lifecycle is tightly coupled to the root window. All 12 tabs are built as inner classes or methods of `App`.

### Threading Model

```
Main Thread (Tkinter event loop)
    │
    ├── _process()          → Thread: IBT parse + analysis (120s watchdog)
    ├── _run_optimizer()    → Thread: Genetic algorithm (cancelable)
    ├── _stream_ai()        → Thread: Claude API stream
    ├── _generate_note_bg() → Thread: Auto session note generation
    └── File watcher        → Thread: iRacing telemetry folder monitor
```

All threads are `daemon=True`. All UI updates from threads use `self.after(0, lambda: ...)`. Shared data (`self.sessions`, `self._analysis_cache`) is written only from the main thread after thread completion.

### Session Model

The app supports loading up to `MAX_SESSIONS` (default: 5) sessions simultaneously. Sessions are stored as:

```python
self.sessions: list[tuple[IBTData, SessionReport]]
self._analysis_cache: dict[int, tuple[sec, best, stint, style, fuel]]
self._ai_cache: dict[int, str]
```

When the session limit is reached, the oldest session is evicted (LRU). The sidebar shows one card per loaded session; clicking a card calls `_sel()` to switch context.

---

## 5. Module Reference

### `core/` — Backend Modules

| File | Responsibility |
|------|---------------|
| `ibt_parser.py` | Binary `.ibt` file reader. Header parsing, variable extraction, channel arrays as NumPy. |
| `analysis_engine.py` | Issue detection and scoring. Produces a prioritized list of setup and driving problems. |
| `advanced_analysis.py` | Sector analysis, best-lap calculation, stint detection, driving style metrics, fuel strategy, session history. |
| `driving_style.py` | Technique analysis: trail braking index, coast time, steering smoothness, throttle application quality. |
| `car_classifier.py` | Maps car names to classes (GT3, GTE, Formula, Oval, Dirt) and parameter sets for the optimizer. |
| `setup_optimizer.py` | Genetic algorithm optimizer. Takes a `SessionReport` and produces ranked setup change recommendations. |
| `ai_advisor.py` | Anthropic Claude API integration. System prompts, streaming, retry logic, stint-aware context. |
| `setup_parser.py` | Parses iRacing `.htm` setup exports into `ParsedSetup` dataclass. Exports `.htm`, `.json`, `.sto`. |
| `config.py` | API key (keyring), config JSON, iRacing SSO credentials, `%APPDATA%\OptimalSector\` path management. |
| `cloud_sync.py` | JWT auth, license state, leaderboard API, telemetry upload, quota management. |
| `file_watcher.py` | Monitors iRacing telemetry folder for new `.ibt` files. Used by Auto-Load on Session End. |
| `pdf_report.py` | ReportLab-based PDF export of session analysis. |
| `ml_predictor.py` | Lap time predictor using pure NumPy Ridge Regression (no scikit-learn). Trains on past sessions; predicts achievable pace given current setup/conditions. Requires ≥3 sessions. |
| `race_engineer.py` | "Steven" race engineer persona. Accumulates style/stint data across sessions; unlocks after 3 sessions analyzed. Surfaces in the AI Advisor tab as a "🏁 Steven Mode" badge — all AI recommendations become personalized coaching from a persistent race engineer character rather than generic AI output. |

### `ui/` — Tab Modules

| File | Responsibility |
|------|---------------|
| `tab_iracing.py` | iRacing tab: leaderboard, auto-load toggle, partnership features panel. |

### Root Files

| File | Responsibility |
|------|---------------|
| `main.py` | App entry point, all 12 tab UIs, session lifecycle. |
| `version.py` | `VERSION`, `APP_NAME`, `CHANGELOG` — single source of truth. |

---

## 6. Feature Deep Dive — Every Tab

### Dashboard

**Purpose:** At-a-glance session summary. Loads first and is always the landing view.

**Shows:**
- Car name, track name, session type, best lap time
- Balance gauges: understeer/oversteer tendency, tire wear evenness, brake balance
- Tire temperature heatmap (all four corners, inner/middle/outer)
- Session summary card: total laps, fuel used, incident count
- Quick-action buttons: load demo, open file, export PDF

**No data state:** Shows a centered prompt — "Load an IBT file or 'Load Demo' to start."

---

### Telemetry

**Purpose:** Interactive chart viewer for all 60 Hz sensor channels.

**Shows:**
- Speed trace with braking zones highlighted
- Throttle and brake inputs overlaid
- G-force channels (lateral, longitudinal)
- Tire temperatures per corner over the lap
- Track map (2D path reconstructed from LapDistPct + GPS or heading)
- **Lap Replay** — animated playhead that scrubs through the lap with live readouts

**Under the hood:** Charts are rendered via `matplotlib.backends.backend_tkagg.FigureCanvasTkAgg`. Figures are reused (`.clear()`) on each update, not recreated. Memory is freed via `plt.close(fig)` in `EmbedChart.destroy()`.

---

### Issues

**Purpose:** Prioritized list of everything wrong with the setup and driving. The primary diagnostic output.

**How issues are scored:**
1. The `AnalysisEngine` runs a rule set against the `SessionReport`
2. Each rule produces a finding with a severity (Critical / High / Medium / Low) and a confidence score
3. Issues are sorted by `severity × confidence`
4. Each issue includes: symptom, probable cause, recommended fix, affected parameter

**Examples of detected issues:**
- "Rear tires running 12°C hotter than fronts — likely rear ARB too stiff"
- "Trail braking index low — releasing brake too early before apex"
- "Fuel level dropped faster than planned — recalculate stint length"
- "Understeer in slow corners — front ride height may be too low"

**Track map integration:** Each issue with a corner association highlights that corner on the track map in amber/red.

---

### Driver

**Purpose:** Driving technique analysis — separate from setup issues.

**Metrics:**
- **Trail Braking Index** (0–100): How long the driver overlaps brake and steering inputs
- **Coast Time %**: Time spent with both throttle and brake at zero — wasted momentum
- **Steering Smoothness**: Standard deviation of steering rate — high = erratic inputs
- **Throttle Application Quality**: How progressively the driver applies power at corner exit
- **Consistency Score**: Lap-to-lap variation in sector times

**Interpretation:** Each metric includes a benchmark (amateur / intermediate / pro band) so drivers know what to aim for.

---

### Sectors

**Purpose:** Identify which sectors are losing or gaining time, and calculate the theoretical best lap.

**How it works:**
1. Lap boundaries are detected from `LapDistPct` rollovers
2. The track is divided into N sectors (default: 3, user-configurable)
3. Each sector's best time across all laps is extracted
4. Theoretical best = sum of all sector bests (shows how much time is "on the table")
5. Each sector is colored: green (personal best), amber (within 0.3s), red (significant loss)

**Track map:** Sectors are drawn as colored arcs on the 2D track path.

---

### Stint & Tires

**Purpose:** Tire analysis and multi-stint performance tracking.

**Tire analysis:**
- Plots temperature and pressure evolution over the stint
- Flags over-temperature (degradation onset) and under-temperature (cold tires) events
- Pressure recommendations: target operating window vs measured hot pressures
- Tire compound detection from session YAML

**Multi-stint:**
- Detects pit stops from speed + fuel level discontinuities
- Compares pace per stint (lap time trend)
- Flags tire drop-off point (when pace degradation exceeds threshold)

---

### Lap Times

**Purpose:** Lap time chart with fuel correction.

**Shows:**
- Raw lap times over the session
- Fuel-corrected times (adjusting for fuel weight delta per lap)
- Trend line (linear regression) to show pace improvement or degradation
- Outlier laps highlighted (yellow flag laps, pit laps, incidents) — excluded from trend

---

### Setup Files

**Purpose:** Load, view, edit, diff, and export iRacing `.htm` setup files.

**Workflow:**
1. User drops a `.htm` setup file onto the tab (or browses)
2. `SetupParser` parses the HTML table structure into a `ParsedSetup` dataclass
3. All parameters are displayed in a categorized tree view (Tires, Suspension, Aero, etc.)
4. User can edit values inline
5. Export options: `.htm` (iRacing-compatible), `.json` (history), `.sto` (native iRacing format)

**Setup Diff:** Load two setups and see a color-coded diff table of every changed parameter.

**IBT Auto-load:** When an IBT is loaded that contains a `CarSetup` block in its session YAML, the setup is auto-extracted and displayed without requiring a separate `.htm` file.

**Atomic writes:** All export operations write to a temp file then `os.replace()` to the destination. The original is never touched until the write is confirmed complete.

---

### AI Advisor

**Purpose:** Plain-English setup and coaching recommendations powered by Claude.

**Three modes:**

| Mode | What it does |
|------|-------------|
| **Quick Advice** | Ask a free-form question about your session. Claude sees your full session report as context. |
| **Setup Recommendations** | Claude reads the issue list and generates specific garage adjustments (spring rates, dampers, wings, pressures). |
| **Tech Legal Setup** | Claude generates a full baseline setup constrained to a specific car class's technical regulations. |

**Stint awareness:** A session mode dropdown (Race / Qualifying / Endurance) shifts Claude's priorities:
- Qualifying: minimize complexity, maximize single-lap peak grip
- Race: balance across the stint, manage degradation
- Endurance: weight tire wear heavily, conservative on edge parameters

**Streaming:** All AI responses stream token-by-token directly into a scrollable text widget. The user sees the answer appearing in real time, not after a wait.

**Retry logic:** `_stream_with_retry()` retries up to 2 times with exponential backoff (1.5s, 3s) on transient errors (timeout, connection drop, 503/529). Auth errors are not retried.

---

### Optimizer (Genetic Algorithm)

**Purpose:** Systematic setup optimization using a genetic algorithm rather than trial and error.

**How it works:**
1. User selects optimization targets: reduce understeer, improve balance, reduce degradation
2. `SetupOptimizer` reads the car class to get valid parameter ranges and step sizes
3. GA evolves a population of setup candidates over N generations
4. Fitness function scores each candidate based on how well it addresses the targets
5. Top candidates are ranked and shown with specific change recommendations

**Fitness function tuning by stint mode:**
- **Qualifying:** Low complexity penalty (fewer changes = more predictable), no tire-wear penalty
- **Race:** Balanced penalty weighting
- **Endurance:** High tire-wear penalty — parameters that increase wear are penalized heavily

**Car class awareness:** Parameter ranges, step sizes, and valid value sets differ between GT3, GTE, Formula, Oval, and Dirt classes. The optimizer uses class-specific bounds from `car_classifier.py`.

---

### Track Templates

**Purpose:** Baseline setup library for common car+track combinations.

**Contains:** Pre-built baseline setups for GT3 and Formula cars at 40+ tracks. Each template includes:
- Starting tire pressures (hot target)
- Spring rate starting points
- Recommended wing/downforce level (low/medium/high based on track type)
- ARB starting position
- Brake balance starting point

Templates are read-only starting points. The user loads one into the Setup Files tab and then modifies from there.

---

### History

**Purpose:** Track setup changes and pace trends across multiple sessions at the same track.

**What is stored (per session):**
- Car and track names
- Best lap time
- Session type (Practice / Qualifying / Race)
- Lap delta vs previous session at same circuit (green = improvement, red = regression)
- Setup snapshot (flat parameter dict)
- Free-text notes (can be auto-generated by AI if enabled)

**Storage:** `%APPDATA%\OptimalSector\history.json` — rotates to keep the last 100 entries per car+track combination.

**Session type badges:** Each history card shows a colored pill — blue for Practice, yellow for Qualifying, red for Race.

---

### Compare

**Purpose:** Side-by-side comparison of two loaded sessions.

**Comparison views:**
- Lap time delta chart (session A vs session B, lap by lap)
- Telemetry overlay (two traces on the same chart — speed, brake, throttle)
- Sector time table with delta column
- Setup diff (if both sessions have setup data)
- Issue delta (problems solved vs new problems introduced)

**CSV export:** Full comparison table exportable for external analysis.

---

### iRacing Tab

**Purpose:** Integration features that connect to iRacing's live data.

**Sub-features:**

**Leaderboard:** Submit your best lap to the Optimal Sector leaderboard for a specific car+track. View top 10 times and your rank.

**Auto-Load on Session End:** Toggle a file watcher on `~/Documents/iRacing/telemetry`. When iRacing writes a new `.ibt` (at session end), the app detects it and prompts the user to load it — or loads it automatically.

**Partnership Features Panel:** Roadmap display showing which iRacing Data API integrations are live versus pending official partnership:
- Live (✅): Leaderboard submission, IBT parsing, session detection
- Pending (⏳): Direct setup file write, official parameter bounds, step sizes from iRacing, track-specific locked parameters, series technical regulations

---

## 7. AI Integration

### Architecture

The `AIAdvisor` class in `core/ai_advisor.py` manages all Claude interactions. It is stateless — no conversation history is maintained between calls.

### System Prompt Design

Each AI feature has a dedicated system prompt scoped to iRacing setup analysis. Prompts:
- Explicitly instruct Claude to stay on-topic (sim racing, setup, driving technique)
- Include the full `SessionReport` as structured context (not raw telemetry)
- Are never exposed to the user or extractable from the compiled executable

### Context Injection Per Call

Every Claude call includes:

```
[System Prompt — defines role and topic scope]
[Stint Context — qualifying/race/endurance guidance]
[Session Report — car, track, issues, lap times, tire data]
[User Query — the specific question or task]
```

### Token Limits

| Feature | max_tokens |
|---------|-----------|
| Quick Advice | 800 |
| Setup Recommendation | 1500 |
| Tech Legal Setup | 2500 |
| Auto Session Note | 200 |
| Race Engineer Briefing | 1200 |

### Security

- API key stored in OS keyring via the `keyring` library — never written to any file
- User-supplied text is passed through `_sanitize()` before concatenation into prompts
- System prompts are compiled into the executable and are not accessible at runtime via any public interface

---

## 8. IBT Telemetry Parser

### File Format

iRacing `.ibt` files are binary files with this structure:

```
[Header — 112 bytes]
  └── Sample offset, rate, count
  └── Session info offset + length
  └── Variable count
[Variable Definitions — N × 144 bytes each]
  └── type, offset, count, name, description, unit
[Session Info YAML — variable length]
  └── Car setup, session metadata, driver info
[Data Buffers — one tick per sample]
  └── All variable values packed per tick at 60 Hz
```

### Channel Extraction

The parser:
1. Reads the header to locate the variable definition table
2. Parses each variable definition (name, type, byte offset within each tick)
3. Reads the session info YAML block and parses it with PyYAML
4. Reads all data ticks into a single NumPy structured array
5. Extracts each channel as a typed NumPy slice (`float32`, `int32`, `bool`)

### Sanity Clamps

After parsing, physically impossible values are clamped and logged:

| Channel | Valid Range |
|---------|------------|
| Throttle | 0.0 – 1.0 |
| Brake | 0.0 – 1.0 |
| Speed | 0.0 – 150.0 m/s (~540 kph) |
| RPM | 0.0 – 30,000 |
| LapDistPct | 0.0 – 1.0 |
| LatAccel / LonAccel | ±100 m/s² |
| SteeringWheelAngle | ±2π rad |

### Lap Detection

Three-tier fallback:
1. **Primary:** `LapDistPct` rollover from ~1.0 back to ~0.0
2. **Fallback 1:** `LapCurrentLapTime` reset to near zero
3. **Fallback 2:** Time-based split at ~90-second intervals (for sessions missing both channels)

Pit laps are flagged via `PlayerTrackSurface == 3` (pit road) and excluded from pace analysis.

### Robustness

| Condition | Behavior |
|-----------|----------|
| Zero-byte file | Rejected immediately with clear message |
| File < 112 bytes | Rejected (cannot contain a valid header) |
| File > 500 MB | Hard reject before attempting to open |
| File > 200 MB | Warning dialog — user confirms before load |
| Truncated data | `struct.error` caught; parser returns what was successfully read |
| Missing channel | `get_channel()` returns `None`; all consumers check for None |
| Corrupt header | Offset bounds checked; exception raised with file path |

---

## 9. Setup File System

### Supported Formats

| Format | Read | Write | Notes |
|--------|------|-------|-------|
| `.htm` | Yes | Yes | iRacing's native export format (HTML table) |
| `.json` | No | Yes | History/archive format |
| `.sto` | No | Yes | iRacing native internal format (YAML-like text) |

### SetupParser

Parses `.htm` files by:
1. Extracting `<h3>` heading elements as section names
2. Extracting `<table>` rows as key→value pairs under the preceding heading
3. Building a `ParsedSetup` with both a sectioned view and a flat dict

Handles malformed HTML gracefully — falls back to regex text extraction if the table structure is missing.

### SetupExporter

Writes files atomically:
```
1. Open NamedTemporaryFile in the same directory
2. Write all content to temp file
3. Close temp file
4. os.replace(tmp_path, output_path)  ← atomic on Windows and Unix
5. Cleanup temp file in finally block
```

If any step fails, the original file is untouched and a user-friendly error is raised (not a raw exception).

---

## 10. Genetic Algorithm Optimizer

### Overview

The `SetupOptimizer` in `core/setup_optimizer.py` treats setup tuning as a combinatorial optimization problem. Given a list of `OptimizationTarget` objects (e.g., "reduce rear instability", "improve traction"), it finds the combination of parameter changes that best addresses all targets simultaneously.

### Algorithm

```
1. Initialize population of N random setups (within class-specific bounds)
2. For each generation:
   a. Score each individual with the fitness function
   b. Select top 50% (elitism)
   c. Crossover: combine pairs of parents
   d. Mutate: randomly adjust one parameter per individual
   e. Repeat for G generations
3. Return top K individuals ranked by fitness score
```

### Fitness Function

Scores each candidate on:
- **Target alignment:** How well the changes address each stated objective
- **Complexity penalty:** Discourages changing too many parameters at once (harder to evaluate in practice)
- **Tire-wear penalty** (endurance mode only): Parameters known to increase wear are penalized

Qualifying mode reduces the complexity penalty (more changes acceptable for a single-lap peak). Endurance mode increases the tire-wear penalty weight significantly.

### Car Class Awareness

Parameter bounds, step sizes, and available parameters differ per class. The optimizer reads these from `car_classifier.py`'s class-specific parameter dictionaries rather than using a universal set.

---

## 11. Licensing and Authentication

### License State

`cloud_sync.py` manages a `LicenseState` singleton:

```python
@dataclass
class LicenseState:
    access_token: str
    refresh_token: str
    tier: str          # "free" | "pro" | "team"
    display_name: str
    expires_at: datetime
```

### Auth Flow

1. User registers/logs in via the Account tab
2. Backend returns JWT access token + refresh token
3. Access token stored in memory only (not persisted)
4. Refresh token stored in OS keyring
5. On each app launch, refresh token is exchanged for a new access token
6. Feature gating uses `license_state.has_feature(feature_name)`

### Feature Gating

Features are gated at the UI level (buttons/tabs disabled if tier insufficient) and at the API call level (backend enforces quota). Client-side gating is convenience UX, not a security boundary.

### Tier Matrix

| Feature | Free | Pro | Team |
|---------|------|-----|------|
| IBT parsing | ✅ | ✅ | ✅ |
| All analysis tabs | ✅ | ✅ | ✅ |
| AI Advisor (limited) | ✅ | ✅ | ✅ |
| AI Advisor (unlimited) | — | ✅ | ✅ |
| GA Optimizer | — | ✅ | ✅ |
| PDF export | — | ✅ | ✅ |
| Leaderboard | ✅ | ✅ | ✅ |
| Multi-session compare | — | ✅ | ✅ |
| Team leaderboards | — | — | ✅ |

---

## 12. Configuration and Storage

### Storage Locations

| Data | Location |
|------|----------|
| Config JSON | `%APPDATA%\OptimalSector\config.json` |
| Log files | `%APPDATA%\OptimalSector\logs\app.log` (rotating, 5 MB × 3) |
| Session history | `%APPDATA%\OptimalSector\history.json` |
| API key | Windows Credential Manager via `keyring` |
| iRacing credentials | Windows Credential Manager via `keyring` |
| Auth refresh token | Windows Credential Manager via `keyring` |

Nothing sensitive is ever written to a file. The config JSON contains only non-sensitive preferences (last opened directory, window geometry, UI settings).

### Config Keys

| Key | Type | Purpose |
|-----|------|---------|
| `last_dir` | str | Last browsed directory for file dialogs |
| `geometry` | str | Window position and size (`WxH+X+Y`) |
| `last_tab` | str | Active tab on last close |
| `last_chart` | str | Active chart on last close |
| `auto_notes` | bool | Auto-generate session notes after load |
| `ai_consent` | bool | User has agreed to send session data to Claude |
| `last_seen_version` | str | Used to detect when to show What's New dialog |

### Legacy Migration

On first launch after upgrade, `_migrate_legacy_config()` copies `~/.iracing_setup_advisor.json` to the new path automatically. The old file is left in place (not deleted).

---

## 13. Build and Packaging

### Source Dependencies

Key packages (see `requirements.txt` for full list):

| Package | Purpose |
|---------|---------|
| `customtkinter` | Dark-themed modern GUI widgets |
| `matplotlib` | All charts and track map visualizations |
| `numpy` | Telemetry channel arrays and numerical analysis |
| `anthropic` | Claude API streaming client |
| `reportlab` | PDF report generation |
| `keyring` | OS credential manager integration |
| `tkinterdnd2` | Drag-and-drop file loading |
| `PyYAML` | Session info YAML parsing from IBT |
| `requests` | Cloud sync HTTP calls |
| `numpy` (Ridge Regression) | ML lap time predictor — pure NumPy, no external ML library required |

### PyInstaller Build

`build.ps1` orchestrates the build:
1. Runs `pyinstaller iRacingSetupAdvisor.spec`
2. Spec file bundles: all `core/`, `ui/`, `data/` directories, app icon, and hidden imports
3. Output: `dist/OptimalSector/OptimalSector.exe` (one-folder mode)

### Installer

`installer.iss` (Inno Setup 6) creates a Windows installer that:
1. Installs to `Program Files\OptimalSector\`
2. Creates Start Menu shortcut
3. Creates optional Desktop shortcut
4. Registers uninstaller in Add/Remove Programs
5. Associates `.ibt` files with the app (optional)

---

## 14. Key Design Decisions

### Why CustomTkinter Instead of Electron / Web?

The app is a binary file cruncher. Parsing a 500 MB `.ibt` file in Python with NumPy is fast. Doing it via a JavaScript bridge in Electron would be 10–50× slower. CustomTkinter gives native Windows look-and-feel with a Python-native stack that has direct access to NumPy arrays without serialization overhead.

### Why a Single `main.py`?

Tkinter/CustomTkinter tab and widget lifecycle is deeply stateful. Every tab shares `self.cur_data`, `self.cur_rpt`, `self.sessions`, `self._analysis_cache`. Splitting tabs into separate files with cross-references creates circular import and event-binding complexity that outweighs the organizational benefit. Tab UI code is already logically separated by method naming conventions (`_build_dashboard_tab`, `_render_sectors`, etc.).

### Why Not Store the Session Report in a Database?

Session reports are ephemeral — they exist only while a session is loaded. The persistent history (best lap, setup snapshot, notes) is lightweight enough for JSON. A full SQLite schema would add complexity without meaningful benefit at the current data volume.

### Why Claude API Instead of a Local Model?

iRacing setup analysis requires deep domain knowledge about car physics, specific iRacing parameter names, and real-world racing engineering concepts. A local model small enough to run on a sim racing PC would not have the reasoning quality needed for meaningful recommendations. The API cost per query is cents; the value delivered is session-by-session coaching.

### Why Atomic File Writes?

iRacing users frequently race in the same session as they make setup adjustments. The setup file is being read by iRacing at the same time the app might be writing it. A direct overwrite creates a window where iRacing reads a partially-written file and crashes or loads a corrupt setup. `os.replace()` is atomic at the OS level — iRacing either reads the old complete file or the new complete file, never a partial.

---

*Optimal Sector is developed and maintained by SpicySteveO Gaming LLC. Not affiliated with iRacing.com Motorsport Simulations, LLC. iRacing® is a registered trademark of iRacing.com.*
