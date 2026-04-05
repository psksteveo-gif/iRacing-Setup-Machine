# Optimal Sector — Changelog

All notable changes documented here. Format: `[version] - date | what changed | why | files affected`.

---

## [3.6.0] - 2026-04-06 | SDK Tiers 1-3 + Coaching Alerts + JSON Fix

### Added — iRacing SDK Tier 1 (Setup Accuracy)
- `core/live_telemetry.py` — `LiveSample` expanded with:
  - `shock_defl[LF/RF/LR/RR]` — suspension travel in mm (LFshockDefl etc)
  - `shock_vel[LF/RF/LR/RR]` — damper velocity m/s (LFshockVel etc)
  - `slip_angle[LF/RF/LR/RR]` — wheel slip angle radians (WheelSlipAngle_LF etc)
  - `brake_line_press[LF/RF/LR/RR]` — actual hydraulic brake pressure Pa
  - `tire_wear_detail[corner][L/M/R]` — per-zone tire wear 0=new 1=worn
- `core/setup_generator.py` — `SignalBundle` expanded with suspension/slip fields
  - `IBTSignalExtractor._extract_suspension()` — shock travel + damper velocity histogram
  - `IBTSignalExtractor._extract_slip_angles()` — cornering slip angle averages
  - `IBTSignalExtractor._extract_traffic()` — CarIdxLapDistPct proximity detection
  - `SetupDeltaEngine._suspension_rules()` — bottoming detection + spring rate from HS/LS damper ratio
  - `SetupDeltaEngine._slip_angle_rules()` — direct OS/US from front/rear slip ratio

### Added — iRacing SDK Tier 2 (Race Strategy)
- `core/live_telemetry.py` — `LiveSample` race fields:
  - `car_position`, `car_class_position` — live race/class position
  - `session_laps_remain` — laps remaining in session
  - `car_idx_lap_dist`, `car_idx_lap` — all competitors' positions (traffic detection)
- `main.py` — live dashboard shows `P{n}` position label, P1 highlighted in accent
- `main.py` — status bar includes position in real-time

### Added — iRacing SDK Tier 3 (Driver Coaching)
- `core/live_telemetry.py` — `LiveSample` coaching fields:
  - `brake_bias_pct` — dcBrakeBias × 100
  - `tc_level`, `abs_level` — driver aid levels
  - `shift_rpm`, `blink_rpm` — PlayerCarSLShiftRPM / PlayerCarSLBlinkRPM
  - `shift_grind_rpm` — ShiftGrindRPM (mis-shift detection)
  - `steering_torque` — SteeringWheelTorque (understeer load)
  - `clutch_pct` — ClutchPct
  - `is_on_track`, `is_in_garage` — session state flags
- `main.py` — `_render_sdk_coaching_alerts()` — collapsible coaching cards in Issues tab:
  - **Shift grind alert** — detects ShiftGrindRPM > 100 events, flags mis-shifts
  - **Short-shifting alert** — compares shift RPM vs PlayerCarSLShiftRPM target
  - **Steering torque alert** — high torque/lateral-G ratio = understeer load signal

### Fixed
- `core/ai_advisor.py` — JSON enforcement now leads the prompt with explicit
  "YOU MUST RESPOND WITH VALID JSON ONLY. First char {. Last char }."
  **Root cause:** Model occasionally prefaced JSON with prose, breaking card renderer
  **Fix:** Hard constraint at top of user message + improved `parse_ai_response()` to strip prose before `{`
- `core/session_enrichments.py` — `AnalysisConfidenceScorer.score()` now accepts
  `contaminated_laps` param — applies up to 15% penalty for traffic-polluted sessions

### Changed
- `ui/obs_overlay.py` — OBS HUD now prefers `LapDeltaToBestLap` (SDK) over interpolated reference lap delta. Shows `SDK Δ` vs `Ref Δ` source indicator. Added track temp, ABS (yellow when active), TC (green when active) to conditions row.
- `main.py` — live dashboard conditions row added: Δ label, track temp, ABS, TC, position

---

## [3.5.0] - 2026-04-06 | Auto IBT Detection + Session Pipeline Wiring

### Added
- `main.py` — `_autostart_file_watcher()` — FileWatcher starts automatically 2s after launch
- `main.py` — `_on_new_ibt_detected()` + `_show_ibt_toast()` — green banner notification when iRacing writes a new .ibt. Shows filename, "Load & Analyze" / "Dismiss" buttons, auto-dismisses after 30s
- `main.py` — `_on_loaded()` now runs `enrich_session()` automatically on every IBT load:
  builds flying-lap mask, extracts AirTemp/TrackTemp from session_info dict,
  runs AmbientTempCorrector + BrakeLineSplitAnalyzer + DownforceTrimAdvisor + AnalysisConfidenceScorer
- `main.py` — `_on_loaded()` now runs `generate_setup()` automatically after enrichments:
  full IBT→setup pipeline with tech_pass guarantee. Stored as `self.cur_setup_result`
- `core/session_enrichments.py` — `AmbientTempCorrector.from_session_info_dict()` — direct dict extraction (no regex)
- `core/live_telemetry.py` — `LiveSample` new fields: `track_temp_c`, `air_temp_c`, `lap_delta_to_best`, `lap_delta_to_optimal`, `lap_delta_valid`, `tire_wear`, `brake_abs_active`, `tc_active`

### Fixed
- `core/session_enrichments.py` — `enrich_session()` now accepts dict or str for `session_info_str`
  **Root cause:** Was rebuilding YAML string from already-parsed fields — fragile and lossy
  **Fix:** Added `from_session_info_dict()` path, dict checked first

---

## [3.4.0] - 2026-04-05 | Setup Generator UI — Write to iRacing + Driver Brief

### Added
- `main.py` — `_show_recommend_dialog()` now has 3 new sections:
  1. **IBT-Derived Setup Changes panel** — shows generator's changes_table grouped by garage tab
     with current→recommended values, color-coded deltas, data-backed reasoning per change,
     green TECH LEGAL badge, confidence %, lap count
  2. **Write to iRacing Now button** (green) — applies all deltas via StoWriter,
     saves `OS_Generated_YYYYMMDD_HHMM.sto` directly to car's iRacing setups folder
  3. **Driver Brief panel** — streams `generate_setup_brief_stream()` when generator result
     available; falls back to `get_setup_recommendation_stream()` for backward compatibility

---

## [3.3.0] - 2026-04-05 | Setup Generator + Car Profiles + Track DB Expansion

### Added
- `core/setup_generator.py` — IBT→setup engine (1,392 lines):
  - `IBTSignalExtractor` — maps AnalysisReport/CornerReport to `SignalBundle`
  - `SetupDeltaEngine` — confidence-gated rules: brake bias, ARB, springs, camber,
    tire pressure, differential, dampers, aero. Min 3 laps + confidence threshold
  - `SetupAssembler` — applies deltas to baseline, clamps through `tech_inspector`,
    runs `validate_setup()`, guarantees `tech_pass=True` on output
  - `build_brief_prompt()` — data-specific AI prompt builder (references actual IBT numbers)
- `core/car_profiles.py` — 74 cars, 121 path entries from iracing-setup-advisor data:
  per-car target hot pressures, temp windows, ride height minimums, engine layout notes
- `core/ai_advisor.py` — `generate_setup_brief_stream()` streams driver brief from SetupResult
- `data/track_corners.py` — 63 total tracks (was 48): Barber, Bathurst, Oulton Park,
  Hockenheimring, Long Beach, Fuji, Okayama, Snetterton, Motegi, Vallelunga, + 8 more

### Changed
- `core/tech_inspector.py` — `validate_setup()` now accepts `car_name` param,
  enforces per-car ride height minimums from `car_profiles` on top of class bounds

---

## [3.2.0] - 2026-04-05 | Session Enrichments + Ambient Temp Correction

### Added
- `core/session_enrichments.py` — 4 new capabilities:
  1. `AmbientTempCorrector` — piecewise cold pressure correction from ambient temp
     (<40°F: +0.45psi/10°F, 40-70°F: +0.35, >70°F: -0.25)
  2. `BrakeLineSplitAnalyzer` — reads LFbrakeLinePress etc, computes actual vs dial split
  3. `DownforceTrimAdvisor` — peak speed → High/Medium/Low downforce recommendation
  4. `AnalysisConfidenceScorer` — 0-1 score, missing channels, lap count, ambient flag

---

## [3.1.0] - 2026-04-05 | Theme Recolor + Design System

### Changed
- Full purple→racing dark palette across all UI files:
  `DARK=#08080A`, `PANEL=#0F0F13`, `CARD=#14141A`, `ACCENT=#E8611A`,
  `BLUE=#4A9EE8`, `TEXT=#F0EEE8`, `DIM=#8A8890`
- Files changed: `ui/theme.py`, `main.py`, `ui/tab_corners.py`, `ui/tab_stint.py`, `ui/tab_telemetry.py`

### Added
- `ui/ds_theme.py`, `ui/ds_components.py`, `ui/ds_base_tab.py`, `ui/ds_ai_renderer.py` — design system library
- AI tab renders structured JSON cards instead of raw markdown text

---

## [2.1.0] - 2026-03-12 | Track Map, Multi-Stint, AI Caching

### Added
- Track Map Visualization — 2D track map colored by speed or braking zones
- Multi-Stint Comparison — auto-detects pit stops and compares performance
- AI Recommendation Caching — cached results load instantly on revisit
- Session Comparison Export — CSV with lap deltas, issues, and metrics
- Lap Replay Animation — scrub through telemetry with live readouts
- History Rotation — automatic pruning keeps DB at manageable size
- AI Streaming — Claude responses stream in real-time
- About dialog, keyboard shortcuts, recent files, window geometry persistence
- Progress bar during loading, tooltips, crash handler, batch IBT processing

### Fixed
- `data_tick` walrus operator bug in driving style balance event detection
- API key storage enforces OS keyring

---

## [2.0.0] - 2025-12-01 | Full GUI Rewrite

### Added
- 12-tab GUI, IBT parser, sector analysis, driving style, tire degradation,
  fuel strategy, car classifier, AI recommendations, PDF export, setup diff,
  track templates, history tracker, G-G diagram, drag-and-drop

---

## [1.0.0] - 2025-06-01 | Initial Release

### Added
- Basic IBT parsing and tire temperature analysis

---

## [3.7.0] - 2026-04-06 | Body Motion, Confidence Chip, Safety Guards

### Added
- `core/live_telemetry.py` — `LiveSample` new fields:
  - `yaw_rate` — YawRate rad/s (rotation around vertical axis)
  - `pitch_rate` — PitchRate rad/s (nose up/down)
  - `roll_rate` — RollRate rad/s (body roll left/right)
- `core/setup_generator.py` — Body motion analysis pipeline:
  - `SignalBundle`: `roll_rate_cornering`, `pitch_rate_braking`, `body_motion_confidence`
  - `IBTSignalExtractor._extract_body_motion()` — reads RollRate/PitchRate channels,
    filters to cornering (|LatAccel| > 3G) and braking (Brake > 0.3) windows
  - `SetupDeltaEngine._body_motion_rules()`:
    - Roll rate > 0.8 rad/s → ARB stiffening recommendation (front/rear from balance score)
    - Pitch rate > 1.0 rad/s → front spring rate increase recommendation
- `main.py` — Dashboard **Analysis Confidence chip**:
  - Colored border (green/yellow/red based on score)
  - Shows: label (High/Medium/Low), score %, flying laps count
  - Lists up to 2 issues inline (traffic contamination, missing channels, etc.)
- `main.py` — `_render_sdk_coaching_alerts()`:
  - **Shift grind**: ShiftGrindRPM > 100 events
  - **Short-shifting**: upshift RPM vs PlayerCarSLShiftRPM target, flags if >25% below
  - **Steering torque**: high torque/lateral-G ratio flags understeer load

### Fixed
- `main.py` — `_on_live_sample()` live dashboard widget updates wrapped in `try/except`
  **Root cause:** Race condition — window can be destroyed between `winfo_exists()` check
  and individual `.configure()` calls, causing `TclError`
  **Fix:** Entire connected-state update block wrapped in try/except, sets `_live_win=None`
  on exception so next sample skips gracefully
  **Files:** `main.py` — `_on_live_sample()`

### Changed
- `core/setup_generator.py` — `_body_motion_rules()` now runs in `compute_deltas()`
  after slip angle and suspension rules (all Tier 1 physics rules run before heuristic rules)

---

## [3.8.0] - 2026-04-06 | Compare Tab Upgrades

### Added
- `main.py` — `_draw_ab_corner_speeds()` — per-corner minimum speed table:
  - Detects speed minima on each driver's best lap using local min algorithm
  - Matches corners between sessions by track position (within 5%)
  - Ranks by largest delta, shows top 12 corners color-coded green/red
  - Data: Position %, A km/h, B km/h, Δ km/h with inline bar visualization
- `main.py` — `_draw_ab_ai_brief()` — AI comparison streaming panel:
  - Streams focused 3-4 sentence analysis via claude-haiku-4-5-20251001
  - Prompt: session A vs B, lap delta, balance scores, top issues
  - Plain text response (not JSON) — readable as narrative
  - "Compare with AI" button, streams in real-time
- `main.py` — A/B compare channel selector expanded from 13 → 24 channels:
  - Added: LFshockDefl/Vel (suspension), WheelSlipAngle_LF/RF (slip angles),
    LFbrakeLinePress/RFbrakeLinePress (brake line), SteeringWheelTorque,
    YawRate, RollRate, FuelLevel
  - Width: 150 → 180px to fit longer channel names

### Notes
- Corner detection uses 1000-point interpolated grid, 5% window deduplication
- AI brief uses Haiku (fastest/cheapest) — not Sonnet — appropriate for short analysis
