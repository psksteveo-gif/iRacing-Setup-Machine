# Changelog

All notable changes to iRacing Setup Advisor will be documented in this file.

## [2.1.0] - 2026-03-12

### Added
- **Track Map Visualization** — 2D track map colored by speed or braking zones (uses GPS or reconstructed path)
- **Multi-Stint Comparison** — Auto-detects pit stops and compares performance across stints
- **AI Recommendation Caching** — Cached results load instantly on revisit
- **Session Comparison Export** — Export full comparison CSV with lap deltas, issues, and metrics
- **Lap Replay Animation** — Scrub through telemetry with live speed/throttle/brake readouts
- **History Rotation** — Automatic pruning keeps history DB at manageable size (500 max entries)
- **AI Streaming** — Claude responses stream in real-time instead of waiting for full response
- About dialog with version info, credits, and license
- Keyboard shortcuts (Ctrl+O, Ctrl+D, Ctrl+E, Ctrl+P, Ctrl+B, Ctrl+Q)
- Recent files list (last 8 IBT files)
- Window geometry persistence across sessions
- Progress bar during telemetry loading
- Tooltips on dashboard metrics
- Comprehensive crash handler with log viewer
- Batch IBT processing (load multiple files at once)
- Application icon and professional branding
- File input validation and security hardening

### Fixed
- `data_tick` walrus operator bug in driving style balance event detection
- API key storage now enforces OS keyring with clear warning on fallback

### Security
- Removed plaintext API key storage fallback — keyring-only with user warning
- File size validation on all file inputs
- Path traversal protection on drag-and-drop
- Rate limiting on API calls

## [2.0.0] - 2025-12-01

### Added
- 12-tab GUI (Dashboard, Telemetry, Issues, Driver, Sectors, Stint & Tires, Lap Times, Setup Files, AI Advisor, Templates, History, Compare)
- Full IBT binary parser with 60Hz channel extraction
- Sector analysis with theoretical best calculation
- Driving style analysis (trail braking, coast time, steering reversals)
- Tire degradation model with cliff detection
- Fuel strategy planner with pit stop calculator
- Car classifier with class-specific pressure targets
- AI-powered recommendations via Claude API
- PDF report export via ReportLab
- CSV telemetry export
- Setup file parser (.htm) with diff comparison
- Track template database
- Session history tracker with setup change detection
- Per-lap overlay charts
- G-G friction circle diagram
- Drag-and-drop file loading
- Dashboard with balance gauges and tire heatmap
- Outlier detection and filtering (IQR + 107% median)

## [1.0.0] - 2025-06-01

### Added
- Initial release with basic telemetry analysis
