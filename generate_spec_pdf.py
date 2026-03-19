"""
Generates the iRacing Setup Machine — High-Level Technical Specification PDF.
Run: python generate_spec_pdf.py
Output: iRacing_Setup_Machine_TechSpec.pdf (same directory)
"""
import os
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak, KeepTogether
)
from reportlab.platypus.tableofcontents import TableOfContents
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from datetime import datetime

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "iRacing_Setup_Machine_TechSpec.pdf")
W, H = A4

# ── Palette ───────────────────────────────────────────────────────────────────
C_BG       = colors.HexColor("#0d1117")
C_ACCENT   = colors.HexColor("#e74c3c")
C_BLUE     = colors.HexColor("#2980b9")
C_GREEN    = colors.HexColor("#27ae60")
C_YELLOW   = colors.HexColor("#f39c12")
C_PURPLE   = colors.HexColor("#8e44ad")
C_DARK     = colors.HexColor("#1a1a2e")
C_MID      = colors.HexColor("#2c3e50")
C_LIGHT    = colors.HexColor("#ecf0f1")
C_DIM      = colors.HexColor("#7f8c8d")
C_WHITE    = colors.white
C_BLACK    = colors.black
C_ROW_ALT  = colors.HexColor("#f8f9fa")
C_ROW_HDR  = colors.HexColor("#2c3e50")

# ── Styles ────────────────────────────────────────────────────────────────────
SS = getSampleStyleSheet()

def sty(name, parent="Normal", **kw):
    return ParagraphStyle(name, parent=SS[parent], **kw)

COVER_TITLE  = sty("CoverTitle",  fontSize=32, textColor=C_WHITE,   leading=40, alignment=TA_CENTER, spaceAfter=6)
COVER_SUB    = sty("CoverSub",    fontSize=16, textColor=C_ACCENT,  leading=22, alignment=TA_CENTER, spaceAfter=4)
COVER_META   = sty("CoverMeta",   fontSize=11, textColor=C_DIM,     leading=16, alignment=TA_CENTER)
H1           = sty("H1",          fontSize=20, textColor=C_ACCENT,  leading=26, spaceBefore=18, spaceAfter=6,  fontName="Helvetica-Bold")
H2           = sty("H2",          fontSize=14, textColor=C_BLUE,    leading=20, spaceBefore=14, spaceAfter=4,  fontName="Helvetica-Bold")
H3           = sty("H3",          fontSize=11, textColor=C_MID,     leading=16, spaceBefore=10, spaceAfter=3,  fontName="Helvetica-Bold")
BODY         = sty("Body",        fontSize=9,  textColor=C_BLACK,   leading=14, spaceAfter=4,  alignment=TA_JUSTIFY)
BODY_SMALL   = sty("BodySmall",   fontSize=8,  textColor=C_MID,     leading=12, spaceAfter=2)
CODE         = sty("Code",        fontSize=8,  textColor=C_DARK,    leading=12, fontName="Courier", backColor=C_ROW_ALT, leftIndent=12, rightIndent=12, spaceAfter=4)
BULLET       = sty("Bullet",      fontSize=9,  textColor=C_BLACK,   leading=13, spaceAfter=2, leftIndent=14, bulletIndent=6)
CAPTION      = sty("Caption",     fontSize=8,  textColor=C_DIM,     leading=11, alignment=TA_CENTER, spaceAfter=6)
TABLE_HDR    = sty("TableHdr",    fontSize=8,  textColor=C_WHITE,   leading=11, fontName="Helvetica-Bold", alignment=TA_CENTER)
TABLE_CELL   = sty("TableCell",   fontSize=8,  textColor=C_BLACK,   leading=11)
TABLE_CELL_C = sty("TableCellC",  fontSize=8,  textColor=C_BLACK,   leading=11, alignment=TA_CENTER)
TIER_FREE    = sty("TierFree",    fontSize=8,  textColor=C_DIM,     leading=11, alignment=TA_CENTER)
TIER_PRO     = sty("TierPro",     fontSize=8,  textColor=C_BLUE,    leading=11, alignment=TA_CENTER, fontName="Helvetica-Bold")
TIER_TEAM    = sty("TierTeam",    fontSize=8,  textColor=C_PURPLE,  leading=11, alignment=TA_CENTER, fontName="Helvetica-Bold")

def b(text): return f"<b>{text}</b>"
def i(text): return f"<i>{text}</i>"
def c(text, col): return f'<font color="{col}">{text}</font>'
def bullet(text, style=BULLET): return Paragraph(f"• {text}", style)
def hr(): return HRFlowable(width="100%", thickness=0.5, color=C_DIM, spaceAfter=8, spaceBefore=4)
def spacer(h=0.3): return Spacer(1, h*cm)

def section_rule(color=C_ACCENT):
    return HRFlowable(width="100%", thickness=2, color=color, spaceAfter=6, spaceBefore=2)

def tbl(data, col_widths, hdr_rows=1):
    t = Table(data, colWidths=col_widths)
    style = [
        ("BACKGROUND",  (0,0), (-1, hdr_rows-1), C_ROW_HDR),
        ("TEXTCOLOR",   (0,0), (-1, hdr_rows-1), C_WHITE),
        ("FONTNAME",    (0,0), (-1, hdr_rows-1), "Helvetica-Bold"),
        ("FONTSIZE",    (0,0), (-1,-1),           8),
        ("ROWBACKGROUNDS", (0, hdr_rows), (-1,-1), [C_WHITE, C_ROW_ALT]),
        ("GRID",        (0,0), (-1,-1),           0.3, C_DIM),
        ("VALIGN",      (0,0), (-1,-1),           "TOP"),
        ("TOPPADDING",  (0,0), (-1,-1),           4),
        ("BOTTOMPADDING",(0,0),(-1,-1),           4),
        ("LEFTPADDING", (0,0), (-1,-1),           5),
        ("RIGHTPADDING",(0,0), (-1,-1),           5),
    ]
    t.setStyle(TableStyle(style))
    return t

# ── Page template ─────────────────────────────────────────────────────────────
def on_first_page(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(C_DARK)
    canvas.rect(0, 0, W, H, fill=True, stroke=False)
    canvas.restoreState()

def on_later_pages(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(C_ROW_ALT)
    canvas.rect(0, 0, W, 1.0*cm, fill=True, stroke=False)
    canvas.setFillColor(C_DIM)
    canvas.setFont("Helvetica", 7)
    canvas.drawString(1.8*cm, 0.35*cm, "iRacing Setup Machine — Technical Specification  |  Confidential")
    canvas.drawRightString(W - 1.8*cm, 0.35*cm, f"Page {doc.page}")
    canvas.restoreState()

# ── Document builder ──────────────────────────────────────────────────────────
def build():
    doc = SimpleDocTemplate(
        OUT,
        pagesize=A4,
        leftMargin=1.8*cm, rightMargin=1.8*cm,
        topMargin=1.8*cm,  bottomMargin=1.8*cm,
        title="iRacing Setup Machine — Technical Specification",
        author="iRacing Setup Machine",
        subject="Architecture & Feature Reference",
    )

    story = []

    # ═══════════════════════════════════════════════════════════════
    # COVER PAGE
    # ═══════════════════════════════════════════════════════════════
    story.append(spacer(4.5))
    story.append(Paragraph("🏎  iRacing Setup Machine", COVER_TITLE))
    story.append(spacer(0.4))
    story.append(Paragraph("High-Level Technical Specification", COVER_SUB))
    story.append(spacer(0.3))
    story.append(HRFlowable(width="60%", thickness=1.5, color=C_ACCENT, hAlign="CENTER", spaceAfter=16))
    story.append(spacer(0.3))
    story.append(Paragraph(f"Version 3.1  •  {datetime.now().strftime('%B %Y')}", COVER_META))
    story.append(Paragraph("Architecture, Feature Reference & Integration Guide", COVER_META))
    story.append(spacer(1.0))

    # Quick stats box on cover
    cover_stats = [
        [Paragraph(b("39"), TABLE_HDR),  Paragraph(b("8"),   TABLE_HDR),  Paragraph(b("18"),  TABLE_HDR),  Paragraph(b("3"),    TABLE_HDR)],
        [Paragraph("Core Modules",CAPTION), Paragraph("UI Mixins",CAPTION), Paragraph("Backend Files",CAPTION), Paragraph("Tiers",CAPTION)],
    ]
    ct = Table(cover_stats, colWidths=[3.8*cm]*4)
    ct.setStyle(TableStyle([
        ("BACKGROUND",  (0,0),(-1,0), C_ACCENT),
        ("BACKGROUND",  (0,1),(-1,1), colors.HexColor("#2c3e50")),
        ("TEXTCOLOR",   (0,1),(-1,1), C_DIM),
        ("GRID",        (0,0),(-1,-1), 0.5, C_MID),
        ("TOPPADDING",  (0,0),(-1,-1), 8),
        ("BOTTOMPADDING",(0,0),(-1,-1), 8),
        ("FONTSIZE",    (0,0),(-1,-1), 9),
    ]))
    story.append(ct)
    story.append(PageBreak())

    # ═══════════════════════════════════════════════════════════════
    # 1. EXECUTIVE OVERVIEW
    # ═══════════════════════════════════════════════════════════════
    story.append(Paragraph("1. Executive Overview", H1))
    story.append(section_rule())
    story.append(Paragraph(
        "The <b>iRacing Setup Machine</b> is a full-stack commercial platform combining a professional "
        "desktop telemetry application with a cloud SaaS backend. It is purpose-built for competitive "
        "iRacing drivers and teams who need data-driven setup advice, AI-powered coaching, and "
        "collaborative tools — all in a single integrated product.",
        BODY))
    story.append(spacer(0.2))

    story.append(Paragraph("Platform Pillars", H2))
    pillars = [
        ("Desktop App", "Python 3.12 + CustomTkinter",
         "A dark-mode, high-DPI telemetry workstation that runs entirely offline. Parses raw .ibt binary files, "
         "runs 15+ analysis engines, renders 15+ chart types, and streams AI advice — all locally."),
        ("SaaS Backend", "FastAPI + PostgreSQL + Redis",
         "A production-ready cloud API providing session storage, async job processing, Stripe billing, "
         "JWT auth with 2FA, team collaboration, leaderboards, and server-side AI calls."),
        ("AI Layer", "Anthropic Claude API (Haiku + Sonnet)",
         "Three distinct AI interaction modes: recommendations (setup-focused), Q&A chat (natural language), "
         "and the Telemetry Agent (tool-use, queries raw channels locally)."),
        ("Race Engineer Persona", "Steven (persistent profile)",
         "An AI persona that accumulates a driver profile across sessions using exponential weighted averages. "
         "Activates after 3 sessions and provides personalised, data-grounded coaching."),
    ]
    for title, tech, desc in pillars:
        row_data = [[
            Paragraph(b(title), TABLE_HDR),
            Paragraph(c(tech, "#3498db"), TABLE_CELL),
            Paragraph(desc, TABLE_CELL),
        ]]
        t = Table(row_data, colWidths=[3.5*cm, 4.0*cm, 9.0*cm])
        t.setStyle(TableStyle([
            ("BACKGROUND",  (0,0),(0,0), C_MID),
            ("BACKGROUND",  (1,0),(2,0), C_ROW_ALT),
            ("GRID",        (0,0),(-1,-1), 0.3, C_DIM),
            ("VALIGN",      (0,0),(-1,-1), "MIDDLE"),
            ("TOPPADDING",  (0,0),(-1,-1), 5),
            ("BOTTOMPADDING",(0,0),(-1,-1), 5),
            ("LEFTPADDING", (0,0),(-1,-1), 6),
        ]))
        story.append(t)
        story.append(spacer(0.1))

    # ═══════════════════════════════════════════════════════════════
    # 2. SYSTEM ARCHITECTURE
    # ═══════════════════════════════════════════════════════════════
    story.append(spacer(0.3))
    story.append(Paragraph("2. System Architecture", H1))
    story.append(section_rule())

    story.append(Paragraph("2.1  High-Level Component Diagram", H2))
    story.append(Paragraph(
        "The system is divided into three deployment targets that communicate over HTTPS/WSS:", BODY))

    arch_data = [
        [Paragraph(b("Layer"), TABLE_HDR), Paragraph(b("Technology"), TABLE_HDR),
         Paragraph(b("Deployment"), TABLE_HDR), Paragraph(b("Key Responsibilities"), TABLE_HDR)],
        [Paragraph("Desktop App", TABLE_CELL), Paragraph("Python 3.12, CustomTkinter, Matplotlib, NumPy", TABLE_CELL),
         Paragraph("User machine (Windows/macOS)", TABLE_CELL),
         Paragraph("IBT parsing, analysis, charts, AI streaming, local tool execution, OBS overlay", TABLE_CELL)],
        [Paragraph("Cloud API", TABLE_CELL), Paragraph("FastAPI, SQLAlchemy 2.0 async, Pydantic v2", TABLE_CELL),
         Paragraph("Docker (Uvicorn + Gunicorn)", TABLE_CELL),
         Paragraph("Auth, session processing, AI proxy, billing, team management, leaderboard, WebSocket", TABLE_CELL)],
        [Paragraph("Background Worker", TABLE_CELL), Paragraph("ARQ (async Redis queue), same Python env", TABLE_CELL),
         Paragraph("Docker (separate container)", TABLE_CELL),
         Paragraph("Heavy telemetry processing, PDF generation, IBT cleanup cron jobs", TABLE_CELL)],
        [Paragraph("Data Stores", TABLE_CELL), Paragraph("PostgreSQL 16, Redis 7, S3/Cloudflare R2", TABLE_CELL),
         Paragraph("Managed cloud services", TABLE_CELL),
         Paragraph("Persistent data, rate limiting, job queues, object storage (IBT, reports, PDFs)", TABLE_CELL)],
    ]
    story.append(tbl(arch_data, [2.8*cm, 4.5*cm, 4.0*cm, 5.3*cm]))

    story.append(spacer(0.3))
    story.append(Paragraph("2.2  Desktop App Class Hierarchy", H2))
    story.append(Paragraph(
        "The desktop application uses Python's multiple-inheritance mixin pattern. The <b>App</b> class "
        "inherits from specialised tab mixins, keeping each feature domain self-contained:", BODY))
    story.append(Paragraph(
        "App(IRacingTabMixin, TelemetryTabMixin, CornersTabMixin, StintTabMixin, ctk.CTk)", CODE))
    story.append(Paragraph(
        "Tab content is built <b>lazily</b> — each tab's UI is constructed only on first visit "
        "(<code>_tab_builders</code> dict + <code>_built_tabs</code> set). This keeps startup time under 1 second "
        "regardless of how many tabs exist.", BODY))

    story.append(spacer(0.3))
    story.append(Paragraph("2.3  Key Data Flows", H2))

    flows = [
        ("IBT Load & Analysis",
         "User opens .ibt → IBTParser reads binary (header + channel arrays) → "
         "AnalysisEngine produces AnalysisReport → SectorAnalyzer, CornerAnalyzer, "
         "DrivingStyleAnalyzer, ConsistencyScorer run in background thread → "
         "UI refreshes all stale tabs on completion."),
        ("AI Recommendations",
         "User clicks Get Recommendations → API key fetched from OS keyring → "
         "If Steven persona active: RaceEngineer.get_recommendations_stream() called; "
         "otherwise get_ai_recommendations_stream() used → "
         "Comprehensive prompt built (report + setup + style + sector + corner data) → "
         "Claude API streamed chunk-by-chunk into CTkTextbox."),
        ("Telemetry Agent",
         "User asks natural language question → ask_telemetry_agent() called locally → "
         "Claude tool-use loop: up to 6 rounds of list_channels / get_channel_stats / "
         "get_channel_slice / compare_laps / get_lap_times tool calls → "
         "All tool execution is local (no raw data sent to API) → streamed answer."),
        ("Cloud Session Upload",
         "cloud_sync.upload_session(ibt_path) → POST /sessions → "
         "IBT stored to S3 → TelemetrySession created (status=pending) → "
         "ARQ job enqueued → Worker downloads IBT, runs full pipeline → "
         "Report JSON uploaded to S3 → WebSocket push (status=complete) → "
         "Desktop receives notification via watch_session_status() WebSocket client."),
        ("Stripe Billing",
         "User clicks Upgrade → POST /billing/checkout → Stripe Checkout session created → "
         "User redirected to Stripe-hosted page → Payment completes → "
         "Stripe webhook POST /billing/webhook → Subscription updated in DB → "
         "license_state.tier updated on next token refresh."),
    ]
    for title, desc in flows:
        story.append(KeepTogether([
            Paragraph(b(title), H3),
            Paragraph(desc, BODY),
            spacer(0.1),
        ]))

    story.append(PageBreak())

    # ═══════════════════════════════════════════════════════════════
    # 3. CORE ANALYSIS MODULES
    # ═══════════════════════════════════════════════════════════════
    story.append(Paragraph("3. Core Analysis Modules", H1))
    story.append(section_rule())
    story.append(Paragraph(
        "All analysis logic lives in <b>files/core/</b> and is shared between the desktop app "
        "and the ARQ background worker. Modules are stateless — each returns a typed dataclass "
        "report from a pure function call.", BODY))

    modules = [
        # (Module, Key Classes/Functions, Description)
        ("ibt_parser.py", "IBTParser, TelemetryData, load_demo_data",
         "Parses iRacing .ibt binary telemetry. Reads 144-byte file header, variable "
         "metadata block, and sample data into NumPy arrays. Reconstructs lap boundaries "
         "from SessionNum + LapCompleted channels. Returns TelemetryData with "
         "_channels dict, lap_times, lap_boundaries, tick_rate, session_info."),
        ("analysis_engine.py", "AnalysisEngine, AnalysisReport, Issue, Severity",
         "Primary analysis pass. Evaluates tire temperatures/pressures, brake balance, "
         "suspension bottoming, fuel usage, RPM limiter hits, grip utilisation, and "
         "corner-phase balance. Issues classified as CRITICAL / WARNING / INFO with "
         "actionable recommendations. Configurable outlier threshold for lap filtering."),
        ("advanced_analysis.py", "SectorAnalyzer, BestLapAnalyzer, StintAnalyzer, FuelStrategyAnalyzer",
         "Sector analysis divides each lap into N equal sectors and computes per-sector "
         "times, speeds, lateral G, and tire temps. BestLapAnalyzer builds theoretical "
         "best by combining each session's fastest sector. StintAnalyzer models tire "
         "degradation rate (s/lap). FuelStrategyAnalyzer projects fuel loads for target stints."),
        ("corner_analysis.py", "CornerAnalyzer, LapDeltaAnalyzer, CornerData",
         "Identifies brake zones from brake channel edges to build a corner list. "
         "Per-corner: brake point %, apex speed, exit speed, brake pressure avg, "
         "throttle exit avg, lateral G peak, per-lap consistency. "
         "LapDeltaAnalyzer builds cumulative time delta trace (dist_pct vs delta_s) "
         "vs. a reference lap — used in PDF charts and OBS overlay."),
        ("driving_style.py", "DrivingStyleAnalyzer, DriverStyleReport",
         "Distinguishes driver technique issues from setup problems. Detects: "
         "trail-braking percentage, throttle-on point, steering reversals (nervousness), "
         "oversteer/understeer events (balance verdict), coast time %, "
         "throttle smoothness. Returns 0–100 scores per trait."),
        ("consistency_score.py", "compute_consistency, ConsistencyBreakdown",
         "Composite 0–100 consistency rating combining lap time variance (CV), "
         "sector repeatability, corner-entry speed std, and brake point std. "
         "Returns component scores, worst lap/sector/corner indices, letter grade A+–F."),
        ("session_quality.py", "IncidentDetector, TrackEvolutionAnalyzer",
         "IncidentDetector flags laps with abnormal G-spikes or LapDistPct teleports "
         "as incident laps to exclude from averages. TrackEvolutionAnalyzer separates "
         "genuine driver improvement from track rubber-in by fitting a linear regression "
         "to consecutive lap times."),
        ("brake_analysis.py", "analyze_braking, BrakeAnalysisReport",
         "Deep brake zone analysis: maximum brake pressure per zone, brake-release "
         "profile (threshold to trail-brake to release), lock detection (speed drop + "
         "wheel speed vs. ground speed divergence if available), per-zone consistency."),
        ("tire_wear_prediction.py", "predict_tire_wear, TireWearPrediction",
         "Models tire degradation using linear regression on rolling lap-time deltas. "
         "Estimates deg_rate (s/lap), cliff lap (where grip falls sharply), and "
         "per-corner deg rates from tire temperature trends."),
        ("ml_predictor.py", "LapTimePredictor, SessionFeatures",
         "NumPy Ridge Regression predictor (no external ML dependency). Trains on "
         "SessionFeatures (balance score, tire temps, fuel/lap, air/track temps) "
         "from loaded sessions. Returns PredictionResult with predicted lap time, "
         "confidence, feature importance dict, and a plain-English insight."),
        ("setup_impact.py", "predict_impact, ImpactReport, compute_sensitivity_matrix",
         "Physics-model setup change predictor. Maps parameter adjustments (wing angle, "
         "spring stiffness, ARB, brake bias, tire pressure) to expected effects on "
         "lap time delta, balance shift, and tire wear. Confidence scores indicate "
         "reliability per parameter."),
        ("setup_optimizer.py", "optimize_setup, OptimizationTarget, OptimizationResult",
         "Iterative setup optimiser that combines predict_impact with a grid-search "
         "or gradient-descent approach over adjustable parameters. Returns ranked "
         "OptimizationResult list with expected lap time gains and balance impacts."),
        ("setup_recommend.py", "find_sto_files, score_sto_matches, build_checklist",
         "Scans the user's iRacing setups folder for matching .sto files by car name "
         "similarity (SequenceMatcher ≥ 0.6). Scores and ranks candidates. Builds "
         "a ChecklistItem list with exact garage label, delta, unit, and current vs. "
         "recommended values for in-game application."),
        ("setup_parser.py", "SetupParser, ParsedSetup, SetupExporter, StoWriter, SetupDiffer",
         "Parses iRacing .htm setup exports (HTML tables) into ParsedSetup with "
         "sections and a flat key→value dict. SetupExporter writes back to .htm. "
         "StoWriter generates native iRacing .sto format (YAML-like text, placed "
         "in ~/Documents/iRacing/setups/<car>/). SetupDiffer returns changed parameters."),
        ("tech_inspector.py", "validate_setup, clamp_to_legal, get_bounds",
         "Enforces per-car-class legal parameter bounds (GT3, GT4, GTP, LMP2, Formula, "
         "Porsche Cup, TCR, etc.). validate_setup returns TechIssue list with "
         "out-of-range parameters. clamp_to_legal auto-corrects to nearest legal value."),
        ("racing_line.py", "reconstruct_racing_line, speed_colormap",
         "Reconstructs track outline and racing line from LapDistPct + lateral acceleration "
         "(or GPS if available). Returns XY coordinate arrays for track map rendering. "
         "speed_colormap generates a per-point colour array for heatmap visualisation."),
        ("gg_diagram.py", "analyze_gg_per_corner, GGReport",
         "Builds lateral vs. longitudinal G scatter plots per corner. Computes combined "
         "G utilisation (available grip fraction) and identifies under-utilised grip areas."),
        ("iracing_api.py", "IRacingAPIClient, get_client, MemberSummary, RaceResult, BestLap",
         "Full iRacing Member Data API client. Auth: base64(SHA-256(password + email.lower())). "
         "Most endpoints return {link: s3_url} — client follows redirect automatically. "
         "Converts lap times from tenths-of-milliseconds (÷10,000). Thread-safe with Lock. "
         "Returns typed dataclasses for all response types."),
        ("race_engineer.py", "RaceEngineer, DriverProfile, DriverProfileManager",
         "Persistent DriverProfile stored at ~/.iracing_engineer_profile.json. "
         "DriverProfileManager.update_from_session() applies EWA (α=0.20) to style "
         "traits, balance scores, and corner weakness records. RaceEngineer('Steven') "
         "activates after 3 sessions, injects profile context into Claude system prompt "
         "for personalised recommendations, Q&A, and evolution summaries."),
        ("telemetry_agent.py", "ask_telemetry_agent, _TOOL_SCHEMAS",
         "Claude tool-use loop with 5 local tools: list_channels, get_lap_times, "
         "get_channel_stats, get_channel_slice, compare_laps. Up to 6 agentic rounds. "
         "All data processing is local — only the question + tool results leave the machine. "
         "Streams final natural-language answer back to the caller."),
        ("live_telemetry.py", "LiveTelemetryMonitor, LiveSample",
         "Polls iRacing shared memory (irsdk) at configurable Hz (default 10 Hz). "
         "Delivers LiveSample snapshots (speed, RPM, gear, throttle, brake, fuel, "
         "tire temps/pressures, lap times) via registered callbacks. "
         "Gracefully handles missing pyirsdk package."),
        ("cloud_sync.py", "watch_session_status, submit_leaderboard, stream_ai_recommendations",
         "Desktop cloud sync client. Uses WebSocket (websocket-client) for session "
         "status watching with HTTP polling fallback. Leaderboard submission/query. "
         "SSE streaming for AI calls. Background thread uploads with progress callbacks. "
         "Token refresh with automatic retry on 401."),
        ("config.py", "get_api_key, set_api_key, get_iracing_credentials",
         "API key and iRacing credentials stored exclusively in OS credential store "
         "(keyring package). Config file never contains plaintext secrets. "
         "Auto-migrates legacy plaintext keys to keyring on first load."),
        ("license.py", "LicenseState, TIER_FEATURES, require_feature",
         "Singleton license state disk-cached for offline operation. "
         "has_feature(feature) gates all premium UI. require_feature() shows a "
         "CTkToplevel upgrade prompt with CTA when a feature is missing."),
    ]

    mod_data = [[
        Paragraph(b("Module"), TABLE_HDR),
        Paragraph(b("Key Exports"), TABLE_HDR),
        Paragraph(b("Description"), TABLE_HDR),
    ]]
    for mod, exports, desc in modules:
        mod_data.append([
            Paragraph(c(mod, "#2980b9"), TABLE_CELL),
            Paragraph(exports, BODY_SMALL),
            Paragraph(desc, TABLE_CELL),
        ])
    story.append(tbl(mod_data, [3.8*cm, 4.5*cm, 8.3*cm]))

    story.append(PageBreak())

    # ═══════════════════════════════════════════════════════════════
    # 4. USER INTERFACE
    # ═══════════════════════════════════════════════════════════════
    story.append(Paragraph("4. Desktop User Interface", H1))
    story.append(section_rule())
    story.append(Paragraph(
        "The desktop UI is built with <b>CustomTkinter</b> (dark mode, blue accent). "
        "All chart rendering uses <b>matplotlib + FigureCanvasTkAgg</b> embedded in custom "
        "<code>EmbedChart</code> frames. Tabs are lazily built on first visit to keep "
        "startup under 1 second.", BODY))

    story.append(Paragraph("4.1  Tab Inventory", H2))
    tabs = [
        ("Dashboard",     "Session KPIs, issue heat map, balance chart, tire heatmap, history sparklines, onboarding banner"),
        ("Telemetry",     "15+ chart types (Speed+Brake+Throttle, tire temps/pressures, G-G, suspension, RPM/gear, lap overlay, reference delta, racing line, sector map, brake trace)"),
        ("Issues",        "Categorised issue cards (CRITICAL / WARNING / INFO) with per-issue recommendation and fix guide"),
        ("Driver",        "Driving style scores, oversteer/understeer verdict, technique breakdown, event log"),
        ("Sectors",       "Per-sector time/speed/G comparison, theoretical best lap, sector consistency chart"),
        ("Corners",       "Per-corner metric table, brake point / apex / exit analysis, coaching notes, consistency heat map"),
        ("Stint & Tires", "Tire degradation chart, cliff detection, fuel strategy calculator, pit stop planner"),
        ("Lap Times",     "Lap time scatter, rolling average, outlier detection, lap selector with stint colouring"),
        ("Brake Trace",   "Brake pressure trace, lock detection markers, trail-braking profile, zone consistency"),
        ("Strategy",      "Multi-stint race strategy table, 0–5 stop options ranked by predicted total time"),
        ("Trends",        "Session-over-session improvement tracking, ML lap time prediction, history chart"),
        ("Impact",        "Setup change effect predictor, sensitivity matrix heat map, parameter adjustment sliders"),
        ("Setup Files",   "Setup parser, parameter table, diff viewer, tech inspector, AI setup recommendation, Export .htm / .sto"),
        ("AI Advisor",    "Streaming recommendations, Q&A chat, Steven mode badge, 📈 Evolution summary button"),
        ("Agent",         "Natural language telemetry agent tab, example prompt chips, streaming chat log"),
        ("Templates",     "Per-car-class setup templates, track-specific baseline parameters"),
        ("History",       "Cross-session lap time trends, aggregated consistency, improvement velocity"),
        ("Compare",       "Side-by-side session comparison, channel overlay for any two sessions"),
        ("iRacing",       "iRating / SR trend charts, race results table, personal bests, best lap trend chart, community leaderboard"),
    ]
    tab_data = [[Paragraph(b("Tab"), TABLE_HDR), Paragraph(b("Contents"), TABLE_HDR)]]
    for name, desc in tabs:
        tab_data.append([Paragraph(name, TABLE_CELL), Paragraph(desc, TABLE_CELL)])
    story.append(tbl(tab_data, [3.5*cm, 13.1*cm]))

    story.append(spacer(0.3))
    story.append(Paragraph("4.2  Peripheral UI Components", H2))
    periph = [
        ("OBS Overlay (obs_overlay.py)",
         "Frameless, always-on-top CTkToplevel HUD. Draggable. Shows: current lap time, Δ vs "
         "session best, speed/gear/RPM, throttle/brake fill-bars, 4-corner tyre temp grid "
         "(cold/optimal/warm/hot colour coding), live delta sparkline. Refreshes at 10 Hz "
         "from LiveTelemetryMonitor callbacks. Designed for OBS Window Capture."),
        ("Command Palette (Ctrl+K)",
         "Fuzzy-search command launcher. Scoring: exact match (10) → prefix (8) → substring (6) "
         "→ word-start (4) → difflib ratio > 0.4. Recently-used section (top 5, persisted in config). "
         "Keyboard Up/Down navigation. 20 result limit. Icons by category (📂 file, 📤 export, "
         "🤖 ai, → navigate, ⚙ general)."),
        ("Live Dashboard",
         "Full-screen live telemetry window launched by 🔴 Live button. Shows real-time "
         "speed, RPM, gear, tire temps, G-forces. Requires pyirsdk for shared memory access."),
        ("Auth Dialog (auth_dialog.py)",
         "Modal CTkToplevel for cloud account login/register. Mode switching between forms. "
         "AccountWidget header badge shows tier + sign-out. UsagePanel shows session/AI/storage "
         "progress bars with upgrade CTA."),
    ]
    for title, desc in periph:
        story.append(KeepTogether([
            Paragraph(b(title), H3),
            Paragraph(desc, BODY),
            spacer(0.1),
        ]))

    story.append(PageBreak())

    # ═══════════════════════════════════════════════════════════════
    # 5. SAAS BACKEND
    # ═══════════════════════════════════════════════════════════════
    story.append(Paragraph("5. SaaS Backend", H1))
    story.append(section_rule())

    story.append(Paragraph("5.1  API Routes", H2))
    routes = [
        ("POST /auth/register", "free", "Create account + free subscription + usage record. Returns token pair."),
        ("POST /auth/login", "free", "bcrypt verify → if TOTP enabled returns totp_token challenge; else returns access+refresh JWT pair."),
        ("POST /auth/totp/setup", "free", "Generate TOTP secret, return provisioning URI + base64 QR PNG data URL."),
        ("POST /auth/totp/enable", "free", "Verify first TOTP code, activate 2FA."),
        ("POST /auth/totp/verify", "free", "Step-2 TOTP login: verify code + totp_token → returns full token pair."),
        ("POST /auth/refresh", "free", "Rotate refresh token (old revoked, new issued). Returns new access+refresh pair."),
        ("GET /auth/me", "free", "Current user profile, tier, usage stats."),
        ("POST /sessions", "free", "Upload IBT (≤250 MB), create DB record, enqueue ARQ job. Returns session_id immediately."),
        ("GET /sessions/{id}/status", "free", "Poll processing status (pending/processing/complete/error)."),
        ("GET /sessions/{id}/report", "pro", "Full JSON analysis report (requires cloud_sync feature)."),
        ("GET /sessions/{id}/channels", "pro", "Downsampled channel data for any lap (up to 500 points)."),
        ("GET /sessions/{id}/lap/{ref}/delta/{cmp}", "pro", "LapDelta computation between two laps."),
        ("POST /sessions/{id}/export/pdf", "pro", "Enqueue PDF generation job; returns presigned download URL on completion."),
        ("POST /sessions/{id}/share", "pro", "Create share link (optional expiry). Returns token for public access."),
        ("POST /ai/recommendations", "pro", "Stream SSE setup recommendations (Claude Haiku, checks AI quota)."),
        ("POST /ai/chat", "pro", "Multi-turn chat with 20-turn history window, streamed SSE."),
        ("POST /ai/session-note", "pro", "Auto-generate 300-token session note."),
        ("POST /billing/checkout", "free", "Create Stripe Checkout session for pro/team upgrade. Returns checkout_url."),
        ("POST /billing/portal", "pro", "Create Stripe Customer Portal link for subscription management."),
        ("POST /billing/webhook", "free", "Stripe webhook: handles subscription.created/updated/deleted, invoice.payment_failed."),
        ("POST /leaderboard/submit", "free", "Opt-in submission of best lap from verified session."),
        ("GET /leaderboard/times", "free", "Top lap times for car+track combo, paginated."),
        ("GET /leaderboard/my-standing", "free", "Caller's rank and percentile for a car+track."),
        ("POST /teams", "team", "Create team (one per owner). Generates 12-char invite code."),
        ("POST /teams/{id}/members", "team", "Invite member by email. Checks seat limit."),
        ("GET /admin/audit-logs", "admin", "Paginated audit log with user/action/since filters."),
        ("GET /admin/stats", "admin", "Platform stats: users by tier, session counts, AI calls, storage."),
        ("WS /ws/sessions/{id}", "free", "WebSocket: stream session processing updates (processing/complete/error)."),
        ("WS /ws/user", "free", "WebSocket: stream all user events (session updates, quota warnings, team events)."),
    ]
    route_data = [[
        Paragraph(b("Endpoint"), TABLE_HDR),
        Paragraph(b("Min Tier"), TABLE_HDR),
        Paragraph(b("Description"), TABLE_HDR),
    ]]
    tier_colors = {"free": C_DIM, "pro": C_BLUE, "team": C_PURPLE, "admin": C_ACCENT}
    for endpoint, tier, desc in routes:
        tc = tier_colors.get(tier, C_DIM)
        route_data.append([
            Paragraph(c(endpoint, "#2980b9"), BODY_SMALL),
            Paragraph(f'<font color="{tc}"><b>{tier.upper()}</b></font>', TABLE_CELL_C),
            Paragraph(desc, TABLE_CELL),
        ])
    story.append(tbl(route_data, [5.8*cm, 1.6*cm, 9.2*cm]))

    story.append(spacer(0.3))
    story.append(Paragraph("5.2  Database Schema", H2))
    story.append(Paragraph(
        "PostgreSQL 16 via async SQLAlchemy 2.0. All tables use UUID primary keys. "
        "JSONB columns for flexible metadata (session_info, audit metadata, setup params).", BODY))

    db_data = [[
        Paragraph(b("Table"), TABLE_HDR),
        Paragraph(b("Key Columns"), TABLE_HDR),
        Paragraph(b("Notes"), TABLE_HDR),
    ]]
    tables_info = [
        ("users", "id, email, hashed_password, totp_secret, totp_enabled, is_admin, discord_id, google_id",
         "OAuth-ready. 2FA via TOTP (pyotp). Email verification + password reset tokens."),
        ("subscriptions", "user_id (unique), stripe_customer_id, stripe_subscription_id, tier, status, trial_end",
         "One per user. tier: free|pro|team. status: active|trialing|past_due|cancelled|unpaid."),
        ("teams", "id, name, owner_id, seats_purchased, invite_code",
         "One team per owner. Members join via 12-char invite code. Coach/member roles."),
        ("team_members", "team_id, user_id, role",
         "Unique (team_id, user_id). role: owner|coach|member."),
        ("telemetry_sessions", "user_id, storage_key, report_key, car_name, track_name, best_lap_s, status, job_id",
         "status: pending→processing→complete→error. Dual S3 keys: raw IBT + processed JSON report."),
        ("setup_files", "user_id, storage_key, car_name, parsed_params (JSONB)",
         "parsed_params caches the flat key→value map to avoid re-parsing on diff requests."),
        ("share_links", "resource_type, resource_id, token, expires_at, views",
         "resource_type: session|setup. Public access via /shared/{token}. Hit counter."),
        ("usage_records", "ai_calls_today, ai_calls_date, sessions_this_month, storage_bytes",
         "One per user. Monthly session counter reset. Daily AI counter reset. Cumulative totals."),
        ("api_keys", "user_id, key_prefix (8 chars), key_hash (SHA-256), expires_at",
         "Full key shown once at creation. team tier only. Prefix for UI display."),
        ("refresh_tokens", "user_id, token_hash, device_hint, expires_at, revoked",
         "Rotation: old revoked when new issued. 30-day expiry."),
        ("audit_logs", "user_id, action, resource_type, resource_id, ip_address, metadata (JSONB)",
         "Immutable. Indexed on (user_id, created_at) and action. Never deleted."),
        ("leaderboard_entries", "user_id, car_name, track_name, lap_time_s, display_name, is_verified",
         "Opt-in. Unique per (user, car, track) — only kept if new time is faster."),
    ]
    for tname, cols, notes in tables_info:
        db_data.append([
            Paragraph(c(tname, "#2980b9"), TABLE_CELL),
            Paragraph(cols, BODY_SMALL),
            Paragraph(notes, TABLE_CELL),
        ])
    story.append(tbl(db_data, [3.2*cm, 7.0*cm, 6.4*cm]))

    story.append(spacer(0.3))
    story.append(Paragraph("5.3  Background Job Worker", H2))
    story.append(Paragraph(
        "ARQ (async Redis queue) powers background processing. Worker runs as a separate "
        "Docker container sharing the same Python environment and files/ directory.", BODY))
    jobs_data = [[Paragraph(b("Job"), TABLE_HDR), Paragraph(b("Trigger"), TABLE_HDR), Paragraph(b("Steps"), TABLE_HDR)]]
    jobs_info = [
        ("process_telemetry_session", "POST /sessions upload",
         "Download IBT → IBTParser → AnalysisEngine → Sector/Corner/Style/Consistency analyzers "
         "→ serialize to JSON → upload to S3 (report_key) → update DB status → WebSocket push."),
        ("generate_pdf_report_job", "POST /sessions/{id}/export/pdf",
         "Download report JSON → reconstruct minimal TelemetryData → generate_pdf_report() "
         "(ReportLab with track map + lap delta charts) → upload PDF to S3 → return presigned URL."),
        ("cleanup_expired_ibt", "Cron (daily)",
         "Delete raw .ibt files from S3 older than ibt_expiry_days setting. "
         "Preserves processed JSON reports. Logs bytes freed."),
    ]
    for jname, trigger, steps in jobs_info:
        jobs_data.append([
            Paragraph(c(jname, "#2980b9"), TABLE_CELL),
            Paragraph(trigger, BODY_SMALL),
            Paragraph(steps, TABLE_CELL),
        ])
    story.append(tbl(jobs_data, [4.5*cm, 3.2*cm, 8.9*cm]))

    story.append(PageBreak())

    # ═══════════════════════════════════════════════════════════════
    # 6. FEATURE / TIER MATRIX
    # ═══════════════════════════════════════════════════════════════
    story.append(Paragraph("6. Feature & Tier Matrix", H1))
    story.append(section_rule())

    CHECK = "\u2713"
    CROSS = "\u2014"
    features_matrix = [
        [Paragraph(b("Feature"), TABLE_HDR),
         Paragraph(b("Free"), TABLE_HDR),
         Paragraph(b("Pro"), TABLE_HDR),
         Paragraph(b("Team"), TABLE_HDR)],
        ["IBT Telemetry Analysis",  CHECK, CHECK, CHECK],
        ["Basic Chart Types (Speed/Brake/Throttle)", CHECK, CHECK, CHECK],
        ["Issue Detection & Recommendations", CHECK, CHECK, CHECK],
        ["Track Map Visualisation", CHECK, CHECK, CHECK],
        ["Lap Delta Comparison", CHECK, CHECK, CHECK],
        ["iRacing Account Integration", CHECK, CHECK, CHECK],
        ["Community Leaderboard", CHECK, CHECK, CHECK],
        ["2FA / TOTP", CHECK, CHECK, CHECK],
        ["Advanced Telemetry Charts (15+ types)", CROSS, CHECK, CHECK],
        ["Sector & Corner Analysis", CROSS, CHECK, CHECK],
        ["Driving Style Analysis", CROSS, CHECK, CHECK],
        ["Consistency Scoring", CROSS, CHECK, CHECK],
        ["Tire Wear & Degradation", CROSS, CHECK, CHECK],
        ["Stint & Race Strategy", CROSS, CHECK, CHECK],
        ["ML Lap Time Predictor", CROSS, CHECK, CHECK],
        ["Setup Optimiser & Impact Predictor", CROSS, CHECK, CHECK],
        ["PDF Export", CROSS, CHECK, CHECK],
        ["CSV / MoTeC Export", CROSS, CHECK, CHECK],
        ["AI Setup Recommendations (200/day)", CROSS, CHECK, CHECK],
        ["AI Q&A Chat", CROSS, CHECK, CHECK],
        ["Telemetry Agent (natural language)", CROSS, CHECK, CHECK],
        ["Steven Persona (after 3 sessions)", CROSS, CHECK, CHECK],
        ["Evolution AI Summary", CROSS, CHECK, CHECK],
        ["OBS Overlay HUD", CROSS, CHECK, CHECK],
        ["Cloud Sync (upload + report storage)", CROSS, CHECK, CHECK],
        ["Sessions / month", "10", "Unlimited", "Unlimited"],
        ["AI calls / day", "5", "200", "500"],
        ["Cloud Storage", "512 MB", "50 GB", "200 GB"],
        ["Team Management & Shared Library", CROSS, CROSS, CHECK],
        ["Coach View (team sessions)", CROSS, CROSS, CHECK],
        ["Setup Sharing (team tier)", CROSS, CROSS, CHECK],
        ["API Key Access", CROSS, CROSS, CHECK],
        ["AI calls / day (team)", "\u2014", "\u2014", "500"],
    ]
    fm_table_data = []
    for row in features_matrix:
        if isinstance(row[0], str):
            styled = [Paragraph(row[0], TABLE_CELL)]
            for cell in row[1:]:
                if cell == CHECK:
                    styled.append(Paragraph(f'<font color="#27ae60"><b>{cell}</b></font>', TABLE_CELL_C))
                elif cell == CROSS:
                    styled.append(Paragraph(f'<font color="#bdc3c7">{cell}</font>', TABLE_CELL_C))
                else:
                    styled.append(Paragraph(str(cell), TABLE_CELL_C))
            fm_table_data.append(styled)
        else:
            fm_table_data.append(row)
    story.append(tbl(fm_table_data, [9.6*cm, 2.0*cm, 2.0*cm, 2.0*cm]))

    story.append(PageBreak())

    # ═══════════════════════════════════════════════════════════════
    # 7. SECURITY
    # ═══════════════════════════════════════════════════════════════
    story.append(Paragraph("7. Security Architecture", H1))
    story.append(section_rule())

    sec_items = [
        ("Password Storage", "bcrypt (passlib) with work factor 12. Never stored plaintext."),
        ("API Keys (backend)", "Full key shown once. Only SHA-256 hash stored in DB. Prefix (8 chars) for UI display."),
        ("JWT Tokens", "HS256-signed access tokens (15-min TTL) + refresh tokens (30-day, rotated on use, revoked on logout). "
                       "Type claim (access/refresh/totp_pending) prevents token misuse."),
        ("2FA / TOTP", "pyotp TOTP (RFC 6238). Setup flow: /totp/setup → QR scan → /totp/enable (first code verify). "
                       "Login step-2 via short-lived totp_pending JWT (5-min TTL). valid_window=1 allows ±30s clock skew."),
        ("Desktop Credentials", "Anthropic API key + iRacing credentials stored exclusively in OS keyring (Windows Credential Manager / macOS Keychain). "
                                "Config file (~/.iracing_setup_advisor.json) never contains secrets."),
        ("Rate Limiting", "Redis sorted-set sliding window per user. Different limits per tier (free: tighter, team: relaxed). "
                          "AI quota checked before stream, incremented after."),
        ("Audit Logging", "Immutable AuditLog table records: login success/failure, TOTP events, session uploads/deletes, "
                          "billing events, admin actions, leaderboard submissions. Never deleted. IP + User-Agent captured."),
        ("Object Storage Access", "All S3/R2 objects use presigned URLs (GET: 1-hour TTL, PUT: 15-min TTL). "
                                  "No public bucket. Keys namespaced by user_id. GDPR erasure via delete_user_objects()."),
        ("CORS", "Strict allowlist of origins in Settings.allowed_origins. Credentials=True for cookie-based flows."),
        ("Stripe Webhooks", "Webhook signature validated with stripe.Webhook.construct_event(). "
                            "Subscription status only updated via webhook, never client-side."),
    ]
    sec_data = [[Paragraph(b("Control"), TABLE_HDR), Paragraph(b("Implementation"), TABLE_HDR)]]
    for ctrl, impl in sec_items:
        sec_data.append([Paragraph(ctrl, TABLE_CELL), Paragraph(impl, TABLE_CELL)])
    story.append(tbl(sec_data, [4.2*cm, 12.4*cm]))

    story.append(PageBreak())

    # ═══════════════════════════════════════════════════════════════
    # 8. EXTERNAL INTEGRATIONS
    # ═══════════════════════════════════════════════════════════════
    story.append(Paragraph("8. External Integrations", H1))
    story.append(section_rule())

    integrations = [
        ("Anthropic Claude API", "claude-haiku-4-5-20251001 (default), claude-sonnet-4-6 (premium)",
         "Three usage patterns: (1) Standard streaming via get_ai_recommendations_stream — builds "
         "comprehensive prompt from AnalysisReport + setup + style + sector data; "
         "(2) Steven persona — injects DriverProfile context into system prompt; "
         "(3) Telemetry Agent — tool-use loop, up to 6 rounds, tools executed locally.",
         "ANTHROPIC_API_KEY (desktop: keyring; server: env var)"),
        ("iRacing Member Data API", "https://members-ng.iracing.com",
         "Cookie-based auth (POST /auth with base64(SHA-256(password + email.lower()))). "
         "Most endpoints return {link: s3_url} — client follows S3 redirect. "
         "Lap times in tenths-of-milliseconds (÷10,000 for seconds). "
         "Rate limit: 240 req/min enforced by 250ms inter-request gap.",
         "User email + password (OS keyring)"),
        ("Stripe", "stripe-python 11.x",
         "Checkout sessions for pro_monthly/pro_annual/team_monthly/team_annual plans. "
         "7-day free trial on pro. Customer Portal for self-serve billing management. "
         "Webhook events: customer.subscription.created/updated/deleted, invoice.payment_failed.",
         "STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, STRIPE_PRICE_* (env vars)"),
        ("AWS S3 / Cloudflare R2", "boto3 1.35+",
         "Optional custom endpoint_url for R2 compatibility. "
         "Key namespacing: ibt/{user_id}/{session_id}.ibt, reports/{user_id}/{session_id}.json, "
         "setups/{user_id}/{setup_id}.sto, exports/{user_id}/{session_id}.pdf. "
         "Presigned upload (PUT, 15-min) and download (GET, 1-hour) URLs.",
         "AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, S3_BUCKET, S3_ENDPOINT_URL (env vars)"),
        ("Redis", "redis[hiredis] 5.x + ARQ 0.26",
         "Rate limiting (sorted-set sliding window), ARQ job queue (iracing_advisor queue), "
         "WebSocket manager not using Redis (in-process), session caching.",
         "REDIS_URL (env var)"),
        ("PostgreSQL", "SQLAlchemy 2.0 async + asyncpg",
         "pool_size=10, pool_pre_ping=True. All models use UUID PKs. "
         "JSONB for flexible metadata (audit, setup params). "
         "Alembic for schema migrations.",
         "DATABASE_URL (env var)"),
    ]
    int_data = [[
        Paragraph(b("Service"), TABLE_HDR),
        Paragraph(b("Library/Version"), TABLE_HDR),
        Paragraph(b("Usage"), TABLE_HDR),
        Paragraph(b("Credentials"), TABLE_HDR),
    ]]
    for svc, lib, usage, creds in integrations:
        int_data.append([
            Paragraph(b(svc), TABLE_CELL),
            Paragraph(lib, BODY_SMALL),
            Paragraph(usage, TABLE_CELL),
            Paragraph(creds, BODY_SMALL),
        ])
    story.append(tbl(int_data, [2.8*cm, 2.8*cm, 8.0*cm, 3.0*cm]))

    story.append(PageBreak())

    # ═══════════════════════════════════════════════════════════════
    # 9. FILE FORMATS & PERSISTENCE
    # ═══════════════════════════════════════════════════════════════
    story.append(Paragraph("9. File Formats & Persistence", H1))
    story.append(section_rule())

    story.append(Paragraph("9.1  File Formats", H2))
    fmt_data = [[
        Paragraph(b("Format"), TABLE_HDR),
        Paragraph(b("Origin"), TABLE_HDR),
        Paragraph(b("Parser/Writer"), TABLE_HDR),
        Paragraph(b("Notes"), TABLE_HDR),
    ]]
    formats = [
        (".ibt", "iRacing simulator", "IBTParser (core/ibt_parser.py)",
         "Binary. 144-byte header + variable metadata + 60 Hz sample records. "
         "Channels as parallel NumPy arrays. Up to 500 MB."),
        (".htm / .html", "iRacing garage export", "SetupParser / SetupExporter (core/setup_parser.py)",
         "HTML tables. Parsed into SetupSection list + flat dict. "
         "Written back with same structure for garage import."),
        (".sto", "iRacing garage (native)", "StoWriter (core/setup_parser.py)",
         "YAML-like text: CarCode, TrackName, SetupName header + named sections. "
         "Default path: ~/Documents/iRacing/setups/<car>/<name>.sto."),
        (".json (reports)", "Analysis pipeline output", "json.dumps / jobs.py",
         "Serialised AnalysisReport + all sub-reports. Stored in S3 under reports/ key. "
         "NumPy arrays converted via _safe() helper (tolist/item)."),
        (".json (profile)", "race_engineer.py", "DriverProfileManager.save/load",
         "Atomic write via os.replace. Path: ~/.iracing_engineer_profile.json. "
         "Stores DriverProfile dataclass (asdict). Reconstructs nested WeaknessRecord etc."),
        (".json (config)", "Desktop app", "core/config.py (load_cfg/save_cfg)",
         "Path: ~/.iracing_setup_advisor.json. Never contains secrets. "
         "Stores: last_dir, geometry, theme, units, palette_recent, onboarding_dismissed."),
        (".pdf (reports)", "PDF export pipeline", "core/pdf_report.py (ReportLab)",
         "Generated by generate_pdf_report(). Embeds track map (LineCollection heatmap) "
         "and lap delta chart (fill_between) as RLImage floatables."),
        (".csv", "MoTeC / external export", "core/motec_export.py",
         "Channel data export in MoTeC i2 compatible format. Optional."),
    ]
    for fmt, origin, parser, notes in formats:
        fmt_data.append([
            Paragraph(c(fmt, "#2980b9"), TABLE_CELL),
            Paragraph(origin, BODY_SMALL),
            Paragraph(parser, BODY_SMALL),
            Paragraph(notes, TABLE_CELL),
        ])
    story.append(tbl(fmt_data, [1.8*cm, 2.8*cm, 4.2*cm, 7.8*cm]))

    story.append(spacer(0.3))
    story.append(Paragraph("9.2  Local Persistence (Desktop)", H2))
    local_data = [[Paragraph(b("Store"), TABLE_HDR), Paragraph(b("Contents"), TABLE_HDR), Paragraph(b("Location"), TABLE_HDR)]]
    local_stores = [
        ("OS Keyring", "Anthropic API key, iRacing email + password, cloud access/refresh tokens", "Windows Credential Manager / macOS Keychain"),
        ("Config JSON", "UI preferences, last directory, geometry, command palette recents, consent flags", "~/.iracing_setup_advisor.json"),
        ("Driver Profile JSON", "DriverProfile: style EWAs, session history, weakness records, car class prefs", "~/.iracing_engineer_profile.json"),
        ("License Cache JSON", "Tier, features, last-verified timestamp (offline fallback)", "~/.iracing_setup_advisor_license.json"),
        ("App Logs", "Rotating file handler 5 MB × 3 backups. Crash reports with traceback.", "~/.iracing_setup_advisor_logs/app.log"),
        ("IBT Cache", "Parsed TelemetryData cached to avoid re-parsing. LRU eviction at 20 entries.", "In-memory (evicted on app restart)"),
    ]
    for store, contents, loc in local_stores:
        local_data.append([Paragraph(store, TABLE_CELL), Paragraph(contents, TABLE_CELL), Paragraph(c(loc, "#7f8c8d"), BODY_SMALL)])
    story.append(tbl(local_data, [3.0*cm, 8.5*cm, 5.1*cm]))

    story.append(PageBreak())

    # ═══════════════════════════════════════════════════════════════
    # 10. DEPLOYMENT
    # ═══════════════════════════════════════════════════════════════
    story.append(Paragraph("10. Deployment & Infrastructure", H1))
    story.append(section_rule())

    story.append(Paragraph("10.1  Docker Compose (docker-compose.yml)", H2))
    compose_services = [
        ("postgres", "postgres:16", "5432", "Primary data store. Persistent volume."),
        ("redis", "redis:7-alpine", "6379", "Job queue + rate limiting. Persistent volume (AOF)."),
        ("api", "Dockerfile (python:3.12-slim)", "8000", "FastAPI + Uvicorn. 4 workers in prod. Mounts files/ for shared analysis pipeline."),
        ("worker", "Same Dockerfile", "—", "ARQ worker. Same image, different CMD: arq backend.jobs.WorkerSettings. max_jobs=4, job_timeout=300s."),
        ("minio", "minio/minio (local dev only)", "9000/9001", "Local S3-compatible object storage for development. Not deployed in production."),
    ]
    dep_data = [[Paragraph(b("Service"), TABLE_HDR), Paragraph(b("Image"), TABLE_HDR),
                 Paragraph(b("Port"), TABLE_HDR), Paragraph(b("Notes"), TABLE_HDR)]]
    for svc, img, port, notes in compose_services:
        dep_data.append([Paragraph(svc, TABLE_CELL), Paragraph(img, BODY_SMALL),
                         Paragraph(port, TABLE_CELL_C), Paragraph(notes, TABLE_CELL)])
    story.append(tbl(dep_data, [2.0*cm, 4.5*cm, 2.0*cm, 8.1*cm]))

    story.append(spacer(0.3))
    story.append(Paragraph("10.2  Environment Variables (.env.example)", H2))
    env_vars = [
        ("SECRET_KEY", "JWT signing key (min 32 chars random)"),
        ("DATABASE_URL", "postgresql+asyncpg://user:pass@host:5432/dbname"),
        ("REDIS_URL", "redis://localhost:6379/0"),
        ("ANTHROPIC_API_KEY", "Server-side Claude API key for cloud AI routes"),
        ("STRIPE_SECRET_KEY", "Stripe API key (sk_live_...)"),
        ("STRIPE_WEBHOOK_SECRET", "Stripe webhook signing secret (whsec_...)"),
        ("STRIPE_PRICE_PRO_MONTHLY / ANNUAL", "Stripe Price IDs for pro plan"),
        ("STRIPE_PRICE_TEAM_MONTHLY / ANNUAL", "Stripe Price IDs for team plan"),
        ("AWS_ACCESS_KEY_ID / SECRET_ACCESS_KEY", "S3 or Cloudflare R2 credentials"),
        ("S3_BUCKET", "Bucket name for all object storage"),
        ("S3_ENDPOINT_URL", "Optional: Cloudflare R2 endpoint URL"),
        ("FRONTEND_URL", "Base URL for email links (e.g. https://app.iracing-advisor.com)"),
        ("ALLOWED_ORIGINS", "CORS whitelist (comma-separated)"),
        ("DEBUG", "true|false — enables /docs, /redoc, verbose logging"),
        ("ENVIRONMENT", "development|staging|production"),
    ]
    env_data = [[Paragraph(b("Variable"), TABLE_HDR), Paragraph(b("Purpose"), TABLE_HDR)]]
    for var, purpose in env_vars:
        env_data.append([Paragraph(c(var, "#2980b9"), BODY_SMALL), Paragraph(purpose, TABLE_CELL)])
    story.append(tbl(env_data, [6.5*cm, 10.1*cm]))

    story.append(spacer(0.3))
    story.append(Paragraph("10.3  Desktop App Distribution", H2))
    dist_items = [
        "Entry point: <b>files/main.py</b> (App().mainloop()). Packaged with PyInstaller into a single-folder bundle.",
        "Requires Python 3.10+. Optional dependencies: pyirsdk (live telemetry), tkinterdnd2 (drag & drop), websocket-client (cloud sync).",
        "App icon: files/app.ico. Version/copyright: files/version.py.",
        "All core analysis modules are pure Python + NumPy — no C extensions beyond NumPy/Matplotlib.",
        "Geometry (window size/position) and last-active tab are saved to config on close and restored on launch.",
    ]
    for item in dist_items:
        story.append(bullet(item))

    story.append(PageBreak())

    # ═══════════════════════════════════════════════════════════════
    # 11. KEY ALGORITHMS
    # ═══════════════════════════════════════════════════════════════
    story.append(Paragraph("11. Key Algorithms & Design Decisions", H1))
    story.append(section_rule())

    algos = [
        ("EWA Driver Profile Updates",
         "All style traits and balance metrics use Exponential Weighted Average (α=0.20): "
         "new_value = α×new + (1−α)×old. When old == 0.0 (first session), returns new directly "
         "to avoid initial zero-bias. Weakness severity uses α=0.30 (faster response). "
         "Corner type classification: <30 km/h = hairpin, <55 = slow, <85 = medium, ≥85 = fast."),
        ("Fuzzy Command Palette Scoring",
         "Score hierarchy (highest wins): exact match (10.0) → prefix match (8.0) → "
         "substring (6.0) → any word starts with query (4.0) → "
         "difflib SequenceMatcher ratio > 0.4 (ratio value, else 0.0). "
         "Top 20 results shown. Recently-used list (8 items) stored in config."),
        ("iRacing API Auth",
         "Password hash = base64(SHA-256(password + email.lower())). "
         "Posted to /auth endpoint → returns authtoken_members cookie. "
         "Subsequent requests carry cookie. Most endpoints return {link: S3_URL} "
         "and client follows S3 redirect automatically."),
        ("Lap Delta Computation",
         "LapDeltaAnalyzer resamples both laps to a common LapDistPct grid (0.0–1.0, "
         "1000 points). Computes per-position time delta via cumulative time integral "
         "over speed channel. Returns dist_pct[] + delta_s[] arrays used in both "
         "PDF charts and OBS overlay live interpolation."),
        ("IBT Lap Boundary Detection",
         "Lap boundaries are detected from SessionNum and LapCompleted channels. "
         "A new lap starts when LapCompleted increments. Sample indices (start, end) "
         "are stored in lap_boundaries[], enabling O(1) slicing of any channel for any lap."),
        ("Sector Analysis",
         "Track divided into N equal LapDistPct segments. For each segment, "
         "per-lap crossing times are computed via linear interpolation at the boundary "
         "sample. Sector consistency = 1 − CV (coefficient of variation). "
         "Theoretical best = sum of each sector's minimum time across all laps."),
        ("ML Lap Time Prediction",
         "NumPy Ridge Regression (no sklearn dependency). Features: 8-element vector "
         "(balance score, front/rear avg tire temps, air/track temp, fuel/lap, "
         "avg grip utilisation, lap count). Trained on all loaded sessions. "
         "Confidence = 1 − (residual_std / mean_lap_time), clamped to [0, 1]."),
        ("Telemetry Agent Tool-Use",
         "Claude is given 5 tool declarations. In each round, the model returns "
         "text and/or tool_use blocks. Tool results are fed back as user messages. "
         "Loop continues for up to MAX_TOOL_ROUNDS=6 iterations or until stop_reason=end_turn. "
         "All tool execution is local — only question text + JSON results cross the API boundary."),
    ]
    for title, desc in algos:
        story.append(KeepTogether([
            Paragraph(b(title), H3),
            Paragraph(desc, BODY),
            spacer(0.15),
        ]))

    # ═══════════════════════════════════════════════════════════════
    # 12. DEPENDENCY SUMMARY
    # ═══════════════════════════════════════════════════════════════
    story.append(spacer(0.2))
    story.append(Paragraph("12. Dependency Summary", H1))
    story.append(section_rule())

    story.append(Paragraph("12.1  Desktop App (requirements.txt)", H2))
    desktop_deps = [
        ("customtkinter", "≥ 5.2", "Dark-mode GUI framework"),
        ("matplotlib", "3.9.3", "All charts and visualisations"),
        ("numpy", "1.26.4", "Numerical computation throughout analysis pipeline"),
        ("reportlab", "4.2.5", "PDF report generation"),
        ("scipy", "1.14.1", "Signal processing (optional, fallback if missing)"),
        ("anthropic", "0.40.0", "Claude API client (streaming)"),
        ("keyring", "latest", "OS credential store (Windows/macOS/Linux)"),
        ("requests", "2.32.3", "iRacing API + cloud sync HTTP calls"),
        ("websocket-client", "1.8.0", "WebSocket session status watcher (cloud sync)"),
        ("tkinterdnd2", "optional", "Drag-and-drop .ibt / .htm file support"),
        ("pyirsdk", "optional", "iRacing shared memory for live telemetry"),
    ]
    dd_data = [[Paragraph(b("Package"), TABLE_HDR), Paragraph(b("Version"), TABLE_HDR), Paragraph(b("Purpose"), TABLE_HDR)]]
    for pkg, ver, purpose in desktop_deps:
        dd_data.append([Paragraph(c(pkg,"#2980b9"), TABLE_CELL), Paragraph(ver, TABLE_CELL_C), Paragraph(purpose, TABLE_CELL)])
    story.append(tbl(dd_data, [4.0*cm, 2.2*cm, 10.4*cm]))

    story.append(spacer(0.2))
    story.append(Paragraph("12.2  Backend (requirements-backend.txt)", H2))
    backend_deps = [
        ("fastapi", "0.115.5", "Async web framework + OpenAPI"),
        ("uvicorn[standard]", "0.32.1", "ASGI server (+ websockets extra)"),
        ("gunicorn", "23.0.0", "Process manager for production"),
        ("sqlalchemy[asyncio]", "2.0.36", "Async ORM"),
        ("asyncpg", "0.30.0", "Async PostgreSQL driver"),
        ("alembic", "1.14.0", "Database migrations"),
        ("python-jose[cryptography]", "3.3.0", "JWT encode/decode"),
        ("passlib[bcrypt]", "1.7.4", "Password hashing"),
        ("pydantic[email]", "2.10.3", "Request/response validation"),
        ("pydantic-settings", "2.6.1", "Environment variable settings"),
        ("redis[hiredis]", "5.2.1", "Redis client + hiredis parser"),
        ("arq", "0.26.1", "Async Redis job queue"),
        ("boto3", "1.35.84", "S3 / Cloudflare R2 object storage"),
        ("stripe", "11.3.0", "Stripe payments + webhooks"),
        ("anthropic", "0.40.0", "Claude API (server-side)"),
        ("pyotp", "2.9.0", "TOTP 2FA generation/verification"),
        ("qrcode[pil]", "8.0", "QR code PNG generation for TOTP setup"),
        ("websocket-client", "1.8.0", "Desktop WS status client"),
    ]
    bd_data = [[Paragraph(b("Package"), TABLE_HDR), Paragraph(b("Version"), TABLE_HDR), Paragraph(b("Purpose"), TABLE_HDR)]]
    for pkg, ver, purpose in backend_deps:
        bd_data.append([Paragraph(c(pkg,"#2980b9"), TABLE_CELL), Paragraph(ver, TABLE_CELL_C), Paragraph(purpose, TABLE_CELL)])
    story.append(tbl(bd_data, [4.0*cm, 2.2*cm, 10.4*cm]))

    story.append(PageBreak())

    # ═══════════════════════════════════════════════════════════════
    # 13. ROADMAP (remaining from approved list)
    # ═══════════════════════════════════════════════════════════════
    story.append(Paragraph("13. Current Build Status & Roadmap", H1))
    story.append(section_rule())

    story.append(Paragraph("13.1  Completed Features", H2))
    completed = [
        "IBT parser, analysis engine, 15+ chart types, sector/corner/style/consistency analysis",
        "Setup parser (.htm/.sto), tech inspector, setup impact predictor, optimizer",
        "AI Setup Recommendations + Q&A chat (streaming SSE, Claude Haiku)",
        "Race Engineer 'Steven' persona (persistent EWA driver profile, 3-session unlock)",
        "Natural Language Telemetry Agent (Claude tool-use, all execution local)",
        "Session Evolution AI Summary (per car+track historical comparison)",
        "iRacing Data API integration (iRating, SR, results, best laps, correlation)",
        "iRacing tab: stats, trend charts, results table, personal bests, best lap trend chart",
        "Community Leaderboard (opt-in, verified, per car+track, rank/percentile)",
        "OBS Overlay HUD (frameless, always-on-top, live delta sparkline, tyre temps)",
        "PDF Report generation (ReportLab, embedded track map + lap delta charts)",
        "Full SaaS Backend: FastAPI, PostgreSQL, Redis, ARQ, S3/R2, Stripe, JWT",
        "2FA / TOTP: setup flow, QR code, step-2 login, enable/disable",
        "Audit Log: immutable events table, admin query endpoint",
        "WebSocket job status: session processing updates, user-wide event stream",
        "Command Palette: fuzzy scoring, recently used, keyboard navigation",
        ".sto setup file writer (native iRacing format, auto-paths to setups folder)",
        "File watcher (auto-load new .ibt), drag-and-drop, batch load",
        "ML lap time predictor, race strategy calculator, stint planner",
        "First-run onboarding banner, OS keyring credential storage",
        "Docker Compose deployment (API + Worker + Postgres + Redis + MinIO)",
    ]
    for item in completed:
        story.append(bullet(f'<font color="#27ae60">\u2713</font>  {item}'))
    story.append(spacer(0.2))

    story.append(Paragraph("13.2  Potential Future Enhancements", H2))
    future = [
        "Discord / Google OAuth login integration",
        "Mobile companion app (React Native PWA)",
        "Natural language setup search ('softer rear for Monza')",
        "WebRTC peer-to-peer screen share for coach sessions",
        "Automated iRacing series calendar integration (upcoming events, base setups)",
        "Voice coaching mode (text-to-speech Steven debrief post-session)",
        "Setup version history with git-like diff and rollback",
        "Public API for third-party integrations (Discord bot, stream overlays)",
        "GDPR data export / erasure endpoints",
        "Multi-language localisation (French, German, Spanish)",
    ]
    for item in future:
        story.append(bullet(f'○  {item}'))

    # ═══════════════════════════════════════════════════════════════
    # FOOTER
    # ═══════════════════════════════════════════════════════════════
    story.append(spacer(0.5))
    story.append(hr())
    story.append(Paragraph(
        f"iRacing Setup Machine  •  Technical Specification v3.1  •  {datetime.now().strftime('%B %Y')}  •  Confidential",
        CAPTION))

    # ── Build ─────────────────────────────────────────────────────────────────
    doc.build(story,
              onFirstPage=on_first_page,
              onLaterPages=on_later_pages)
    print(f"PDF written to: {OUT}")
    return OUT

if __name__ == "__main__":
    build()
