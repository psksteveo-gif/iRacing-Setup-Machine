# Optimal Sector — Developer Notes & Troubleshooting Guide

This file documents known issues, root causes, fixes, and architectural decisions.
Updated every build session. If something breaks, start here.

---

## Architecture Overview

```
main.py (App shell, ~8500 lines)
├── core/
│   ├── ibt_parser.py          — IBT binary file parser, session YAML extraction
│   ├── analysis_engine.py     — AnalysisReport, balance scores, issue detection
│   ├── setup_generator.py     — IBTSignalExtractor → SetupDeltaEngine → SetupAssembler
│   ├── session_enrichments.py — AmbientTempCorrector, BrakeLineSplit, Confidence scorer
│   ├── ai_advisor.py          — Claude API calls, prompt building, JSON parsing
│   ├── knowledge_base.py      — COACHING_KNOWLEDGE_BASE system prompt
│   ├── live_telemetry.py      — LiveTelemetryMonitor (pyirsdk), LiveSample dataclass
│   ├── car_profiles.py        — 74 cars, tire pressure targets, temp windows
│   ├── tech_inspector.py      — Setup legality bounds per car class
│   ├── setup_parser.py        — .htm/.sto setup file parser, StoWriter
│   └── file_watcher.py        — Poll-based IBT/setup folder watcher
├── ui/
│   ├── obs_overlay.py         — Floating always-on-top HUD window
│   └── ds_*.py                — Design system components
└── data/
    ├── track_corners.py        — 63 tracks, sector splits, named corners
    └── templates/              — Car setup templates
```

---

## Pipeline Flow (every IBT load)

```
_process(path)
  └── worker thread
        ├── IBTParser.parse()          → TelemetryData (channels dict + session_info)
        ├── AnalysisEngine.analyze()   → AnalysisReport (balance, issues, tire summary)
        ├── SectorAnalyzer.analyze()   → SectorReport
        ├── [8 more analyzers...]
        └── _on_loaded() on main thread
              ├── enrich_session()     → SessionEnrichments (ambient temp, brake split, confidence)
              ├── generate_setup()     → SetupResult (deltas, tech_pass=True guaranteed)
              └── [renders all tabs]
```

---

## Known Issues & Fixes

### [FIXED 3.6.0] AI tab shows raw markdown instead of cards
**Symptom:** AI recommendations display as `**bold**` text and `## headers` instead of styled cards
**Root cause:** Claude model occasionally prefaced JSON with a sentence like "Here are my recommendations:"
**Fix:** `core/ai_advisor.py` — prompt now leads with "YOU MUST RESPOND WITH VALID JSON ONLY. First char {. Last char }." and `parse_ai_response()` strips all prose before the first `{`
**Files:** `core/ai_advisor.py` — `_build_prompt()`, `parse_ai_response()`
**Test:** After fix, `parse_ai_response("Here is the JSON: {\"summary\": {}}")` should return `{"summary": {}}`

### [FIXED 3.5.0] enrich_session fragile YAML reconstruction
**Symptom:** Ambient temp correction occasionally returns 0.0 even when session has AirTemp
**Root cause:** `enrich_session()` was rebuilding a YAML string (`"AirTemp: X C\n"`) from already-parsed dict fields, then re-parsing it — lossy and brittle
**Fix:** `core/session_enrichments.py` — `enrich_session()` now accepts dict directly. `AmbientTempCorrector.from_session_info_dict()` reads `air_temp_c` key directly
**Files:** `core/session_enrichments.py`, `main.py` (`_on_loaded()`)
**Test:** `enrich_session({'air_temp_c': 20.0}, ...)` should return `ambient_temp_f ≈ 68.0`

### [FIXED 3.5.0] FileWatcher not auto-starting
**Symptom:** Drivers had to manually click "Watch" button to enable auto-detection
**Root cause:** FileWatcher was only started from `_toggle_file_watcher()` button click
**Fix:** `main.py` — `_autostart_file_watcher()` called after 2s delay via `self.after(2000, ...)`
**Files:** `main.py`
**Note:** 2s delay ensures window is fully built before watcher starts

### [KNOWN] Live dashboard .winfo_exists() guard
**Symptom:** Potential crash if live window is closed while samples are still arriving
**Status:** Not yet fixed. `_on_live_sample()` checks `self._live_win.winfo_exists()` but individual widget updates don't guard
**Workaround:** None needed in practice — window destruction happens on main thread
**Priority:** Low — fix before 1.0 launch

### [KNOWN] StoWriter write-back verification
**Symptom:** No confirmation that iRacing actually loaded the written .sto file
**Status:** iRacing SDK doesn't expose "currently loaded setup" confirmation
**Workaround:** Dialog shows path + instructs user to load in garage manually

### [KNOWN] CarIdxLapDistPct traffic detection (Tier 2)
**Symptom:** `_extract_traffic()` may not detect all contaminated laps if CarIdxLapDistPct is not recorded in IBT
**Root cause:** IBT files don't always include opponent channels — depends on session type and iRacing settings
**Workaround:** `contaminated_laps` defaults to 0 when channel missing — conservative (no false positives)

---

## Architectural Decisions

### Why `tech_pass=True` is always guaranteed on SetupResult
Every delta produced by `SetupDeltaEngine` is clamped through `tech_inspector.clamp_to_legal()` before being assembled into the final setup. If clamping changes a value, a `clamped=True` flag is set on the delta and shown as "⚠ adjusted to legal limit" in the UI. This means the Write to iRacing button is always safe to use.

### Why enrichment uses dict path over YAML
The IBT session YAML is a ~500 line text block. Re-parsing it for ambient temp when `ibt_parser.py` already extracted `air_temp_c` into `session_info` dict is wasteful and error-prone. The dict path is authoritative.

### Why setup generator runs on every IBT load (not on demand)
Running `generate_setup()` eagerly means the Recommend to iRacing dialog opens instantly with results already available. The generator takes ~50-100ms on a 20-lap session — imperceptible during the existing analysis pipeline (1-3s total).

### Why the confidence scorer penalizes contaminated laps
A session where 3 of 5 flying laps had traffic is statistically unreliable for setup recommendations — the balance scores are distorted by defensive driving. The 15% max penalty reflects this without completely invalidating the analysis.

### Why we use `generate_setup_brief_stream()` over `get_setup_recommendation_stream()`
The brief stream uses `build_brief_prompt()` which constructs a prompt from actual IBT signal values (e.g. "front avg slip angle: 0.042rad"). The generic recommendation stream works from high-level AnalysisReport summaries. The brief is more specific and actionable.

---

## Key Constants & Config

| Constant | Location | Value | Purpose |
|---|---|---|---|
| `ACCENT` | `main.py` | `#E8611A` | Orange accent — buttons, highlights |
| `DARK` | `main.py` | `#08080A` | App background |
| `PANEL` | `main.py` | `#0F0F13` | Card panels |
| `CARD` | `main.py` | `#14141A` | Inner cards |
| `GREEN` | `main.py` | `#2ECC71` | Positive values, connected |
| `YELLOW` | `main.py` | `#F1C40F` | Warnings |
| `RED` | `main.py` | `#E74C3C` | Errors, critical |
| `BLUE` | `main.py` | `#4A9EE8` | Info, secondary actions |
| `MIN_CONFIDENCE` | `setup_generator.py` | `0.35` | Below this, no deltas generated |
| `MIN_LAPS` | `setup_generator.py` | `3` | Minimum flying laps for recommendations |
| `POLL_INTERVAL_S` | `file_watcher.py` | `3.0` | FileWatcher poll frequency |

---

## SDK Channel Reference (what we read vs what's available)

### Currently Reading (LiveSample)
| Channel | iRacing Name | Used For |
|---|---|---|
| Speed | Speed | Dashboard, overlay |
| Throttle/Brake | Throttle, Brake | Bars, coaching |
| Steering | SteeringWheelAngle | Balance analysis |
| Gear/RPM | Gear, RPM | Dashboard |
| Fuel | FuelLevel, FuelLevelPct | Strategy |
| Lap times | LapCurrentLapTime etc | Dashboard |
| Tire temps | LFtempCL/CM/CR etc | Setup analysis |
| Tire pressures | LFpressure etc | Setup analysis |
| Tire wear | LFwearL/M/R etc | Wear analysis |
| Suspension | LFshockDefl, LFshockVel etc | Setup generator |
| Slip angles | WheelSlipAngle_LF etc | Balance rules |
| Brake line | LFbrakeLinePress etc | Actual split |
| Track temp | TrackTempCrew | Pressure correction |
| Air temp | AirTemp | Pressure correction |
| Sector delta | LapDeltaToBestLap | Overlay, dashboard |
| Position | PlayerCarPosition | Dashboard |
| All cars | CarIdxLapDistPct | Traffic detection |
| Coaching | ShiftGrindRPM, SteeringWheelTorque, PlayerCarSLShiftRPM | Issues tab |
| Aids | dcBrakeBias, dcTractionControl, dcABS, BrakeABSactive | Dashboard |

### Not Yet Reading (future value)
| Channel | Value |
|---|---|
| CarIdxEstTime | Gaps to other cars in real time |
| LapDeltaToOptimalLap | Theoretical best delta |
| PlayerCarSLFirstRPM | Upshift light first stage |
| SteeringWheelTorqueST | Steering torque spike detection |
| YawRate | Rotation rate — complements slip angle |
| Pitch/Roll | Body motion — suspension validation |

---

## Pre-Launch Checklist

- [ ] End-to-end test with real Porsche 992 Cup IBT at Watkins Glen
- [ ] Verify Write to iRacing button produces valid .sto that loads in garage
- [ ] Verify AI tab renders JSON cards not raw markdown on fresh session
- [ ] Verify toast notification fires when iRacing writes new IBT
- [ ] `.winfo_exists()` guard audit on live window widgets
- [ ] Per-car bounds spot-check: 992 Cup ride height minimums
- [ ] Font files in `files/assets/fonts/`: BarlowCondensed-SemiBold.ttf, Barlow-Regular.ttf, JetBrainsMono-Regular.ttf
- [ ] Stripe paywall integration ($12.99/month)
- [ ] iRacing EULA compliance review before public launch
