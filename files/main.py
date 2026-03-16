"""
iRacing Setup Advisor — Professional Desktop Telemetry Tool
Integrates: telemetry, setup parsing, sector analysis, driving style,
tire pressure model, fuel correction, stint analysis, history, AI, PDF export.
"""

import sys
if sys.version_info < (3, 10):
    sys.exit("iRacing Setup Advisor requires Python 3.10 or later.")

import customtkinter as ctk
from tkinter import filedialog, messagebox
import threading, os, json, logging, logging.handlers, csv, traceback, time, re
from datetime import datetime
import numpy as np
from version import VERSION, APP_NAME, COPYRIGHT
import matplotlib
matplotlib.use('TkAgg')
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt
import matplotlib.patches

# Drag-and-drop support (optional)
try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    _HAS_DND = True
except ImportError:
    _HAS_DND = False

# ── Logging (file + console) ──────────────────────────────────────────────
_LOG_DIR = os.path.expanduser("~/.iracing_setup_advisor_logs")
os.makedirs(_LOG_DIR, exist_ok=True)
_LOG_FILE = os.path.join(_LOG_DIR, "app.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.handlers.RotatingFileHandler(
            _LOG_FILE, maxBytes=5*1024*1024, backupCount=3, encoding='utf-8'),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.ibt_parser          import IBTParser, load_demo_data, TelemetryData
from core.analysis_engine     import (AnalysisEngine, AnalysisReport, Severity, format_laptime,
                                       DOWNSAMPLE_CHART, DOWNSAMPLE_LAP)
from core.advanced_analysis   import (SectorAnalyzer, SectorAnalysisReport,
                                       BestLapAnalyzer, BestLapReport,
                                       StintAnalyzer, TireDegReport,
                                       HistoryTracker,
                                       FuelStrategyAnalyzer, FuelStrategyReport)
from core.driving_style       import DrivingStyleAnalyzer, DriverStyleReport
from core.corner_analysis     import CornerAnalyzer, CornerAnalysisReport, LapDeltaAnalyzer
from core.consistency_score   import compute_consistency, ConsistencyBreakdown
from core.tire_wear_prediction import predict_tire_wear, TireWearPrediction
from core.track_zones         import classify_zones
from core.setup_parser        import (SetupParser, SetupExporter, SetupDiffer, ParsedSetup,
                                       create_demo_setup, parsed_setup_from_ibt)
from core.ai_advisor          import (get_ai_recommendations_sync, get_ai_recommendations_stream,
                                       ask_setup_question_stream, generate_session_note_stream)
from core.live_telemetry      import LiveTelemetryMonitor, LiveSample
from core.reference_lap       import compute_reference_delta
from data.templates.track_templates import get_setup_template, get_track_info, list_tracks
from core.lap_overlay         import extract_lap_trace, compare_laps
from core.brake_analysis      import analyze_braking, BrakeAnalysisReport
from core.session_aggregator  import aggregate_sessions, AggregationReport
from core.stint_strategy      import calculate_strategy, StrategyReport
from core.file_watcher        import FileWatcher
from core.setup_impact        import (predict_impact, get_available_parameters, ImpactReport,
                                       compute_sensitivity_matrix)
from core.setup_optimizer     import optimize_setup, OptimizationTarget, OptimizationResult
from core.racing_line         import reconstruct_racing_line, speed_colormap
from core.gg_diagram          import analyze_gg_per_corner, GGReport
from core.share_export        import (build_share_summary, export_json, export_clipboard_text,
                                       send_discord_webhook)
from core.session_highlights  import detect_highlights, SessionHighlights
from core.motec_export        import export_motec_csv
from core.ml_predictor        import LapTimePredictor, SessionFeatures
from core.ibt_cache           import load_cached, save_cached, evict_old_entries
from core.car_classifier      import classify_car
from core.setup_recommend     import (find_sto_files, score_sto_matches, copy_base_setup,
                                       get_car_setups_dir, build_checklist, StoMatch)

# ── Theme ─────────────────────────────────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

from ui.theme import (DARK, PANEL, CARD, ACCENT, BLUE, TEXT, DIM, GREEN, YELLOW,
                      RED, PURPLE, SEV_COLOR, lbl, card_frame, sec_lbl, stat_blk,
                      _Tooltip, EmbedChart, IssueCard)
from ui.tab_telemetry import TelemetryTabMixin
from ui.tab_corners import CornersTabMixin
from ui.tab_stint import StintTabMixin
from core.config import (get_api_key as _get_api_key, set_api_key as _set_api_key,
                          load_cfg, save_cfg)

MAX_SESSIONS = 20  # LRU eviction when exceeded

# ── Helpers (imported from ui.theme) ──────────────────────────────────────────

# ══════════════════════════════════════════════════════════════════════════════
class App(TelemetryTabMixin, CornersTabMixin, StintTabMixin, ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME}  v{VERSION}")
        # Set window icon
        _icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'app.ico')
        if os.path.exists(_icon_path):
            try:
                self.iconbitmap(_icon_path)
            except Exception:
                pass
        # Restore window geometry
        cfg = load_cfg()
        geo = cfg.get('geometry', '1360x880')
        self.geometry(geo)
        self.configure(fg_color=DARK); self.minsize(1100,700)
        # Save geometry on close
        self.protocol('WM_DELETE_WINDOW', self._on_close)
        # Enable drag-and-drop if tkinterdnd2 is available
        if _HAS_DND:
            try:
                TkinterDnD._require(self)
            except Exception:
                pass
        self.cfg=cfg
        self.sessions:list[tuple[TelemetryData,AnalysisReport]]=[]
        self._analysis_cache:dict[int,tuple]={}  # session-index -> (sec, best, stint, style, fuel)
        self._ai_cache:dict[int,str]={}  # session-index -> AI recommendation text
        self.cur_data:TelemetryData|None=None
        self.cur_rpt:AnalysisReport|None=None
        self.cur_sec:SectorAnalysisReport|None=None
        self.cur_best:BestLapReport|None=None
        self.cur_stint:TireDegReport|None=None
        self.cur_style:DriverStyleReport|None=None
        self.cur_fuel:FuelStrategyReport|None=None
        self.cur_setup:ParsedSetup|None=None
        self.cmp_setup_b:ParsedSetup|None=None
        self.engine=AnalysisEngine()
        self.history=HistoryTracker()
        self._ai_last_text = ""
        self._loading = False
        self._ref_data: TelemetryData | None = None   # external reference IBT
        self._live_monitor: LiveTelemetryMonitor | None = None
        self._live_win = None  # ctk.CTkToplevel for live dashboard
        self._ml_predictor = LapTimePredictor()
        self._ml_features: list[SessionFeatures] = []
        self._last_opt_result: OptimizationResult | None = None
        self._session_notes: dict[int, str] = {}  # session-index → auto-generated note
        self._batch_queue: list[str] = []
        self._batch_total = 0
        self._file_watcher: FileWatcher | None = None
        self._build()
        self._bind_shortcuts()
        threading.Thread(target=evict_old_entries, daemon=True).start()
        # Restore last active tab/chart
        saved_tab = self.cfg.get('last_tab')
        if saved_tab:
            try: self.tv.set(saved_tab)
            except Exception: pass
        saved_chart = self.cfg.get('last_chart')
        if saved_chart and saved_chart in self.CDEFS:
            self._tv.set(saved_chart)

    def _on_close(self):
        """Save state and exit cleanly."""
        if self._loading:
            if not messagebox.askyesno("Confirm Exit",
                    "A telemetry file is still loading.\nExit anyway?"):
                return
        if self._file_watcher and self._file_watcher.is_running:
            self._file_watcher.stop()
        if self._live_monitor and self._live_monitor.is_running:
            self._live_monitor.stop()
        try:
            self.cfg['geometry'] = self.geometry()
            self.cfg['last_tab'] = self.tv.get()
            self.cfg['last_chart'] = self._tv.get()
            save_cfg(self.cfg)
        except Exception:
            pass
        self.destroy()

    def _bind_shortcuts(self):
        """Register global keyboard shortcuts."""
        self.bind_all('<Control-o>', lambda e: self._load_ibt())
        self.bind_all('<Control-d>', lambda e: self._load_demo())
        self.bind_all('<Control-e>', lambda e: self._export_csv())
        self.bind_all('<Control-p>', lambda e: self._export_pdf())
        self.bind_all('<Control-q>', lambda e: self._on_close())
        self.bind_all('<Control-b>', lambda e: self._batch_load())
        self.bind_all('<Control-s>', lambda e: self._share_export())
        # Tab navigation: Ctrl+1 through Ctrl+9 for first 9 tabs
        tabs = ["Dashboard","Telemetry","Issues","Driver","Sectors","Corners",
                "Stint & Tires","Lap Times","Setup Files"]
        for i, tab in enumerate(tabs):
            self.bind_all(f'<Control-Key-{i+1}>', lambda e, t=tab: self.tv.set(t))
        # F5 = reload/refresh current tab
        self.bind_all('<F5>', lambda e: self._refresh())
        # Ctrl+W = toggle file watcher
        self.bind_all('<Control-w>', lambda e: self._toggle_file_watcher())
        self.bind_all('<Control-k>', lambda e: self._open_command_palette())
        self.bind_all('<Control-m>', lambda e: self._export_motec())

    # ── LAYOUT ────────────────────────────────────────────────────────────────
    def _build(self):
        hdr=ctk.CTkFrame(self,fg_color=PANEL,height=54,corner_radius=0)
        hdr.pack(fill='x'); hdr.pack_propagate(False)
        lbl(hdr,f"🏎  {APP_NAME}",17,bold=True).pack(side='left',padx=18)
        self._status_lbl = lbl(hdr,"",11,color=YELLOW)
        self._status_lbl.pack(side='left',padx=12)
        # Progress bar (hidden by default)
        self._progress = ctk.CTkProgressBar(hdr, width=120, height=14,
            fg_color=CARD, progress_color=ACCENT, mode='indeterminate')
        self._load_btns = []
        for t,cmd,bg in [("⚙ Settings",self._settings,"transparent"),
                          ("❓ About",self._about,"transparent"),
                          ("👁 Watch",self._toggle_file_watcher,"transparent"),
                          ("🔴 Live",self._toggle_live,CARD),
                          ("📤 Share",self._share_export,CARD),
                          ("Load Demo",self._load_demo,CARD),
                          ("📂 Load IBT",self._load_ibt,ACCENT)]:
            btn=ctk.CTkButton(hdr,text=t,width=110,height=30,fg_color=bg,
                hover_color="#2a3050" if bg=="transparent" else "#c0392b",
                command=cmd)
            btn.pack(side='right',padx=4)
            if "Load" in t:
                self._load_btns.append(btn)
        main=ctk.CTkFrame(self,fg_color="transparent"); main.pack(fill='both',expand=True)
        self._sidebar(main); self._tabs(main)
        # Register drag-and-drop on the entire window
        if _HAS_DND:
            try:
                self.drop_target_register(DND_FILES)
                self.dnd_bind('<<Drop>>', self._on_drop)
            except Exception:
                pass

    def _on_drop(self, event):
        """Handle files dropped onto the application window."""
        raw = event.data
        # tkdnd wraps paths with spaces in braces: {C:\path with space\file.ibt}
        paths = []
        if '{' in raw:
            import re
            paths = re.findall(r'\{([^}]+)\}', raw)
        else:
            paths = raw.strip().split()
        for path in paths:
            path = path.strip()
            # Validate: must be an existing file with an allowed extension
            if not os.path.isfile(path):
                continue
            lower = path.lower()
            if lower.endswith('.ibt'):
                self.cfg['last_dir'] = os.path.dirname(path)
                save_cfg(self.cfg)
                self._process(path)
                return
            elif lower.endswith(('.htm', '.html')):
                try:
                    self.cur_setup = SetupParser().parse_file(path)
                    self._render_setup(self.cur_setup)
                    self.tv.set("Setup Files")
                except Exception as ex:
                    logger.exception("Failed to load dropped setup file")
                    messagebox.showerror("Error", f"Failed to load setup file:\n{type(ex).__name__}: {ex}")
                return
        dropped = [os.path.basename(p) for p in paths[:3]]
        msg = f"Cannot open: {', '.join(dropped)}\nOnly .ibt telemetry and .htm setup files are supported." if dropped else "Drop .ibt telemetry or .htm setup files."
        messagebox.showinfo("Unsupported", msg)

    def _sidebar(self,parent):
        sb=ctk.CTkFrame(parent,fg_color=PANEL,width=210,corner_radius=0)
        sb.pack(side='left',fill='y'); sb.pack_propagate(False)
        lbl(sb,"SESSIONS",9,bold=True,color=DIM).pack(anchor='w',padx=12,pady=(10,3))
        self._sf=ctk.CTkScrollableFrame(sb,fg_color="transparent")
        self._sf.pack(fill='both',expand=True,padx=6)
        self._no_sess=lbl(self._sf,"No sessions loaded.\nLoad IBT or Demo to begin.",11,color=DIM,justify='center')
        self._no_sess.pack(pady=30)

    def _add_sess_card(self,data,rpt):
        self._no_sess.pack_forget()
        f=ctk.CTkFrame(self._sf,fg_color=CARD,corner_radius=7,cursor="hand2"); f.pack(fill='x',pady=3)
        f._session_data = data
        lbl(f,data.car_name.replace('_',' ').title(),12,bold=True).pack(anchor='w',padx=8,pady=(6,0))
        lbl(f,data.track_name,10,color=DIM).pack(anchor='w',padx=8)
        lbl(f,f"Best: {format_laptime(rpt.best_lap)}",11,color=GREEN).pack(anchor='w',padx=8,pady=(2,6))
        for w in [f]+list(f.winfo_children()): w.bind("<Button-1>",lambda e,d=data,r=rpt:self._sel(d,r))
        self._highlight_card(data)

    def _highlight_card(self, active_data):
        """Highlight the sidebar card for the active session."""
        for w in self._sf.winfo_children():
            if isinstance(w, ctk.CTkFrame) and hasattr(w, '_session_data'):
                w.configure(fg_color="#1a4a6a" if w._session_data is active_data else CARD)

    def _tabs(self,parent):
        self.tv=ctk.CTkTabview(parent,fg_color=DARK,
            segmented_button_fg_color=PANEL,
            segmented_button_selected_color=ACCENT,
            segmented_button_selected_hover_color="#c0392b",
            segmented_button_unselected_hover_color="#2a3050")
        self.tv.pack(fill='both',expand=True,padx=6,pady=6)
        tabs=["Dashboard","Telemetry","Issues","Driver","Sectors","Corners",
              "Stint & Tires","Lap Times","Brake Trace","Strategy","Trends",
              "Impact","Setup Files","AI Advisor","Templates","History","Compare"]
        for t in tabs: self.tv.add(t)
        self.tv.configure(command=self._on_tab_change)
        # Lazy tab loading: only build Dashboard + Telemetry on startup.
        # Other tabs are built on first visit.
        self._built_tabs: set[str] = set()
        self._tab_builders = {
            "Dashboard": self._t_dashboard, "Telemetry": self._t_telemetry,
            "Issues": self._t_issues, "Driver": self._t_driver,
            "Sectors": self._t_sectors, "Corners": self._t_corners,
            "Stint & Tires": self._t_stint, "Lap Times": self._t_laptimes,
            "Brake Trace": self._t_brake_trace, "Strategy": self._t_strategy,
            "Trends": self._t_trends, "Impact": self._t_impact,
            "Setup Files": self._t_setup, "AI Advisor": self._t_ai,
            "Templates": self._t_templates, "History": self._t_history,
            "Compare": self._t_compare,
        }
        # Build the two most-used tabs immediately
        for name in ("Dashboard", "Telemetry"):
            self._tab_builders[name]()
            self._built_tabs.add(name)

    # ══════════════════════════════════════════════════════════════════════════
    # DASHBOARD
    # ══════════════════════════════════════════════════════════════════════════
    def _t_dashboard(self):
        tab=self.tv.tab("Dashboard"); tab.configure(fg_color=DARK)
        self._dash_ph=lbl(tab,"Load an IBT file or 'Load Demo' to start.",14,color=DIM); self._dash_ph.pack(expand=True)
        self._dash_sc=ctk.CTkScrollableFrame(tab,fg_color="transparent")
        r1=ctk.CTkFrame(self._dash_sc,fg_color="transparent"); r1.pack(fill='x',padx=10,pady=(8,4))
        self._di=card_frame(r1); self._di.pack(side='left',fill='both',expand=True,padx=(0,6))
        self._dc=EmbedChart(r1,figsize=(4,2)); self._dc.pack(side='left',fill='both',expand=True)
        r2=ctk.CTkFrame(self._dash_sc,fg_color="transparent"); r2.pack(fill='x',padx=10,pady=4)
        self._dth=EmbedChart(r2,figsize=(5,2.8)); self._dth.pack(side='left',fill='both',expand=True,padx=(0,6))
        self._dl=ctk.CTkFrame(r2,fg_color=PANEL,corner_radius=8); self._dl.pack(side='left',fill='both',expand=True)
        self._dif=ctk.CTkFrame(self._dash_sc,fg_color="transparent"); self._dif.pack(fill='x',padx=10,pady=(4,4))
        self._dbal=EmbedChart(self._dash_sc,figsize=(10,2.0))
        self._dh=ctk.CTkFrame(self._dash_sc,fg_color="transparent"); self._dh.pack(fill='x',padx=10,pady=(0,10))

    def _u_dashboard(self):
        d,r=self.cur_data,self.cur_rpt
        if d is None or r is None:
            return
        self._dash_ph.pack_forget(); self._dash_sc.pack(fill='both',expand=True)
        for w in self._di.winfo_children(): w.destroy()
        car_class = classify_car(d.car_name)
        car_row = ctk.CTkFrame(self._di, fg_color="transparent"); car_row.pack(fill='x', padx=12, pady=(10,0))
        lbl(car_row, d.car_name.replace('_',' ').title(), 15, bold=True).pack(side='left')
        if car_class.value != 'default':
            cls_badge = ctk.CTkLabel(car_row, text=car_class.value.upper().replace('_',' '),
                font=ctk.CTkFont(size=9, weight='bold'),
                fg_color=PURPLE, text_color="white", corner_radius=4,
                width=0, height=18, padx=6)
            cls_badge.pack(side='left', padx=(8,0), pady=2)
        lbl(self._di, d.track_name, 12, color=DIM).pack(anchor='w', padx=12)
        # Session metadata
        si = d.session_info
        meta_parts = []
        if si.get('driver_name'): meta_parts.append(si['driver_name'])
        if si.get('session_type'): meta_parts.append(si['session_type'])
        if si.get('track_length_km'): meta_parts.append(f"{si['track_length_km']:.2f} km")
        if si.get('weather_type') or si.get('skies'):
            meta_parts.append(si.get('skies', si.get('weather_type', '')))
        if meta_parts:
            lbl(self._di, '  •  '.join(meta_parts), 10, color=DIM).pack(anchor='w', padx=12)
        sr=ctk.CTkFrame(self._di,fg_color="transparent"); sr.pack(fill='x',padx=12,pady=6)
        stat_blk(sr,"Best Lap",format_laptime(r.best_lap),GREEN,tooltip="Fastest valid lap time in session")
        stat_blk(sr,"Avg Lap",format_laptime(r.avg_lap),tooltip="Average of all valid (non-outlier) laps")
        stat_blk(sr,"Laps",str(d.num_laps),tooltip="Total laps completed in session")
        # Consistency Score (headline metric)
        cs = self._compute_consistency_score()
        if cs:
            sc_color = GREEN if cs.overall >= 85 else YELLOW if cs.overall >= 70 else RED
            stat_blk(sr, "Consistency", f"{cs.overall:.0f}  {cs.grade}", sc_color,
                     tooltip=f"Composite consistency rating: lap times ({cs.lap_time_score:.0f}), sectors ({cs.sector_score:.0f}), corners ({cs.corner_score:.0f}), brakes ({cs.brake_point_score:.0f}), speed ({cs.speed_score:.0f})")
        at=d.session_info.get('air_temp_c')
        tt=d.session_info.get('track_temp_c')
        if at: stat_blk(sr,"Air Temp",f"{at:.1f}°C / {at*9/5+32:.1f}°F",tooltip="Ambient air temperature")
        if tt: stat_blk(sr,"Track Temp",f"{tt:.1f}°C / {tt*9/5+32:.1f}°F",YELLOW,tooltip="Track surface temperature")
        ws=d.session_info.get('wind_speed_ms')
        if ws: stat_blk(sr,"Wind",f"{ws:.1f} m/s",tooltip="Wind speed")
        lbl(self._di,f"🔴 {r.critical_count} Critical  🟡 {r.warning_count} Warning  🔵 {r.info_count} Info",12,color=DIM).pack(anchor='w',padx=12,pady=(0,2))
        # Extra stats row: grip, RPM, coast
        sr2=ctk.CTkFrame(self._di,fg_color="transparent"); sr2.pack(fill='x',padx=12,pady=(0,8))
        if r.grip_utilization_pct>0: stat_blk(sr2,"Grip Used",f"{r.grip_utilization_pct:.0f}%",BLUE,tooltip="% of available tire grip being used (higher=faster but riskier)")
        if r.max_combined_g>0: stat_blk(sr2,"Max G",f"{r.max_combined_g:.1f}",ACCENT,tooltip="Peak combined lateral + longitudinal G-force")
        if r.rev_limiter_pct>0: stat_blk(sr2,"Rev Limiter",f"{r.rev_limiter_pct:.1f}%",RED,tooltip="% of time spent on rev limiter (should be <2%)")
        st=self.cur_style
        if st and st.coast_time_pct>0: stat_blk(sr2,"Coast Time",f"{st.coast_time_pct:.1f}%",YELLOW,tooltip="% of lap with no throttle or brake (wasted time)")
        if st and st.full_throttle_pct>0: stat_blk(sr2,"Full Throt.",f"{st.full_throttle_pct:.0f}%",GREEN,tooltip="% of lap at 100% throttle")
        if r.outlier_count>0: stat_blk(sr2,"Outliers",f"{r.outlier_count} laps",YELLOW,tooltip="Laps excluded from averages (pit laps, incidents, etc.)")
        self._draw_balance(r.balance_score)
        if r.tire_summary: self._draw_tires(r.tire_summary)
        self._draw_balance_timeline(r)
        for w in self._dl.winfo_children(): w.destroy()
        lbl(self._dl,"Lap Times",12,bold=True).pack(anchor='w',padx=10,pady=(8,3))
        best=r.best_lap
        fc=getattr(self.cur_best,'fuel_corrected',[]) or []
        mask=r.valid_lap_mask if r.valid_lap_mask else [True]*len(r.lap_times)
        for i,t in enumerate(r.lap_times[:10]):
            is_outlier=i<len(mask) and not mask[i]
            clr=GREEN if t==best else DIM if is_outlier else TEXT
            delta=f" +{t-best:.3f}s" if t!=best and best>0 else ""
            fc_s=f"  fc:{format_laptime(fc[i])}" if i<len(fc) else ""
            flag="  ⚠" if is_outlier else ""
            lbl(self._dl,f"Lap {i+1}: {format_laptime(t)}{delta}{fc_s}{flag}",10,color=clr).pack(anchor='w',padx=10)
        for w in self._dif.winfo_children(): w.destroy()
        lbl(self._dif,"Top Issues",13,bold=True).pack(anchor='w',pady=(4,4))
        for iss in r.issues[:3]: IssueCard(self._dif,iss).pack(fill='x',pady=2)
        # Consistency breakdown card
        if cs and cs.overall > 0:
            self._draw_consistency_card(cs)
        # Session Highlights
        self._draw_highlights(d, r, cs)
        # ML prediction (shown if enough sessions trained)
        self._draw_ml_prediction(d, r)

    def _draw_highlights(self, d, r, cs):
        """Render session highlight cards in the _dh frame."""
        for w in self._dh.winfo_children(): w.destroy()
        hl = detect_highlights(d, r,
                               sector_report=self.cur_sec,
                               style_report=self.cur_style,
                               consistency=cs)
        if not hl.highlights:
            return
        lbl(self._dh, "Session Highlights", 13, bold=True).pack(anchor='w', pady=(6, 4))
        grid = ctk.CTkFrame(self._dh, fg_color="transparent"); grid.pack(fill='x')
        CAT_COLOR = {'best': GREEN, 'consistency': BLUE, 'event': YELLOW, 'worst': RED}
        cols = 4
        for idx, h in enumerate(hl.highlights):
            col = idx % cols
            row = idx // cols
            card = ctk.CTkFrame(grid, fg_color=PANEL, corner_radius=8, width=200, height=80)
            card.grid(row=row, column=col, padx=4, pady=4, sticky='nsew')
            card.grid_propagate(False)
            grid.columnconfigure(col, weight=1)
            top = ctk.CTkFrame(card, fg_color="transparent"); top.pack(fill='x', padx=8, pady=(6, 0))
            lbl(top, h.emoji, 12).pack(side='left')
            c_col = CAT_COLOR.get(h.category, TEXT)
            lbl(top, h.metric_label, 11, bold=True, color=c_col).pack(side='right')
            lbl(card, h.title, 10, bold=True).pack(anchor='w', padx=8)
            lbl(card, h.description, 9, color=DIM, wraplength=190,
                justify='left').pack(anchor='w', padx=8, pady=(1, 4))

    def _draw_ml_prediction(self, d, r):
        """Show ML lap time prediction if predictor is trained."""
        if not self._ml_predictor.is_trained:
            return
        feat = self._ml_predictor.extract(d, r)
        if feat is None:
            return
        result = self._ml_predictor.predict(feat)
        if result is None:
            return
        mf = ctk.CTkFrame(self._dh, fg_color=PANEL, corner_radius=8); mf.pack(fill='x', pady=(6, 0))
        mr = ctk.CTkFrame(mf, fg_color="transparent"); mr.pack(fill='x', padx=12, pady=8)
        lbl(mr, "🤖 ML Prediction", 11, bold=True).pack(side='left', padx=(0, 12))
        pred_col = GREEN if result.delta_vs_actual < -0.05 else YELLOW if abs(result.delta_vs_actual) < 0.05 else RED
        stat_blk(mr, "Predicted Pace", format_laptime(result.predicted_lap_s), pred_col,
                 tooltip=f"Based on {result.n_sessions} sessions (±{result.residual_std:.3f}s model error)")
        stat_blk(mr, "vs Actual", f"{result.delta_vs_actual:+.3f}s",
                 GREEN if result.delta_vs_actual < 0 else RED)
        stat_blk(mr, "Confidence", f"{result.confidence:.0%}", BLUE)
        lbl(mf, result.insight, 10, color=DIM, wraplength=900,
            justify='left').pack(anchor='w', padx=12, pady=(0, 8))

    def _draw_balance(self,score):
        c=self._dc; c.clear()
        r = self.cur_rpt
        # Draw 4 balance gauges: overall + entry/mid/exit
        phases = [
            ("Overall", score),
            ("Entry", r.balance_entry if r else 0),
            ("Mid", r.balance_mid if r else 0),
            ("Exit", r.balance_exit if r else 0),
        ]
        for idx, (name, val) in enumerate(phases):
            ax = c.fig.add_subplot(1, 4, idx + 1, facecolor=PANEL)
            ax.axis('off')
            grad = np.linspace(-1, 1, 200).reshape(1, -1)
            ax.imshow(grad, aspect='auto', cmap='RdYlGn_r', extent=(-1, 1, -0.15, 0.15), vmin=-1, vmax=1)
            ax.axvline(val, color='white', lw=2.5, zorder=5)
            ax.set_xlim(-1.3, 1.3); ax.set_ylim(-0.6, 0.6)
            ax.text(-1.15, -0.4, "US", color=GREEN, fontsize=7, fontweight='bold')
            ax.text(0.9, -0.4, "OS", color=RED, fontsize=7, fontweight='bold')
            verdict = "US" if val < -0.15 else "OS" if val > 0.15 else "OK"
            ax.text(val, 0.35, verdict, ha='center', color='white', fontsize=8, fontweight='bold')
            ax.set_title(name, color=TEXT, fontsize=9, pad=2)
        c.fig.tight_layout(pad=0.3); c.draw()

    def _draw_balance_timeline(self, r):
        """Render a per-lap balance bar chart below the issues section."""
        timeline = r.balance_timeline if r else []
        if len(timeline) < 2:
            try: self._dbal.pack_forget()
            except Exception: pass
            return
        self._dbal.pack(fill='x', padx=10, pady=(0, 4))
        c = self._dbal; c.clear()
        ax = c.fig.add_subplot(111, facecolor=PANEL)
        laps = list(range(1, len(timeline) + 1))
        colors = [GREEN if v > 0.05 else RED if v < -0.05 else BLUE for v in timeline]
        ax.bar(laps, timeline, color=colors, alpha=0.82, width=0.65, zorder=3)
        ax.axhline(0, color=DIM, lw=0.8, ls='--', zorder=2)
        ax.axhspan(-0.05, 0.05, color=BLUE, alpha=0.07)
        ax.set_xlim(0.3, len(laps) + 0.7)
        ax.set_ylim(-1.05, 1.05)
        ax.set_xlabel("Lap", color=DIM, fontsize=8)
        ax.set_ylabel("← Understeer   Oversteer →", color=DIM, fontsize=7)
        ax.tick_params(colors=DIM, labelsize=7)
        for spine in ax.spines.values(): spine.set_edgecolor('#2a3050')
        ax.set_title("Balance Timeline — per lap", color=TEXT, fontsize=9, pad=3)
        ax.set_facecolor(PANEL)
        c.fig.patch.set_facecolor(PANEL)
        c.fig.tight_layout(pad=0.5); c.draw()

    def _draw_tires(self,ts):
        c=self._dth; c.clear(); ax=c.fig.add_subplot(111,facecolor=PANEL)
        ax.set_title("Tire Temps (°C / °F)",color=TEXT,fontsize=11); ax.set_xlim(0,4); ax.set_ylim(0,3); ax.axis('off')
        pos={'LF':(0.5,2.2),'RF':(2.5,2.2),'LR':(0.5,0.2),'RR':(2.5,0.2)}
        for corner,(cx,cy) in pos.items():
            t=ts.get(corner,{})
            if not t: continue
            for i,z in enumerate(['inner','mid','outer']):
                tv=t.get(z,75); norm=np.clip((tv-70)/40,0,1)
                cmap=matplotlib.colormaps['RdYlGn_r']
                rect=matplotlib.patches.Rectangle((cx+i*0.28-0.42,cy),0.28,0.5,facecolor=cmap(norm),edgecolor='#2a3050',lw=0.5)
                ax.add_patch(rect)
                ax.text(cx+i*0.28-0.28,cy+0.25,f"{tv:.0f}",ha='center',va='center',fontsize=7,color='white',fontweight='bold')
            ax.text(cx,cy+0.72,corner,ha='center',fontsize=11,color=TEXT,fontweight='bold')
            avg_c=t.get('avg',0); avg_f=avg_c*9/5+32
            ax.text(cx,cy-0.18,f"avg {avg_c:.1f}°C / {avg_f:.1f}°F",ha='center',fontsize=7,color=DIM)
        c.fig.tight_layout(pad=0.3); c.draw()

    def _compute_consistency_score(self) -> ConsistencyBreakdown | None:
        """Compute and cache the consistency score for the current session."""
        d, r = self.cur_data, self.cur_rpt
        if not d or not r or not r.lap_times:
            return None
        return compute_consistency(
            lap_times=r.lap_times,
            valid_mask=r.valid_lap_mask,
            sector_report=self.cur_sec,
            corner_report=getattr(self, 'cur_corner_report', None),
            style_report=self.cur_style,
        )

    def _draw_consistency_card(self, cs: ConsistencyBreakdown):
        """Draw a consistency breakdown card on the dashboard."""
        cf = ctk.CTkFrame(self._dif, fg_color="#1e2845", corner_radius=8)
        cf.pack(fill='x', pady=(6, 2))
        # Header
        sc_color = GREEN if cs.overall >= 85 else YELLOW if cs.overall >= 70 else RED
        hdr = ctk.CTkFrame(cf, fg_color="transparent"); hdr.pack(fill='x', padx=12, pady=(8, 4))
        lbl(hdr, f"🎯 Consistency Score: {cs.overall:.0f}/100  ({cs.grade})", 13, bold=True, color=sc_color).pack(side='left')
        # Sub-score bars
        bars = ctk.CTkFrame(cf, fg_color="transparent"); bars.pack(fill='x', padx=12, pady=(0, 4))
        components = [
            ("Lap Times", cs.lap_time_score, f"±{cs.lap_time_std_s:.3f}s std"),
            ("Sectors", cs.sector_score, f"Worst: S{cs.worst_sector}" if cs.worst_sector else ""),
            ("Corners", cs.corner_score, f"Worst: T{cs.worst_corner}" if cs.worst_corner else ""),
            ("Brake Points", cs.brake_point_score, ""),
            ("Speed", cs.speed_score, ""),
        ]
        for name, score, detail in components:
            row = ctk.CTkFrame(bars, fg_color="transparent"); row.pack(fill='x', pady=1)
            clr = GREEN if score >= 85 else YELLOW if score >= 70 else RED
            lbl(row, f"{name}:", 9, color=DIM).pack(side='left', padx=(0, 4))
            # Progress bar
            pb = ctk.CTkProgressBar(row, width=120, height=10,
                fg_color="#0d1b2a", progress_color=clr, corner_radius=4)
            pb.pack(side='left', padx=4)
            pb.set(score / 100)
            lbl(row, f"{score:.0f}", 9, bold=True, color=clr).pack(side='left', padx=4)
            if detail:
                lbl(row, detail, 8, color=DIM).pack(side='left', padx=4)
        # Coaching notes
        if cs.notes:
            nf = ctk.CTkFrame(cf, fg_color="#0d1b2a", corner_radius=6)
            nf.pack(fill='x', padx=12, pady=(2, 8))
            for note in cs.notes[:3]:
                lbl(nf, f"• {note}", 9, color=TEXT, wraplength=500, justify='left', anchor='w').pack(
                    fill='x', padx=8, pady=1)

    # ══════════════════════════════════════════════════════════════════════════
    # ISSUES
    # ══════════════════════════════════════════════════════════════════════════
    def _t_issues(self):
        tab=self.tv.tab("Issues"); tab.configure(fg_color=DARK)
        fbar=ctk.CTkFrame(tab,fg_color=PANEL,height=44,corner_radius=8)
        fbar.pack(fill='x',padx=10,pady=(8,4)); fbar.pack_propagate(False)
        lbl(fbar,"Filter:",color=DIM).pack(side='left',padx=10)
        for f in ["All","Critical","Warning","Info"]:
            ctk.CTkButton(fbar,text=f,width=75,height=28,fg_color=CARD,
                hover_color="#1a5a8a",command=lambda v=f:self._pop_issues(v)).pack(side='left',padx=3)
        self._is=ctk.CTkScrollableFrame(tab,fg_color="transparent")
        self._is.pack(fill='both',expand=True,padx=10,pady=(4,8))
        lbl(self._is,"Load a session to see diagnostic issues.",14,color=DIM).pack(pady=40)

    def _pop_issues(self,flt="All"):
        for w in self._is.winfo_children(): w.destroy()
        if not self.cur_rpt: return
        sm={"Critical":Severity.CRITICAL,"Warning":Severity.WARNING,"Info":Severity.INFO}
        issues=[i for i in self.cur_rpt.issues if flt=="All" or i.severity==sm.get(flt)]
        if not issues: lbl(self._is,"No issues for this filter.",color=DIM).pack(pady=20); return
        for iss in issues: IssueCard(self._is,iss).pack(fill='x',pady=3)

    # ══════════════════════════════════════════════════════════════════════════
    # DRIVER ANALYSIS
    # ══════════════════════════════════════════════════════════════════════════
    def _t_driver(self):
        tab=self.tv.tab("Driver"); tab.configure(fg_color=DARK)
        hdr=ctk.CTkFrame(tab,fg_color=PANEL,height=46,corner_radius=8)
        hdr.pack(fill='x',padx=10,pady=(8,4)); hdr.pack_propagate(False)
        lbl(hdr,"🧠  Driver vs. Car Analysis — Are issues driver technique or car setup?",12,bold=True).pack(side='left',padx=12)
        self._drs=ctk.CTkScrollableFrame(tab,fg_color="transparent")
        self._drs.pack(fill='both',expand=True,padx=10,pady=(4,8))

    def _u_driver(self):
        r=self.cur_style; f=self._drs
        for w in f.winfo_children(): w.destroy()
        if not r:
            lbl(f,"Load a session with at least 1 complete lap for driver analysis.",color=DIM).pack(pady=30); return
        row=ctk.CTkFrame(f,fg_color="transparent"); row.pack(fill='x',pady=(4,8))
        for name,score,col in [("Overall",r.overall_score,ACCENT),("Braking",r.brake_consistency,BLUE),
                                ("Throttle",r.throttle_smoothness,GREEN),("Steering",r.steering_smoothness,YELLOW),
                                ("Trail Brake",r.trail_braking_score,PURPLE),("Stability",r.oversteer_management,RED)]:
            sc=card_frame(row); sc.pack(side='left',fill='both',expand=True,padx=3)
            lbl(sc,name,9,color=DIM).pack(pady=(8,0))
            lbl(sc,f"{score:.0f}",22,bold=True,color=col).pack()
            lbl(sc,"/100",9,color=DIM).pack()
            pb=ctk.CTkProgressBar(sc,width=70,height=5,progress_color=col,fg_color="#1e2845")
            pb.set(score/100); pb.pack(pady=(2,8))
        if r.style_profile:
            pf=ctk.CTkFrame(f,fg_color=PANEL,corner_radius=8); pf.pack(fill='x',pady=4)
            lbl(pf,f"🏁 Profile: {r.style_profile}",12,bold=True,color=BLUE).pack(anchor='w',padx=12,pady=(8,2))
            if r.balance_verdict: lbl(pf,f"⚖ Balance Verdict: {r.balance_verdict}",11,color=YELLOW).pack(anchor='w',padx=12,pady=(0,8))
        sec_lbl(f,"📊 Key Metrics")
        mf=ctk.CTkFrame(f,fg_color=PANEL,corner_radius=8); mf.pack(fill='x',pady=2)
        for lab,val in [("Brake Point Consistency",f"{r.brake_point_std*100:.3f}% std"),
                        ("Throttle Blips",str(r.throttle_blips)),
                        ("Steering Reversals/Lap",str(r.steering_reversals)),
                        ("Trail Braking Usage",f"{r.trail_braking_pct:.1f}% of zones"),
                        ("Oversteer Events",str(r.oversteer_events)),
                        ("Understeer Events",str(r.understeer_events))]:
            rw=ctk.CTkFrame(mf,fg_color="transparent"); rw.pack(fill='x',padx=12,pady=3)
            lbl(rw,lab,11,color=DIM).pack(side='left'); lbl(rw,val,11,bold=True).pack(side='right')
        if r.findings:
            sec_lbl(f,"🔍 Findings")
            for fn in r.findings:
                ff=ctk.CTkFrame(f,fg_color="#1e2845",corner_radius=6); ff.pack(fill='x',pady=2)
                lbl(ff,f"•  {fn}",11,color=TEXT,wraplength=780,justify='left',anchor='w').pack(padx=12,pady=6)
        if r.recommendations:
            sec_lbl(f,"💡 Technique Tips")
            for rec in r.recommendations:
                rf=ctk.CTkFrame(f,fg_color="#0f2a1a",corner_radius=6); rf.pack(fill='x',pady=2)
                lbl(rf,f"→  {rec}",11,color=GREEN,wraplength=780,justify='left',anchor='w').pack(padx=12,pady=6)

    # ══════════════════════════════════════════════════════════════════════════
    # SECTORS
    # ══════════════════════════════════════════════════════════════════════════
    def _t_sectors(self):
        tab=self.tv.tab("Sectors"); tab.configure(fg_color=DARK)
        self._ph_sectors=lbl(tab,"Load a session to see sector analysis.",14,color=DIM)
        self._ph_sectors.pack(pady=40)
        ctrl=ctk.CTkFrame(tab,fg_color=PANEL,height=46,corner_radius=8)
        ctrl.pack(fill='x',padx=10,pady=(8,4)); ctrl.pack_propagate(False)
        lbl(ctrl,"Sectors:",color=DIM).pack(side='left',padx=10)
        self._sn=ctk.StringVar(value="3")
        ctk.CTkOptionMenu(ctrl,values=["3","4","5","6"],variable=self._sn,
            fg_color=CARD,button_color=ACCENT,width=70,command=lambda _:self._u_sectors()).pack(side='left',padx=8)
        self._secsc=ctk.CTkScrollableFrame(tab,fg_color="transparent")
        self._secsc.pack(fill='both',expand=True,padx=10,pady=(4,8))
        self._sec_bar=EmbedChart(self._secsc,figsize=(10,2.5)); self._sec_bar.pack(fill='x',pady=(0,4))
        self._sec_tmp=EmbedChart(self._secsc,figsize=(10,2.5)); self._sec_tmp.pack(fill='x',pady=(0,4))
        self._sec_det=ctk.CTkFrame(self._secsc,fg_color="transparent"); self._sec_det.pack(fill='x')

    def _u_sectors(self):
        if not self.cur_data: return
        n=int(self._sn.get())
        self.cur_sec=SectorAnalyzer().analyze(self.cur_data,n)
        self._draw_sectors()

    def _draw_sectors(self):
        r=self.cur_sec
        if not r or not r.sectors: return
        try: self._ph_sectors.pack_forget()
        except Exception: pass
        S=r.sectors
        xlabs=[f"S{i+1}\n{s.start_pct*100:.0f}–{s.end_pct*100:.0f}%" for i,s in enumerate(S)]
        # Bar chart
        c=self._sec_bar; c.clear(); ax=c.std_ax("Sector Times — Avg vs Best",xlabel="Sector")
        x=np.arange(len(S)); w=0.35
        avgs=[s.avg_time for s in S]; bests=[s.best_time for s in S]
        bcols=[RED if i==r.worst_sector else BLUE for i in range(len(S))]
        ax.bar(x-w/2,avgs,w,label='Avg',color=bcols,alpha=0.85)
        ax.bar(x+w/2,bests,w,label='Best',color=GREEN,alpha=0.85)
        ax.set_xticks(x); ax.set_xticklabels(xlabs,color=DIM,fontsize=8)
        ax.set_ylabel("seconds",color=DIM,fontsize=8)
        ax.legend(fontsize=8,facecolor='#1e2845',edgecolor='#2a3050',labelcolor=TEXT)
        c.fig.tight_layout(pad=0.8); c.draw()
        # Temp chart
        c2=self._sec_tmp; c2.clear(); ax2=c2.std_ax("Avg Tire Temp by Sector",xlabel="Sector")
        for corner,col in [('lf_temps',BLUE),('rf_temps',RED),('lr_temps',GREEN),('rr_temps',YELLOW)]:
            vals=[np.mean(getattr(s,corner)) if getattr(s,corner) else 0 for s in S]
            ax2.plot(xlabs,vals,marker='o',color=col,label=corner[:2].upper(),lw=1.5)
        ax2.legend(fontsize=8,facecolor='#1e2845',edgecolor='#2a3050',labelcolor=TEXT)
        c2.fig.tight_layout(pad=0.8); c2.draw()
        # Detail cards
        for w in self._sec_det.winfo_children(): w.destroy()
        row=ctk.CTkFrame(self._sec_det,fg_color="transparent"); row.pack(fill='x')
        for i,s in enumerate(S):
            sc=card_frame(row); sc.pack(side='left',fill='both',expand=True,padx=4,pady=4)
            worst=i==r.worst_sector
            lbl(sc,f"S{i+1}{'  ← worst' if worst else ''}",12,bold=True,color=RED if worst else TEXT).pack(pady=(8,3))
            lbl(sc,f"Best:  {s.best_time:.3f}s",11,color=GREEN).pack()
            lbl(sc,f"Avg:   {s.avg_time:.3f}s",11).pack()
            lbl(sc,f"Delta: +{s.avg_time-s.best_time:.3f}s",11,color=YELLOW).pack()
            lbl(sc,f"Consistency: {s.consistency:.0f}%",11,color=BLUE).pack()
            spd=np.mean(s.avg_speeds) if s.avg_speeds else 0
            lbl(sc,f"Avg Speed: {spd:.0f} km/h",10,color=DIM).pack(pady=(0,8))
        tb=r.theoretical_best; ab=r.actual_best; left=r.time_left_on_table
        sf=ctk.CTkFrame(self._sec_det,fg_color=PANEL,corner_radius=8); sf.pack(fill='x',pady=6)
        lbl(sf,f"🏆 Theoretical Best: {format_laptime(tb)}  |  Actual Best: {format_laptime(ab)}  |  Time left: +{left:.3f}s",
            12,bold=True,color=GREEN if left<0.3 else YELLOW).pack(pady=10)

    # ══════════════════════════════════════════════════════════════════════════
    # SETUP FILES
    # ══════════════════════════════════════════════════════════════════════════
    def _t_setup(self):
        tab=self.tv.tab("Setup Files"); tab.configure(fg_color=DARK)
        tb=ctk.CTkFrame(tab,fg_color=PANEL,height=50,corner_radius=8)
        tb.pack(fill='x',padx=10,pady=(8,4)); tb.pack_propagate(False)
        for t,cmd,bg in [("📂 Load Setup (.htm)",self._load_setup,ACCENT),
                          ("💾 Export Setup",self._export_setup,CARD),
                          ("🏁 Recommend to iRacing",self._recommend_to_iracing,CARD),
                          ("🔄 Demo Setup",self._demo_setup,CARD),
                          ("📊 Compare Setups",self._cmp_setups,CARD)]:
            ctk.CTkButton(tb,text=t,height=32,fg_color=bg,
                hover_color="#c0392b" if bg==ACCENT else "#1a5a8a",command=cmd).pack(side='left',padx=5,pady=8)
        panes=ctk.CTkFrame(tab,fg_color="transparent"); panes.pack(fill='both',expand=True,padx=10,pady=(4,8))
        self._svf=ctk.CTkScrollableFrame(panes,fg_color=PANEL,corner_radius=8)
        self._svf.pack(side='left',fill='both',expand=True,padx=(0,4))
        lbl(self._svf,"Load a .htm setup file to view parameters.",color=DIM).pack(pady=30)
        self._sdf=ctk.CTkScrollableFrame(panes,fg_color=PANEL,corner_radius=8,width=320)
        self._sdf.pack(side='left',fill='both')
        lbl(self._sdf,"Setup Diff\nLoad two setups to compare",11,color=DIM,justify='center').pack(pady=20)

    def _load_setup(self):
        path=filedialog.askopenfilename(title="Load Setup",initialdir=self.cfg.get('last_dir',''),
            filetypes=[("iRacing Setup","*.htm *.html"),("All","*.*")])
        if not path: return
        try: self.cur_setup=SetupParser().parse_file(path); self._render_setup(self.cur_setup)
        except Exception as e:
            logger.exception("Failed to load setup file")
            messagebox.showerror("Error","Failed to load setup file. Check the file format.")

    def _demo_setup(self):
        car=self.cur_data.car_name if self.cur_data else "ferrari_296_gt3"
        track=self.cur_data.track_name if self.cur_data else "Sebring"
        self.cur_setup=create_demo_setup(car,track); self._render_setup(self.cur_setup)

    def _export_setup(self):
        if not self.cur_setup: messagebox.showwarning("No Setup","Load a setup first."); return
        path=filedialog.asksaveasfilename(title="Export Setup",defaultextension=".htm",
            filetypes=[("iRacing Setup","*.htm")],
            initialfile=f"setup_{datetime.now():%Y%m%d_%H%M}.htm")
        if not path: return
        try: SetupExporter().export_htm(self.cur_setup,path); messagebox.showinfo("Exported",f"Saved to:\n{path}")
        except Exception as e:
            logger.exception("Failed to export setup")
            messagebox.showerror("Error","Failed to export setup file.")

    def _find_iracing_setups_dir(self) -> str | None:
        """Locate the iRacing setups directory."""
        for base in [os.path.expanduser('~/Documents'),
                     os.path.expanduser('~/OneDrive/Documents')]:
            candidate = os.path.join(base, 'iRacing', 'setups')
            if os.path.isdir(candidate):
                return candidate
        return None

    def _recommend_to_iracing(self):
        """Open the Recommend to iRacing dialog, auto-running the optimizer if needed."""
        if not self.cur_rpt:
            messagebox.showwarning("No Telemetry",
                "Load an IBT telemetry file first.\n\n"
                "The app will extract your setup and analyze your driving\n"
                "to generate a personalized recommendation.")
            return

        setups_dir = self._find_iracing_setups_dir()
        if not setups_dir:
            messagebox.showerror("iRacing Not Found",
                "Could not find the iRacing setups folder.\n\n"
                "Expected at:\n  Documents/iRacing/setups/")
            return

        car_name = (self.cur_data.car_name or '') if self.cur_data else ''
        track_name = (self.cur_data.track_name or '') if self.cur_data else ''
        if not car_name and self.cur_setup:
            car_name = self.cur_setup.car or ''

        session_type = 'race'
        if self.cur_data and self.cur_data.session_info:
            st = self.cur_data.session_info.get('session_type', '').lower()
            if 'qual' in st:
                session_type = 'qualify'
            elif 'endur' in st:
                session_type = 'endurance'

        matches = find_sto_files(setups_dir, car_name)
        matches = score_sto_matches(matches, car_name, track_name, session_type)

        # If optimizer hasn't run yet for this session, run it now automatically
        if self._last_opt_result is None:
            self._run_optimizer_for_recommend(matches, car_name, track_name, setups_dir)
        else:
            self._show_recommend_dialog(matches, self._last_opt_result,
                                        car_name, track_name, setups_dir)

    def _run_optimizer_for_recommend(self, matches, car_name, track_name, setups_dir):
        """Run optimizer in background then open recommend dialog."""
        # Build a quick loading dialog
        loading = ctk.CTkToplevel(self)
        loading.title("Optimizing Setup…")
        loading.geometry("340x120")
        loading.configure(fg_color=DARK)
        loading.grab_set()
        loading.lift()
        lbl(loading, "Analyzing your telemetry and optimizing setup…",
            12, color=TEXT, wraplength=300, justify='center').pack(pady=(24, 8))
        bar = ctk.CTkProgressBar(loading, mode='indeterminate', width=260)
        bar.pack(); bar.start()

        balance = self.cur_rpt.balance_score if self.cur_rpt else 0.0
        issues  = [f.title for f in self.cur_rpt.issues] if self.cur_rpt else []

        def worker():
            from core.setup_optimizer import optimize_setup, OptimizationTarget
            result = optimize_setup(
                current_balance=balance,
                current_issues=issues,
                target=OptimizationTarget(mode='balance_and_time'),
                n_generations=60,
                pop_size=80,
            )
            self.after(0, lambda: _done(result))

        def _done(result):
            self._last_opt_result = result
            try:
                bar.stop(); loading.destroy()
            except Exception:
                pass
            self._show_recommend_dialog(matches, result, car_name, track_name, setups_dir)

        threading.Thread(target=worker, daemon=True).start()

    def _show_recommend_dialog(self, matches: list, opt_result, car_name: str,
                                track_name: str, setups_dir: str):
        """Top-level window: pick base .sto + show garage adjustment checklist."""
        win = ctk.CTkToplevel(self)
        win.title("Recommend Setup to iRacing")
        win.geometry("960x680")
        win.configure(fg_color=DARK)
        win.grab_set()
        win.lift()

        # ── Header ────────────────────────────────────────────────────────────
        hdr = ctk.CTkFrame(win, fg_color=PANEL, height=52, corner_radius=0)
        hdr.pack(fill='x')
        hdr.pack_propagate(False)
        lbl(hdr, "🏁  Recommend Setup to iRacing", 14, bold=True).pack(
            side='left', padx=16, pady=14)
        lbl(hdr, f"{car_name}  |  {track_name}", 11, color=DIM).pack(
            side='right', padx=16)

        # ── Content ───────────────────────────────────────────────────────────
        content = ctk.CTkFrame(win, fg_color='transparent')
        content.pack(fill='both', expand=True, padx=12, pady=8)

        # Left column: base setup picker
        left = ctk.CTkFrame(content, fg_color=PANEL, corner_radius=8, width=380)
        left.pack(side='left', fill='both', padx=(0, 6))
        left.pack_propagate(False)

        lbl(left, "Step 1 — Choose a Base Setup", 12, bold=True,
            color=ACCENT).pack(anchor='w', padx=12, pady=(12, 2))
        lbl(left,
            "This .sto file will be copied to your setups folder.\n"
            "Load it in iRacing then apply the Step 2 changes.",
            10, color=DIM, wraplength=340, justify='left').pack(
            anchor='w', padx=12, pady=(0, 8))

        sel_var = ctk.StringVar(value=matches[0].path if matches else '')

        sto_scroll = ctk.CTkScrollableFrame(left, fg_color='transparent')
        sto_scroll.pack(fill='both', expand=True, padx=8, pady=(0, 8))

        best_score = matches[0].score if matches else 0
        for m in matches[:25]:
            badge = '  ★ best match' if m.score == best_score else ''
            stype = m.session_type.upper()
            wet   = '  WET' if m.is_wet else ''
            sub   = f"[{stype}{wet}]{badge}"
            rb = ctk.CTkRadioButton(
                sto_scroll, text=m.filename,
                variable=sel_var, value=m.path,
                fg_color=ACCENT, text_color=TEXT,
                font=ctk.CTkFont(size=10))
            rb.pack(anchor='w', pady=(4, 0), padx=4)
            lbl(sto_scroll, sub, 9, color=GREEN if badge else DIM).pack(
                anchor='w', padx=24, pady=(0, 4))

        # Right column: adjustment checklist
        right = ctk.CTkFrame(content, fg_color=PANEL, corner_radius=8)
        right.pack(side='left', fill='both', expand=True, padx=(6, 0))

        lbl(right, "Step 2 — Apply These Garage Adjustments", 12, bold=True,
            color=ACCENT).pack(anchor='w', padx=12, pady=(12, 2))

        chk_vars = []
        impact_preds = {}
        if opt_result and opt_result.impact:
            impact_preds = {p.parameter: p for p in opt_result.impact.predictions}
        items = build_checklist(opt_result.changes, self.cur_setup,
                                impact_predictions=impact_preds) if opt_result else []

        if items:
            lbl(right,
                f"After loading the base setup, make these {len(items)} changes in "
                "the iRacing garage, then save as your own setup.",
                10, color=DIM, wraplength=520, justify='left').pack(
                anchor='w', padx=12, pady=(0, 8))

            chk_scroll = ctk.CTkScrollableFrame(right, fg_color='transparent')
            chk_scroll.pack(fill='both', expand=True, padx=8, pady=(0, 8))

            for item in items:
                var = ctk.BooleanVar(value=False)
                chk_vars.append((var, item))

                cf = ctk.CTkFrame(chk_scroll, fg_color='#1e2845', corner_radius=6)
                cf.pack(fill='x', pady=3)

                row = ctk.CTkFrame(cf, fg_color='transparent')
                row.pack(fill='x', padx=8, pady=(7, 2))

                ctk.CTkCheckBox(row, text='', variable=var, width=24,
                                fg_color=GREEN, checkmark_color=DARK,
                                border_color=DIM).pack(side='left')
                lbl(row, item.label, 12, bold=True).pack(side='left', padx=(6, 0))
                val_col = GREEN if item.delta > 0 else RED
                lbl(row, item.display, 12, bold=True, color=val_col).pack(
                    side='right', padx=8)

                # Show current → recommended if IBT setup was loaded
                if item.current_value and item.recommended_value:
                    arrow_row = ctk.CTkFrame(cf, fg_color='transparent')
                    arrow_row.pack(fill='x', padx=36, pady=(0, 2))
                    lbl(arrow_row, item.current_value, 11,
                        color=DIM).pack(side='left')
                    lbl(arrow_row, '  →  ', 11, color=DIM).pack(side='left')
                    lbl(arrow_row, item.recommended_value, 11, bold=True,
                        color=val_col).pack(side='left')

                lbl(cf, item.hint, 10, color=DIM).pack(
                    anchor='w', padx=36, pady=(0, 7))
        else:
            mid = ctk.CTkFrame(right, fg_color='transparent')
            mid.pack(expand=True)
            lbl(mid,
                "Run the Setup Optimizer first to get\n"
                "specific garage adjustment recommendations.",
                13, color=DIM, justify='center').pack(pady=20)
            ctk.CTkButton(mid, text="Open Optimizer Tab", width=180, height=34,
                          fg_color=CARD,
                          command=lambda: (win.destroy(),
                                          self.tv.set("Setup Optimizer"))
                          ).pack()

        # ── Footer ────────────────────────────────────────────────────────────
        footer = ctk.CTkFrame(win, fg_color=PANEL, height=62, corner_radius=0)
        footer.pack(fill='x', side='bottom')
        footer.pack_propagate(False)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M')
        name_var = ctk.StringVar(value=f"AI_Recommended_{timestamp}.sto")

        lbl(footer, "Save as:", 11).pack(side='left', padx=(14, 4), pady=18)
        ctk.CTkEntry(footer, textvariable=name_var, width=300, height=32,
                     font=ctk.CTkFont(size=11)).pack(side='left', pady=18)

        def do_copy():
            src = sel_var.get()
            name = name_var.get().strip() or f"AI_Recommended_{timestamp}.sto"
            if not name.endswith('.sto'):
                name += '.sto'
            if not src or not os.path.isfile(src):
                messagebox.showerror("No File Selected",
                                     "Select a base setup file.", parent=win)
                return
            # Copy to the car-level setups dir (one below setups_dir)
            dest_dir = get_car_setups_dir(src, setups_dir)
            try:
                dest = copy_base_setup(src, dest_dir, name)
                checklist_lines = '\n'.join(
                    f"  {'✓' if v.get() else '○'}  {item.label}: {item.display}"
                    for v, item in chk_vars
                ) or "  (Run the Setup Optimizer for specific recommendations)"
                messagebox.showinfo(
                    "Setup Copied!",
                    f"Base setup copied to:\n{dest}\n\n"
                    "─── In iRacing ───\n"
                    "1. Go to Garage → Load Car Setup\n"
                    f"2. Select  '{name}'\n"
                    "3. Apply these garage changes:\n"
                    f"{checklist_lines}\n"
                    "4. Save as your own setup name",
                    parent=win)
            except Exception as e:
                logger.exception("Failed to copy .sto base setup")
                messagebox.showerror("Copy Failed", str(e), parent=win)

        ctk.CTkButton(footer, text="Cancel", width=80, height=36,
                      fg_color=CARD, hover_color='#1a5a8a',
                      command=win.destroy).pack(side='right', padx=(0, 12), pady=13)
        ctk.CTkButton(footer, text="🏁  Copy to iRacing", width=170, height=36,
                      fg_color=ACCENT, hover_color='#c0392b',
                      command=do_copy).pack(side='right', padx=(0, 8), pady=13)

    def _cmp_setups(self):
        if not self.cur_setup: messagebox.showwarning("Need Setup A","Load a primary setup first."); return
        path=filedialog.askopenfilename(title="Load Setup B",filetypes=[("iRacing Setup","*.htm *.html"),("All","*.*")])
        if not path: return
        try: self.cmp_setup_b=SetupParser().parse_file(path); self._render_diff(self.cur_setup,self.cmp_setup_b)
        except Exception as e:
            logger.exception("Failed to load setup B")
            messagebox.showerror("Error","Failed to load setup file for comparison.")

    def _render_setup(self,setup:ParsedSetup):
        f=self._svf
        for w in f.winfo_children(): w.destroy()
        lbl(f,setup.car or "Unknown Car",14,bold=True,color=ACCENT).pack(anchor='w',padx=10,pady=(10,2))
        lbl(f,f"Track: {setup.track or '—'}  |  {setup.filename}",10,color=DIM).pack(anchor='w',padx=10,pady=(0,8))
        for sec in setup.sections:
            if not sec.params: continue
            ctk.CTkFrame(f,fg_color="#2a3050",height=1).pack(fill='x',padx=10,pady=4)
            lbl(f,sec.name,11,bold=True,color=BLUE).pack(anchor='w',padx=10,pady=(2,4))
            for param,val in sec.params.items():
                rw=ctk.CTkFrame(f,fg_color="transparent"); rw.pack(fill='x',padx=10)
                lbl(rw,param,10,color=DIM).pack(side='left')
                lbl(rw,val,10,bold=True).pack(side='right')
        if self.cur_data and self.cur_rpt:
            # Guard: skip if last history entry already matches this session+setup
            prev = self.history._find_last(self.cur_data.car_name, self.cur_data.track_name)
            if not prev or prev.setup_snapshot != setup.flat:
                self.history.add_entry(self.cur_data.car_name,self.cur_data.track_name,
                    self.cur_rpt.best_lap,setup.flat)
            self._u_history()

    def _render_diff(self,a:ParsedSetup,b:ParsedSetup):
        f=self._sdf
        for w in f.winfo_children(): w.destroy()
        lbl(f,"Setup Diff",12,bold=True,color=ACCENT).pack(pady=(10,6))
        changes=SetupDiffer().diff(a,b)
        if not changes: lbl(f,"Setups are identical.",color=DIM).pack(pady=10); return
        lbl(f,f"{len(changes)} differences",10,color=DIM).pack(anchor='w',padx=8)
        for ch in changes:
            rw=ctk.CTkFrame(f,fg_color="#1e2845",corner_radius=5); rw.pack(fill='x',pady=2,padx=4)
            lbl(rw,ch['param'],9,bold=True).pack(anchor='w',padx=8,pady=(5,0))
            lbl(rw,f"A: {ch['before']}",9,color=RED).pack(anchor='w',padx=8)
            lbl(rw,f"B: {ch['after']}",9,color=GREEN).pack(anchor='w',padx=8,pady=(0,5))

    # ══════════════════════════════════════════════════════════════════════════
    # AI ADVISOR
    # ══════════════════════════════════════════════════════════════════════════
    def _t_ai(self):
        tab=self.tv.tab("AI Advisor"); tab.configure(fg_color=DARK)
        hdr=ctk.CTkFrame(tab,fg_color=PANEL,height=50,corner_radius=8)
        hdr.pack(fill='x',padx=10,pady=(8,4)); hdr.pack_propagate(False)
        lbl(hdr,"🤖  Claude AI Setup Recommendations",13,bold=True).pack(side='left',padx=14)
        self._ais=lbl(hdr,"",11,color=DIM); self._ais.pack(side='right',padx=8)
        self._aib=ctk.CTkButton(hdr,text="Get Recommendations",width=170,height=32,
            fg_color=ACCENT,hover_color="#c0392b",command=self._get_ai)
        self._aib.pack(side='right',padx=8)
        # ── Quick setup question bar ──────────────────────────────────────────
        qf=ctk.CTkFrame(tab,fg_color=PANEL,height=40,corner_radius=8)
        qf.pack(fill='x',padx=10,pady=(0,4)); qf.pack_propagate(False)
        lbl(qf,"Ask:",11,color=DIM).pack(side='left',padx=(10,6))
        self._ai_q=ctk.CTkEntry(qf,
            placeholder_text="e.g. What if I soften the front ARB 2 clicks?",
            fg_color=CARD,border_color="#2a3050",height=28)
        self._ai_q.pack(side='left',fill='x',expand=True,padx=(0,6))
        self._ai_q.bind('<Return>', lambda e: self._ask_setup_question())
        self._ai_qb=ctk.CTkButton(qf,text="Ask",width=60,height=28,
            fg_color=BLUE,hover_color="#1a5a8a",command=self._ask_setup_question)
        self._ai_qb.pack(side='right',padx=(0,8))
        # ── Answer box (compact, for quick question replies) ──────────────────
        self._ai_ans=ctk.CTkTextbox(tab,fg_color=CARD,text_color=TEXT,
            font=ctk.CTkFont(family="Helvetica",size=12),wrap='word',height=70)
        self._ai_ans.pack(fill='x',padx=10,pady=(0,4))
        self._ai_ans.insert('1.0',"Type a question above and press Ask or Enter.")
        self._ai_ans.configure(state='disabled')
        # ── Main recommendations box ──────────────────────────────────────────
        self._ait=ctk.CTkTextbox(tab,fg_color=PANEL,text_color=TEXT,
            font=ctk.CTkFont(family="Helvetica",size=13),wrap='word')
        self._ait.pack(fill='both',expand=True,padx=10,pady=(0,8))
        self._ait.insert('1.0',"Load a session then click 'Get Recommendations'.\nRequires Anthropic API key in Settings (⚙).")
        self._ait.configure(state='disabled')

    def _get_ai(self):
        if not self.cur_rpt: messagebox.showwarning("No Session","Load a session first."); return
        # One-time consent for AI data transmission
        if not self.cfg.get('ai_consent'):
            ok = messagebox.askyesno("AI Data Notice",
                "This will send session telemetry data (car, track,\n"
                "tire temps, lap times, setup parameters) to the\n"
                "Anthropic Claude API for analysis.\n\n"
                "No personally identifiable information is included.\n\n"
                "Allow data transmission?")
            if not ok:
                return
            self.cfg['ai_consent'] = True
            save_cfg(self.cfg)
        # Check cache first
        cache_key = next((i for i,(d,_) in enumerate(self.sessions) if d is self.cur_data), None)
        if cache_key is not None and cache_key in self._ai_cache:
            self._ai_last_text = self._ai_cache[cache_key]
            self._ait.configure(state='normal'); self._ait.delete('1.0','end')
            self._ait.insert('1.0', self._ai_last_text); self._ait.configure(state='disabled')
            self._ais.configure(text="✅ Cached")
            return
        key=_get_api_key().strip()
        if not key: messagebox.showwarning("API Key Needed","Set your key in Settings."); self._settings(); return
        self._aib.configure(state='disabled',text="Analyzing…")
        self._ais.configure(text="⏳ Streaming from Claude…")
        self._ait.configure(state='normal'); self._ait.delete('1.0','end')
        self._ai_last_text = ""
        self._ai_cancel = threading.Event()
        cancel = self._ai_cancel  # capture for closure
        def worker():
            if self.cur_data is None:
                return
            setup_flat = self.cur_setup.flat if self.cur_setup else None
            try:
                for chunk in get_ai_recommendations_stream(
                        self.cur_rpt, self.cur_data.car_name, self.cur_data.track_name, key,
                        setup_data=setup_flat,
                        sector_report=self.cur_sec,
                        style_report=self.cur_style,
                        stint_report=self.cur_stint,
                        session_info=self.cur_data.session_info,
                        best_report=self.cur_best,
                        corner_report=getattr(self, 'cur_corner_report', None)):
                    if cancel.is_set():
                        return
                    self.after(0, lambda c=chunk: self._on_ai_chunk(c))
            except Exception as ex:
                logger.warning("AI streaming failed: %s", ex)
                if not cancel.is_set():
                    self.after(0, lambda: self._on_ai_chunk(
                        "\n\n⚠ AI request failed. Check your API key and internet connection.\n"))
                    self.after(0, lambda: self._mark_ai_incomplete())
            if not cancel.is_set():
                self.after(0, self._on_ai_done)
        t = threading.Thread(target=worker, daemon=True)
        t.start()
        def _ai_timeout():
            if t.is_alive():
                cancel.set()
                self.after(0, lambda: (
                    self._ait.configure(state='normal'),
                    self._ait.insert('end', '\n\n⚠ Response incomplete — request timed out after 90 seconds.'),
                    self._ait.configure(state='disabled'),
                    self._aib.configure(state='normal', text="Get Recommendations"),
                    self._ais.configure(text="⚠ Timed out")))
        self.after(90_000, _ai_timeout)

    def _on_ai_chunk(self, chunk):
        self._ait.configure(state='normal')
        self._ait.insert('end', chunk)
        self._ait.see('end')
        self._ait.configure(state='disabled')
        self._ai_last_text += chunk

    def _on_ai_done(self):
        self._aib.configure(state='normal', text="Get Recommendations")
        self._ais.configure(text="✅ Done")
        # Cache result for this session
        if self.cur_data and self._ai_last_text:
            idx = next((i for i,(d,_) in enumerate(self.sessions) if d is self.cur_data), None)
            if idx is not None:
                self._ai_cache[idx] = self._ai_last_text

    def _mark_ai_incomplete(self):
        """Flag that the AI response was not fully received."""
        self._ait.configure(state='normal')
        self._ait.insert('end', '\n\n⚠ Response may be incomplete.')
        self._ait.configure(state='disabled')
        self._ais.configure(text="⚠ Incomplete")

    def _ask_setup_question(self):
        """Stream an answer to the quick natural-language setup question."""
        question = self._ai_q.get().strip()
        if not question:
            return
        if not self.cur_rpt:
            messagebox.showwarning("No Session", "Load a session first.")
            return
        key = _get_api_key().strip()
        if not key:
            messagebox.showwarning("API Key Needed", "Set your key in Settings.")
            self._settings(); return
        self._ai_qb.configure(state='disabled', text="…")
        self._ai_ans.configure(state='normal')
        self._ai_ans.delete('1.0', 'end')
        self._ai_ans.configure(state='disabled')
        cancel = threading.Event()
        self._ai_q_cancel = cancel

        def worker():
            setup_flat = self.cur_setup.flat if self.cur_setup else None
            try:
                for chunk in ask_setup_question_stream(
                        question,
                        self.cur_rpt,
                        self.cur_data.car_name if self.cur_data else "",
                        self.cur_data.track_name if self.cur_data else "",
                        key,
                        setup_data=setup_flat,
                        sector_report=self.cur_sec,
                        session_info=self.cur_data.session_info if self.cur_data else None):
                    if cancel.is_set():
                        return
                    self.after(0, lambda c=chunk: self._on_q_chunk(c))
            except Exception as ex:
                logger.warning("Quick question failed: %s", ex)
            if not cancel.is_set():
                self.after(0, self._on_q_done)

        threading.Thread(target=worker, daemon=True).start()
        self.after(30_000, lambda: (cancel.set(),
                                    self._ai_qb.configure(state='normal', text="Ask")))

    def _on_q_chunk(self, chunk: str):
        self._ai_ans.configure(state='normal')
        self._ai_ans.insert('end', chunk)
        self._ai_ans.see('end')
        self._ai_ans.configure(state='disabled')

    def _on_q_done(self):
        self._ai_qb.configure(state='normal', text="Ask")

    # ══════════════════════════════════════════════════════════════════════════
    # TEMPLATES
    # ══════════════════════════════════════════════════════════════════════════
    def _t_templates(self):
        tab=self.tv.tab("Templates"); tab.configure(fg_color=DARK)
        ctrl=ctk.CTkFrame(tab,fg_color=PANEL,height=50,corner_radius=8)
        ctrl.pack(fill='x',padx=10,pady=(8,4)); ctrl.pack_propagate(False)
        lbl(ctrl,"Car:",color=DIM).pack(side='left',padx=10)
        self._tc2=ctk.StringVar(value="GT3/GT4")
        ctk.CTkOptionMenu(ctrl,values=["GT3/GT4","Formula"],variable=self._tc2,
            fg_color=CARD,button_color=ACCENT,command=self._u_template).pack(side='left',padx=6)
        lbl(ctrl,"Track:",color=DIM).pack(side='left',padx=10)
        tracks=list(list_tracks())
        self._tt=ctk.StringVar(value=tracks[0] if tracks else "")
        ctk.CTkOptionMenu(ctrl,values=tracks,variable=self._tt,width=220,
            fg_color=CARD,button_color=ACCENT,command=self._u_template).pack(side='left',padx=6)
        ctk.CTkButton(ctrl,text="📋 Apply to Setup",height=30,fg_color=CARD,
            hover_color="#1a5a8a",command=self._apply_tmpl).pack(side='right',padx=10)
        self._tmsc=ctk.CTkScrollableFrame(tab,fg_color="transparent")
        self._tmsc.pack(fill='both',expand=True,padx=10,pady=(4,8))
        self._u_template()

    def _u_template(self,*_):
        cc="gt3" if "GT3" in self._tc2.get() else "formula"
        tn=self._tt.get(); tmpl=get_setup_template(cc,tn); info=get_track_info(tn)
        f=self._tmsc
        for w in f.winfo_children(): w.destroy()
        if info:
            lbl(f,f"📍 {info.name}  •  Downforce: {info.downforce_demand.upper()}  •  Tire stress: {info.tire_stress.upper()}",11,color=DIM).pack(anchor='w',pady=(8,2))
            if info.notes: lbl(f,info.notes,10,color=DIM,wraplength=660,justify='left').pack(anchor='w',pady=(0,6))
        def sec(title,items):
            lbl(f,title,12,bold=True,color=BLUE).pack(anchor='w',pady=(8,2))
            for k,v in items:
                rw=ctk.CTkFrame(f,fg_color=PANEL,corner_radius=5); rw.pack(fill='x',pady=1)
                lbl(rw,k,10,color=DIM).pack(side='left',padx=10,pady=4)
                lbl(rw,str(v),10,bold=True).pack(side='right',padx=10)
        if tmpl.front_wing: sec("🌬 Aero",[("Front Wing",tmpl.front_wing),("Rear Wing",tmpl.rear_wing or "—")])
        if tmpl.tire_pressures_psi:
            p=tmpl.tire_pressures_psi; sec("🏎 Cold Pressures",[(c,f"{p.get(c,'—')} PSI") for c in ['LF','RF','LR','RR']])
        if tmpl.camber_deg:
            c2=tmpl.camber_deg; sec("📐 Camber",[(c,f"{c2.get(c,'—')}°") for c in ['LF','RF','LR','RR']])
        susp=[(nm,getattr(tmpl,a)) for a,nm in [('spring_notes','Springs'),('arb_notes','ARB'),
            ('ride_height_notes','Ride Height'),('damper_notes','Dampers')] if getattr(tmpl,a)]
        if susp: sec("🔧 Suspension",susp)
        if tmpl.brake_bias_pct: sec("🛑 Brakes",[("Brake Bias",f"{tmpl.brake_bias_pct}% front")])
        if tmpl.key_adjustments:
            lbl(f,"🎯 Key Adjustments",12,bold=True,color=BLUE).pack(anchor='w',pady=(8,2))
            for adj in tmpl.key_adjustments:
                rw=ctk.CTkFrame(f,fg_color=PANEL,corner_radius=5); rw.pack(fill='x',pady=1)
                lbl(rw,f"•  {adj}",10,color=TEXT,wraplength=660,justify='left',anchor='w').pack(padx=10,pady=5)
        if tmpl.priority_notes:
            pf=ctk.CTkFrame(f,fg_color="#1a3a1a",corner_radius=6); pf.pack(fill='x',pady=6)
            lbl(pf,f"💡 {tmpl.priority_notes}",12,bold=True,color=GREEN,wraplength=660,justify='left').pack(padx=12,pady=8)

    def _apply_tmpl(self):
        if not self.cur_setup: self._demo_setup()
        if self.cur_setup is None:
            return
        cc="gt3" if "GT3" in self._tc2.get() else "formula"
        tmpl=get_setup_template(cc,self._tt.get())
        if tmpl.tire_pressures_psi:
            for co,psi in tmpl.tire_pressures_psi.items(): self.cur_setup.set(f"{co} Cold Pressure",f"{psi} psi")
        if tmpl.camber_deg:
            for co,deg in tmpl.camber_deg.items(): self.cur_setup.set(f"{co} Camber",f"{deg} deg")
        if tmpl.brake_bias_pct: self.cur_setup.set("Brake Bias",f"{tmpl.brake_bias_pct}% front")
        self._render_setup(self.cur_setup); self.tv.set("Setup Files")
        messagebox.showinfo("Applied","Template applied to setup. Review in Setup Files tab and export when ready.")

    # ══════════════════════════════════════════════════════════════════════════
    # HISTORY
    # ══════════════════════════════════════════════════════════════════════════
    def _t_history(self):
        tab=self.tv.tab("History"); tab.configure(fg_color=DARK)
        ctrl=ctk.CTkFrame(tab,fg_color=PANEL,height=46,corner_radius=8)
        ctrl.pack(fill='x',padx=10,pady=(8,4)); ctrl.pack_propagate(False)
        lbl(ctrl,"📚 Setup Change History — track what changed between sessions",13,bold=True).pack(side='left',padx=12)
        ctk.CTkButton(ctrl,text="🗑 Clear",width=80,height=28,fg_color="#6b1a1a",
            hover_color=RED,command=self._clear_hist).pack(side='right',padx=8)
        self._hsc=ctk.CTkScrollableFrame(tab,fg_color="transparent")
        self._hsc.pack(fill='both',expand=True,padx=10,pady=(4,8))
        self._u_history()

    def _u_history(self):
        f=self._hsc
        for w in f.winfo_children(): w.destroy()
        entries=self.history.get_history()
        if not entries:
            lbl(f,"No history yet. Sessions with setup files are tracked here.",color=DIM).pack(pady=30); return
        # Build a lookup: (car_name, track_name) → session index for auto-notes
        _note_lookup: dict[tuple, int] = {}
        for si, (sd, _) in enumerate(self.sessions):
            _note_lookup[(sd.car_name, sd.track_name)] = si

        for entry in entries[:30]:
            ec=ctk.CTkFrame(f,fg_color=PANEL,corner_radius=8); ec.pack(fill='x',pady=3)
            hr=ctk.CTkFrame(ec,fg_color="transparent"); hr.pack(fill='x',padx=10,pady=(8,4))
            lbl(hr,f"{entry.car} @ {entry.track}",12,bold=True).pack(side='left')
            lbl(hr,entry.timestamp[:16].replace('T',' '),10,color=DIM).pack(side='right')
            lbl(hr,f"Best: {format_laptime(entry.best_lap)}",11,color=GREEN).pack(side='right',padx=12)
            if entry.changes_from_prev:
                lbl(ec,f"  {len(entry.changes_from_prev)} change(s) from previous:",10,color=DIM).pack(anchor='w',padx=10)
                for ch in entry.changes_from_prev[:5]:
                    lbl(ec,f"  {ch['param']}: {ch['before']} → {ch['after']}",10,color=YELLOW).pack(anchor='w',padx=20)
                if len(entry.changes_from_prev)>5:
                    lbl(ec,f"  ...and {len(entry.changes_from_prev)-5} more",10,color=DIM).pack(anchor='w',padx=20,pady=(0,6))
            else:
                lbl(ec,"  First session for this car/track.",10,color=DIM).pack(anchor='w',padx=10,pady=(0,6))
            # Show auto-generated session note if available
            note_idx = _note_lookup.get((entry.car, entry.track))
            if note_idx is not None and note_idx in self._session_notes:
                note_text = self._session_notes[note_idx]
                note_frame = ctk.CTkFrame(ec, fg_color="#1a2035", corner_radius=6)
                note_frame.pack(fill='x', padx=10, pady=(0, 8))
                lbl(note_frame, "📝 Session Note", 9, color=BLUE, bold=True).pack(anchor='w', padx=8, pady=(4, 1))
                lbl(note_frame, note_text, 10, color=TEXT, wraplength=680).pack(anchor='w', padx=8, pady=(0, 6))

    def _clear_hist(self):
        entries = self.history.get_history()
        n = len(entries)
        if messagebox.askyesno("Clear History",
                f"This will permanently delete setup history\n"
                f"for all cars and tracks ({n} entries).\n\n"
                f"This cannot be undone. Continue?"):
            self.history.clear(); self._u_history()

    # ══════════════════════════════════════════════════════════════════════════
    # COMPARE
    # ══════════════════════════════════════════════════════════════════════════
    def _t_compare(self):
        tab=self.tv.tab("Compare"); tab.configure(fg_color=DARK)
        ctrl=ctk.CTkFrame(tab,fg_color=PANEL,height=50,corner_radius=8)
        ctrl.pack(fill='x',padx=10,pady=(8,4)); ctrl.pack_propagate(False)
        lbl(ctrl,"A:",color=DIM).pack(side='left',padx=10)
        self._ca=ctk.StringVar()
        self._cam=ctk.CTkOptionMenu(ctrl,variable=self._ca,values=["(none)"],fg_color=CARD,button_color=ACCENT,width=220)
        self._cam.pack(side='left',padx=4)
        lbl(ctrl,"B:",color=DIM).pack(side='left',padx=10)
        self._cb=ctk.StringVar()
        self._cbm=ctk.CTkOptionMenu(ctrl,variable=self._cb,values=["(none)"],fg_color=CARD,button_color=ACCENT,width=220)
        self._cbm.pack(side='left',padx=4)
        self._cmp_ch=ctk.StringVar(value="Speed")
        ctk.CTkOptionMenu(ctrl,values=["Speed","Throttle","Brake","LatAccel","LongAccel","RPM","SteeringWheelAngle"],
            variable=self._cmp_ch,fg_color=CARD,button_color=ACCENT,width=130).pack(side='left',padx=4)
        ctk.CTkButton(ctrl,text="Compare →",fg_color=ACCENT,height=32,command=self._run_cmp).pack(side='left',padx=8)
        ctk.CTkButton(ctrl,text="📊 Export",fg_color=CARD,height=32,hover_color="#1a5a8a",
            command=self._export_cmp_csv).pack(side='left',padx=4)
        self._csc=ctk.CTkScrollableFrame(tab,fg_color="transparent")
        self._csc.pack(fill='both',expand=True,padx=10,pady=(4,8))

    def _find_session_by_label(self, label: str):
        """Return session index matching a compare dropdown label, or None."""
        for i, (d, r) in enumerate(self.sessions):
            if f"#{i+1} {d.car_name} — {format_laptime(r.best_lap)}" == label:
                return i
        return None

    def _run_cmp(self):
        if len(self.sessions)<2: messagebox.showinfo("Need 2","Load at least 2 IBT files."); return
        ai=self._find_session_by_label(self._ca.get()); bi=self._find_session_by_label(self._cb.get())
        if ai is None or bi is None or ai==bi: messagebox.showwarning("Pick 2 Different","Select two different sessions."); return
        da,ra=self.sessions[ai]; db,rb=self.sessions[bi]
        f=self._csc
        for w in f.winfo_children(): w.destroy()
        cols=ctk.CTkFrame(f,fg_color="transparent"); cols.pack(fill='both',expand=True)
        for data,rpt,nm in [(da,ra,"Session A"),(db,rb,"Session B")]:
            col=ctk.CTkFrame(cols,fg_color=PANEL,corner_radius=8); col.pack(side='left',fill='both',expand=True,padx=4,pady=4)
            lbl(col,nm,14,bold=True,color=BLUE).pack(pady=8)
            lbl(col,data.car_name.replace('_',' ').title(),12).pack()
            lbl(col,data.track_name,11,color=DIM).pack()
            lbl(col,f"Best: {format_laptime(rpt.best_lap)}",14,bold=True,color=GREEN).pack(pady=6)
            lbl(col,f"🔴{rpt.critical_count} 🟡{rpt.warning_count} 🔵{rpt.info_count}",11).pack(pady=4)
            for iss in rpt.issues[:6]:
                icon={"critical":"🔴","warning":"🟡","info":"🔵"}[iss.severity.value]
                lbl(col,f"{icon} {iss.title}",10,color=TEXT,wraplength=260).pack(anchor='w',padx=12)
        # Lap time comparison chart
        if ra.lap_times and rb.lap_times:
            ch=EmbedChart(f,figsize=(10,2.5)); ch.pack(fill='x',pady=8)
            ax=ch.std_ax("Lap Time Comparison",xlabel="Lap")
            ax.plot(range(1,len(ra.lap_times)+1),ra.lap_times,'o-',color=BLUE,label="A",lw=1.5)
            ax.plot(range(1,len(rb.lap_times)+1),rb.lap_times,'s-',color=RED,label="B",lw=1.5)
            ax.legend(fontsize=8,facecolor='#1e2845',edgecolor='#2a3050',labelcolor=TEXT)
            ch.fig.tight_layout(pad=0.8); ch.draw()
        # Telemetry overlay: best lap from each session
        self._draw_cmp_overlay(f, da, db, self._cmp_ch.get())

    def _draw_cmp_overlay(self, parent, da, db, ch_name):
        """Overlay best-lap telemetry traces from two sessions."""
        arr_a = da.get_channel(ch_name)
        arr_b = db.get_channel(ch_name)
        dist_a = da.get_channel('LapDistPct')
        dist_b = db.get_channel('LapDistPct')
        if arr_a is None or arr_b is None or dist_a is None or dist_b is None:
            lbl(parent, f"Channel '{ch_name}' not available in one or both sessions.", 11, color=DIM).pack(pady=8)
            return
        def best_lap_slice(data):
            if not data.lap_times or len(data.lap_boundaries) < 2: return None, None
            best_idx = int(np.argmin(data.lap_times))
            if best_idx + 1 >= len(data.lap_boundaries): return None, None
            return data.lap_boundaries[best_idx], data.lap_boundaries[best_idx + 1]
        sa, ea = best_lap_slice(da)
        sb, eb = best_lap_slice(db)
        if sa is None or sb is None: return
        ch = EmbedChart(parent, figsize=(10, 3)); ch.pack(fill='x', pady=8)
        ax = ch.std_ax(f"Best Lap Overlay — {ch_name}")
        step_a = max(1, (ea - sa) // DOWNSAMPLE_LAP)
        step_b = max(1, (eb - sb) // DOWNSAMPLE_LAP)
        ax.plot(dist_a[sa:ea][::step_a] * 100, arr_a[sa:ea][::step_a],
                color=BLUE, lw=1.3, alpha=0.9, label="A best")
        ax.plot(dist_b[sb:eb][::step_b] * 100, arr_b[sb:eb][::step_b],
                color=RED, lw=1.3, alpha=0.9, label="B best")
        ax.set_xlabel("Track Position (%)", color=DIM, fontsize=8)
        ax.set_ylabel(ch_name, color=DIM, fontsize=9)
        ax.legend(fontsize=8, facecolor='#1e2845', edgecolor='#2a3050', labelcolor=TEXT)
        ch.fig.tight_layout(pad=1.0); ch.draw()

    def _export_cmp_csv(self):
        """Export comparison results for both sessions to CSV."""
        if len(self.sessions) < 2:
            messagebox.showinfo("Need 2", "Load at least 2 sessions first.")
            return
        ai = self._find_session_by_label(self._ca.get())
        bi = self._find_session_by_label(self._cb.get())
        if ai is None or bi is None or ai == bi:
            messagebox.showwarning("Error", "Run a comparison first.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv",
            filetypes=[("CSV", "*.csv")], title="Export Comparison CSV")
        if not path:
            return
        da, ra = self.sessions[ai]
        db, rb = self.sessions[bi]
        with open(path, 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(["Session Comparison Export"])
            w.writerow([])
            w.writerow(["Metric", "Session A", "Session B", "Delta"])
            w.writerow(["Car", da.car_name, db.car_name])
            w.writerow(["Track", da.track_name, db.track_name])
            w.writerow(["Best Lap", f"{ra.best_lap:.3f}", f"{rb.best_lap:.3f}",
                         f"{rb.best_lap - ra.best_lap:+.3f}"])
            w.writerow(["Avg Lap", f"{ra.avg_lap:.3f}", f"{rb.avg_lap:.3f}",
                         f"{rb.avg_lap - ra.avg_lap:+.3f}"])
            w.writerow(["Balance Score", f"{ra.balance_score:.1f}", f"{rb.balance_score:.1f}"])
            w.writerow(["Grip %", f"{ra.grip_utilization_pct:.1f}", f"{rb.grip_utilization_pct:.1f}"])
            w.writerow(["Max Lat G", f"{ra.max_lat_g:.2f}", f"{rb.max_lat_g:.2f}"])
            w.writerow(["Max Long G", f"{ra.max_long_g:.2f}", f"{rb.max_long_g:.2f}"])
            w.writerow(["Critical Issues", str(ra.critical_count), str(rb.critical_count)])
            w.writerow(["Warning Issues", str(ra.warning_count), str(rb.warning_count)])
            w.writerow([])
            # Lap times
            max_laps = max(len(ra.lap_times), len(rb.lap_times))
            w.writerow(["Lap", "A Time", "B Time", "Delta"])
            for i in range(max_laps):
                a_t = f"{ra.lap_times[i]:.3f}" if i < len(ra.lap_times) else ""
                b_t = f"{rb.lap_times[i]:.3f}" if i < len(rb.lap_times) else ""
                delta = ""
                if i < len(ra.lap_times) and i < len(rb.lap_times):
                    delta = f"{rb.lap_times[i] - ra.lap_times[i]:+.3f}"
                w.writerow([i + 1, a_t, b_t, delta])
            w.writerow([])
            # Issues
            w.writerow(["Session A Issues"])
            for iss in ra.issues:
                w.writerow([iss.severity.value, iss.title, iss.description])
            w.writerow([])
            w.writerow(["Session B Issues"])
            for iss in rb.issues:
                w.writerow([iss.severity.value, iss.title, iss.description])
        messagebox.showinfo("Exported", f"Comparison saved to:\n{path}")

    # ══════════════════════════════════════════════════════════════════════════
    # ABOUT / HELP
    # ══════════════════════════════════════════════════════════════════════════
    def _about(self):
        win=ctk.CTkToplevel(self); win.title("About"); win.geometry("480x420")
        win.configure(fg_color=DARK); win.grab_set(); win.resizable(False,False)
        win.bind('<Escape>', lambda e: win.destroy())
        lbl(win,f"🏎  {APP_NAME}",20,bold=True).pack(pady=(24,4))
        lbl(win,f"Version {VERSION}",13,color=DIM).pack()
        lbl(win,COPYRIGHT,10,color=DIM).pack(pady=(2,12))
        lbl(win,"Professional telemetry analysis and setup\noptimization for iRacing — powered by AI.",12,
            color=TEXT,justify='center').pack(pady=(0,12))
        ff=ctk.CTkFrame(win,fg_color=PANEL,corner_radius=8); ff.pack(fill='x',padx=24,pady=4)
        for feat in ["12 analysis tabs with real-time charts",
                      "AI-powered coaching via Claude API",
                      "Track map, lap replay, stint comparison",
                      "PDF & CSV export, setup diff & templates",
                      "Secure API key storage via OS keyring"]:
            lbl(ff,f"  ✓  {feat}",10,color=GREEN).pack(anchor='w',padx=12,pady=1)
        lbl(ff,"",4).pack()
        sf=ctk.CTkFrame(win,fg_color=PANEL,corner_radius=8); sf.pack(fill='x',padx=24,pady=8)
        lbl(sf,"Keyboard Shortcuts",11,bold=True,color=BLUE).pack(anchor='w',padx=12,pady=(6,2))
        for k,v in [("Ctrl+O","Open IBT"),("Ctrl+D","Demo"),("Ctrl+E","Export CSV"),
                     ("Ctrl+P","Export PDF"),("Ctrl+B","Batch Load"),("Ctrl+Q","Quit")]:
            row=ctk.CTkFrame(sf,fg_color="transparent"); row.pack(fill='x',padx=12)
            lbl(row,k,9,color=YELLOW).pack(side='left')
            lbl(row,v,9,color=DIM).pack(side='left',padx=8)
        lbl(sf,"",4).pack()
        lr=ctk.CTkFrame(win,fg_color="transparent"); lr.pack(fill='x',padx=24,pady=4)
        ctk.CTkButton(lr,text="📋 View Logs",width=100,height=28,fg_color=CARD,
            hover_color="#1a5a8a",command=self._open_logs).pack(side='left')
        ctk.CTkButton(lr,text="Close",width=80,height=28,fg_color=ACCENT,
            command=win.destroy).pack(side='right')

    def _open_logs(self):
        """Open the log directory in file explorer."""
        import subprocess as _sp
        if sys.platform == 'win32':
            os.startfile(_LOG_DIR)
        elif sys.platform == 'darwin':
            _sp.Popen(['open', _LOG_DIR])
        else:
            _sp.Popen(['xdg-open', _LOG_DIR])

    # ══════════════════════════════════════════════════════════════════════════
    # BATCH / RECENT FILES
    # ══════════════════════════════════════════════════════════════════════════
    def _batch_load(self):
        """Load multiple IBT files at once via a queue (chained one-at-a-time)."""
        init_dir = self.cfg.get('last_dir', '')
        if not init_dir or not os.path.isdir(init_dir):
            for base in [os.path.expanduser('~/Documents'), os.path.expanduser('~/OneDrive/Documents')]:
                candidate = os.path.join(base, 'iRacing', 'telemetry')
                if os.path.isdir(candidate):
                    init_dir = candidate
                    break
        paths = filedialog.askopenfilenames(title="Select IBT Files",initialdir=init_dir,
            filetypes=[("iRacing Telemetry","*.ibt"),("All","*.*")])
        if not paths: return
        self.cfg['last_dir'] = os.path.dirname(paths[0]); save_cfg(self.cfg)
        for p in paths:
            self._add_recent(p)
        self._batch_queue = list(paths)
        self._batch_total = len(paths)
        self._batch_next()

    def _batch_next(self):
        """Process the next file in the batch queue, or finish."""
        if not self._batch_queue:
            self._batch_total = 0
            return
        idx = self._batch_total - len(self._batch_queue) + 1
        self._status_lbl.configure(text=f"⏳ Loading {idx} of {self._batch_total}…")
        # Parallel batch loading
        import concurrent.futures
        paths = self._batch_queue.copy()
        self._batch_queue.clear()
        results = []
        def process_file(p):
            try:
                return IBTParser(p).parse()
            except Exception as e:
                logger.error(f"Batch load failed for {p}: {e}")
                return None
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, len(paths))) as executor:
            for res in executor.map(process_file, paths):
                results.append(res)
        self._status_lbl.configure(text=f"Batch loaded {len(results)} files.")
        # Optionally: store results or trigger further processing

    def _add_recent(self, path: str):
        """Add a file to the recent files list."""
        recent = self.cfg.get('recent_files', [])
        recent = [r for r in recent if r != path]
        recent.insert(0, path)
        self.cfg['recent_files'] = recent[:8]
        save_cfg(self.cfg)

    def _get_recent(self) -> list[str]:
        return self.cfg.get('recent_files', [])

    # ══════════════════════════════════════════════════════════════════════════
    # SETTINGS / PDF
    # ══════════════════════════════════════════════════════════════════════════
    def _settings(self):
        win=ctk.CTkToplevel(self); win.title("Settings"); win.geometry("540x440")
        win.configure(fg_color=DARK); win.grab_set()
        lbl(win,"Settings",16,bold=True).pack(pady=14)
        # API Key
        row=ctk.CTkFrame(win,fg_color="transparent"); row.pack(fill='x',padx=24,pady=4)
        lbl(row,"Anthropic API Key:",color=DIM,width=150).pack(side='left')
        e=ctk.CTkEntry(row,show="•",width=280,fg_color=PANEL)
        e.insert(0,_get_api_key()); e.pack(side='left',padx=8)
        lbl(win,"Get a key at console.anthropic.com  •  Stored securely in OS keyring",10,color=DIM).pack()
        # Export buttons
        pr=ctk.CTkFrame(win,fg_color="transparent"); pr.pack(fill='x',padx=24,pady=10)
        lbl(pr,"Export Report:",color=DIM,width=150).pack(side='left')
        ctk.CTkButton(pr,text="📄 Export PDF Report",height=30,fg_color=CARD,
            hover_color="#1a5a8a",command=lambda:(win.destroy(),self._export_pdf())).pack(side='left',padx=8)
        ctk.CTkButton(pr,text="📊 Export CSV",height=30,fg_color=CARD,
            hover_color="#1a5a8a",command=lambda:(win.destroy(),self._export_csv())).pack(side='left',padx=8)
        # Toggles
        trow = ctk.CTkFrame(win, fg_color="transparent"); trow.pack(fill='x', padx=24, pady=6)
        auto_notes_var = ctk.BooleanVar(value=bool(self.cfg.get('auto_notes', True)))
        ctk.CTkCheckBox(trow, text="Auto-generate session notes after load (requires API key)",
            variable=auto_notes_var, fg_color=ACCENT, hover_color=BLUE).pack(side='left')
        # Recent files
        recent = self._get_recent()
        if recent:
            lbl(win,"Recent Files",12,bold=True,color=BLUE).pack(anchor='w',padx=24,pady=(10,2))
            rf=ctk.CTkScrollableFrame(win,fg_color=PANEL,height=100,corner_radius=8)
            rf.pack(fill='x',padx=24,pady=2)
            for rp in recent:
                btn=ctk.CTkButton(rf,text=os.path.basename(rp),anchor='w',height=24,
                    fg_color="transparent",hover_color="#2a3050",
                    font=ctk.CTkFont(size=10),
                    command=lambda p=rp,w=win:(w.destroy(),self._process(p)))
                btn.pack(fill='x',pady=1)
        # Save / Cancel
        br=ctk.CTkFrame(win,fg_color="transparent"); br.pack(fill='x',padx=24,pady=14)
        def save():
            _set_api_key(e.get().strip())
            self.cfg['auto_notes'] = auto_notes_var.get()
            save_cfg(self.cfg)
            win.destroy()
        ctk.CTkButton(br,text="Save",fg_color=ACCENT,command=save,width=120).pack(side='right',padx=4)
        ctk.CTkButton(br,text="Cancel",fg_color=CARD,command=win.destroy,width=100).pack(side='right',padx=4)
        win.bind('<Return>', lambda e: save())
        win.bind('<Escape>', lambda e: win.destroy())

    def _export_csv(self):
        if not self.cur_data or not self.cur_rpt:
            messagebox.showwarning("No Session","Load a session first."); return
        path=filedialog.asksaveasfilename(title="Export CSV",defaultextension=".csv",
            filetypes=[("CSV","*.csv")],initialfile=f"telemetry_{datetime.now():%Y%m%d_%H%M}.csv")
        if not path: return
        d,r=self.cur_data,self.cur_rpt
        try:
            with open(path,'w',newline='',encoding='utf-8') as f:
                w=csv.writer(f)
                # Header info
                w.writerow(["iRacing Setup Advisor — Telemetry Export"])
                w.writerow(["Car",d.car_name,"Track",d.track_name,"Laps",d.num_laps])
                w.writerow(["Best Lap",format_laptime(r.best_lap),"Avg Lap",format_laptime(r.avg_lap)])
                w.writerow([])
                # Lap times
                w.writerow(["Lap","Time (s)","Formatted","Delta to Best","Fuel Corrected","Outlier"])
                fc=getattr(self.cur_best,'fuel_corrected',None) or []
                mask=r.valid_lap_mask if r.valid_lap_mask else [True]*len(r.lap_times)
                for i,t in enumerate(r.lap_times):
                    delta=t-r.best_lap
                    fc_val=format_laptime(fc[i]) if i<len(fc) else ""
                    outlier="Yes" if i<len(mask) and not mask[i] else ""
                    w.writerow([i+1,f"{t:.4f}",format_laptime(t),f"+{delta:.3f}" if delta>0 else "BEST",fc_val,outlier])
                w.writerow([])
                # Issues
                w.writerow(["Severity","Category","Issue","Detail"])
                for iss in r.issues:
                    w.writerow([iss.severity.value,iss.category.value,iss.title,iss.description])
                w.writerow([])
                # Tire summary
                if r.tire_summary:
                    w.writerow(["Corner","Inner","Mid","Outer","Avg"])
                    for corner in ['LF','RF','LR','RR']:
                        ts=r.tire_summary.get(corner,{})
                        if ts: w.writerow([corner,f"{ts.get('inner',0):.1f}",f"{ts.get('mid',0):.1f}",
                                           f"{ts.get('outer',0):.1f}",f"{ts.get('avg',0):.1f}"])
            messagebox.showinfo("CSV Exported",f"Saved to:\n{path}")
        except Exception as ex:
            logger.exception("CSV export failed")
            messagebox.showerror("CSV Error","Failed to export CSV.")

    def _export_pdf(self):
        if not self.cur_data: messagebox.showwarning("No Session","Load a session first."); return
        path=filedialog.asksaveasfilename(title="Export PDF",defaultextension=".pdf",
            filetypes=[("PDF","*.pdf")],initialfile=f"setup_report_{datetime.now():%Y%m%d_%H%M}.pdf")
        if not path: return
        self._status_lbl.configure(text="⏳ Generating PDF…")
        self._progress.pack(side='left',padx=8); self._progress.start()
        def worker():
            try:
                from core.pdf_report import generate_pdf_report
                # Gather optional enrichment data
                cs = self._compute_consistency_score()
                ml_res = (self._ml_predictor.predict(self._ml_features[-1])
                          if self._ml_predictor.is_trained and self._ml_features
                          else None)
                sess_idx = len(self.sessions) - 1
                note = self._session_notes.get(sess_idx, "")
                generate_pdf_report(
                    output_path=path, data=self.cur_data, report=self.cur_rpt,
                    sector_report=self.cur_sec, best_report=self.cur_best,
                    tire_deg=self.cur_stint, driver_report=self.cur_style,
                    ai_text=self._ai_last_text,
                    consistency=cs, ml_result=ml_res, session_note=note)
                self.after(0,lambda:(self._progress.stop(),self._progress.pack_forget(),
                    self._status_lbl.configure(text=""),
                    messagebox.showinfo("PDF Exported",f"Saved to:\n{path}")))
            except Exception as ex:
                logger.exception("PDF export failed")
                self.after(0,lambda:(self._progress.stop(),self._progress.pack_forget(),
                    self._status_lbl.configure(text=""),
                    messagebox.showerror("PDF Error","Failed to generate PDF report.")))
        threading.Thread(target=worker,daemon=True).start()

    # ══════════════════════════════════════════════════════════════════════════
    # BRAKE TRACE TAB
    # ══════════════════════════════════════════════════════════════════════════
    def _t_brake_trace(self):
        tab = self.tv.tab("Brake Trace"); tab.configure(fg_color=DARK)
        self._ph_brake = lbl(tab, "Load a session to see brake trace analysis.", 14, color=DIM)
        self._ph_brake.pack(pady=40)
        self._brake_sc = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        self._brake_sc.pack(fill='both', expand=True, padx=10, pady=8)
        self._brake_chart = EmbedChart(self._brake_sc, figsize=(10, 3.5))
        self._brake_chart.pack(fill='x', pady=(0, 4))
        self._brake_cards = ctk.CTkFrame(self._brake_sc, fg_color="transparent")
        self._brake_cards.pack(fill='x')

    def _u_brake_trace(self):
        d = self.cur_data
        if not d or d.num_laps < 1:
            return
        try: self._ph_brake.pack_forget()
        except Exception: pass
        report = analyze_braking(d)
        if not report:
            return
        # Draw brake pressure chart for first corner
        c = self._brake_chart; c.clear()
        ax = c.std_ax("Brake Pressure Profiles", xlabel="Track %")
        ax.set_ylabel("Brake", color=DIM, fontsize=8)
        palette = [ACCENT, BLUE, GREEN, YELLOW, PURPLE, RED]
        for i, p in enumerate(report.profiles[:6]):
            col = palette[i % len(palette)]
            # Draw average brake trace in zone
            ld = d.get_channel('LapDistPct')
            brk = d.get_channel('Brake')
            if ld is not None and brk is not None:
                s0 = d.lap_boundaries[0]; e0 = d.lap_boundaries[1]
                mask = (ld[s0:e0] >= p.brake_start_pct) & (ld[s0:e0] <= p.apex_pct + 0.05)
                if np.sum(mask) > 0:
                    ax.plot(ld[s0:e0][mask] * 100, brk[s0:e0][mask], color=col,
                            lw=1.5, alpha=0.8, label=f"Corner {p.corner_num}")
        ax.legend(fontsize=7, facecolor='#1e2845', edgecolor='#2a3050', labelcolor=TEXT)
        c.fig.tight_layout(pad=0.8); c.draw()
        # Profile cards
        for w in self._brake_cards.winfo_children(): w.destroy()
        sec_lbl(self._brake_cards, f"🛑 Brake Analysis — {len(report.profiles)} zones | "
                f"Overall modulation: {report.overall_modulation_score:.0f}/100")
        for p in report.profiles:
            cf = ctk.CTkFrame(self._brake_cards, fg_color="#1e2845", corner_radius=8)
            cf.pack(fill='x', pady=4)
            hdr = ctk.CTkFrame(cf, fg_color="transparent"); hdr.pack(fill='x', padx=12, pady=(8, 4))
            is_worst = p.corner_num == report.weakest_corner
            lbl(hdr, f"{'🔴' if is_worst else '🟢'} Corner {p.corner_num}" +
                (" ← WEAKEST" if is_worst else ""), 13, bold=True,
                color=RED if is_worst else TEXT).pack(side='left')
            mr = ctk.CTkFrame(cf, fg_color="transparent"); mr.pack(fill='x', padx=8, pady=4)
            stat_blk(mr, "Initial Bite", f"{p.initial_bite:.0%}", BLUE)
            stat_blk(mr, "Peak", f"{p.peak_pressure:.0%}", RED)
            stat_blk(mr, "Modulation", f"{p.modulation_score:.0f}/100",
                     GREEN if p.modulation_score > 70 else YELLOW)
            stat_blk(mr, "Trail Brake", f"{p.trail_brake_pct:.0f}%",
                     GREEN if p.trail_brake_pct > 30 else DIM)
            stat_blk(mr, "Duration", f"{p.avg_brake_duration_s:.2f}s")
            if p.coaching_note:
                nf = ctk.CTkFrame(cf, fg_color="#0d1b2a", corner_radius=6)
                nf.pack(fill='x', padx=12, pady=(4, 8))
                lbl(nf, p.coaching_note, 10, color=TEXT, wraplength=800,
                    justify='left', anchor='w').pack(fill='x', padx=8, pady=6)
        if report.findings:
            sec_lbl(self._brake_cards, "📋 Findings")
            for fn in report.findings:
                ff = ctk.CTkFrame(self._brake_cards, fg_color="#1e2845", corner_radius=6)
                ff.pack(fill='x', pady=2)
                lbl(ff, f"•  {fn}", 11, color=TEXT, wraplength=820,
                    justify='left', anchor='w').pack(padx=12, pady=6)

    # ══════════════════════════════════════════════════════════════════════════
    # STRATEGY TAB
    # ══════════════════════════════════════════════════════════════════════════
    def _t_strategy(self):
        tab = self.tv.tab("Strategy"); tab.configure(fg_color=DARK)
        self._ph_strat = lbl(tab, "Enter race details to calculate pit strategy.", 14, color=DIM)
        self._ph_strat.pack(pady=20)
        ctrl = ctk.CTkFrame(tab, fg_color=PANEL, corner_radius=8)
        ctrl.pack(fill='x', padx=10, pady=4)
        lbl(ctrl, "Race Laps:", color=DIM).pack(side='left', padx=(10, 4))
        self._strat_laps = ctk.CTkEntry(ctrl, width=60, fg_color=CARD); self._strat_laps.pack(side='left', padx=4)
        self._strat_laps.insert(0, "30")
        lbl(ctrl, "Base Lap (s):", color=DIM).pack(side='left', padx=(10, 4))
        self._strat_base = ctk.CTkEntry(ctrl, width=70, fg_color=CARD); self._strat_base.pack(side='left', padx=4)
        lbl(ctrl, "Fuel/Lap (L):", color=DIM).pack(side='left', padx=(10, 4))
        self._strat_fpl = ctk.CTkEntry(ctrl, width=60, fg_color=CARD); self._strat_fpl.pack(side='left', padx=4)
        lbl(ctrl, "Tank (L):", color=DIM).pack(side='left', padx=(10, 4))
        self._strat_tank = ctk.CTkEntry(ctrl, width=60, fg_color=CARD); self._strat_tank.pack(side='left', padx=4)
        ctk.CTkButton(ctrl, text="Calculate", width=100, fg_color=ACCENT,
                       hover_color="#c0392b", command=self._calc_strategy).pack(side='left', padx=8)
        self._strat_sc = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        self._strat_sc.pack(fill='both', expand=True, padx=10, pady=4)
        self._strat_chart = EmbedChart(self._strat_sc, figsize=(10, 3))
        self._strat_chart.pack(fill='x', pady=(0, 4))
        self._strat_cards = ctk.CTkFrame(self._strat_sc, fg_color="transparent")
        self._strat_cards.pack(fill='x')

    def _calc_strategy(self):
        try:
            race_laps = int(self._strat_laps.get())
            base_text = self._strat_base.get().strip()
            fpl_text = self._strat_fpl.get().strip()
            tank_text = self._strat_tank.get().strip()
        except ValueError:
            messagebox.showwarning("Invalid Input", "Enter valid numbers.")
            return
        # Auto-fill from session if fields empty
        base = float(base_text) if base_text else (self.cur_rpt.best_lap if self.cur_rpt else 90.0)
        if not fpl_text and self.cur_fuel:
            fpl = self.cur_fuel.fuel_per_lap_l
        else:
            fpl = float(fpl_text) if fpl_text else 3.5
        if not tank_text and self.cur_data:
            tank = self.cur_data.session_info.get('fuel_capacity_l', 120)
        else:
            tank = float(tank_text) if tank_text else 120
        deg = 0.03
        cliff = 30
        if self.cur_stint and self.cur_stint.deg_rate > 0:
            deg = self.cur_stint.deg_rate
            cliff = self.cur_stint.cliff_lap
        report = calculate_strategy(race_laps, fpl, tank, base, deg, cliff)
        self._render_strategy(report)

    def _render_strategy(self, report: StrategyReport):
        try: self._ph_strat.pack_forget()
        except Exception: pass
        # Chart: lap time prediction across stints
        c = self._strat_chart; c.clear()
        ax = c.std_ax("Predicted Lap Times by Stint", xlabel="Lap")
        stint_colors = [BLUE, GREEN, YELLOW, PURPLE, RED, ACCENT]
        for si, stint in enumerate(report.stints):
            col = stint_colors[si % len(stint_colors)]
            laps = list(range(stint.start_lap, stint.end_lap + 1))
            avg = [stint.expected_avg_lap] * len(laps)
            ax.fill_between(laps, [stint.expected_avg_lap - 0.2] * len(laps),
                            [stint.expected_avg_lap + 0.2] * len(laps), color=col, alpha=0.2)
            ax.plot(laps, avg, color=col, lw=2, label=f"Stint {si+1}")
        for stop in report.pit_stops:
            ax.axvline(stop.lap, color=RED, ls='--', lw=1, alpha=0.6)
        ax.set_ylabel("Lap time (s)", color=DIM, fontsize=8)
        ax.legend(fontsize=7, facecolor='#1e2845', edgecolor='#2a3050', labelcolor=TEXT)
        c.fig.tight_layout(pad=0.8); c.draw()
        # Summary cards
        for w in self._strat_cards.winfo_children(): w.destroy()
        sf = ctk.CTkFrame(self._strat_cards, fg_color=PANEL, corner_radius=8); sf.pack(fill='x', pady=4)
        sr = ctk.CTkFrame(sf, fg_color="transparent"); sr.pack(fill='x', padx=12, pady=10)
        stat_blk(sr, "Stops", str(report.num_stops), ACCENT)
        stat_blk(sr, "Race Time", f"{report.race_time_min:.1f} min", BLUE)
        stat_blk(sr, "Total Fuel", f"{report.total_fuel_needed_l:.0f} L", YELLOW)
        stat_blk(sr, "Stints", str(len(report.stints)), GREEN)
        for si, stint in enumerate(report.stints):
            sf2 = ctk.CTkFrame(self._strat_cards, fg_color="#1e2845", corner_radius=8); sf2.pack(fill='x', pady=2)
            mr = ctk.CTkFrame(sf2, fg_color="transparent"); mr.pack(fill='x', padx=8, pady=6)
            lbl(mr, f"Stint {si+1}: Laps {stint.start_lap}–{stint.end_lap}", 12,
                bold=True, color=stint_colors[si % len(stint_colors)]).pack(side='left', padx=8)
            stat_blk(mr, "Laps", str(stint.num_laps))
            stat_blk(mr, "Fuel Start", f"{stint.fuel_start_l:.0f}L", BLUE)
            stat_blk(mr, "Avg Lap", f"{stint.expected_avg_lap:.2f}s", GREEN)
        if report.findings:
            sec_lbl(self._strat_cards, "📋 Strategy Notes")
            for fn in report.findings:
                ff = ctk.CTkFrame(self._strat_cards, fg_color="#1e2845", corner_radius=6); ff.pack(fill='x', pady=2)
                lbl(ff, f"•  {fn}", 11, color=TEXT, wraplength=820,
                    justify='left', anchor='w').pack(padx=12, pady=6)

    # ══════════════════════════════════════════════════════════════════════════
    # TRENDS TAB (Multi-Session Aggregation)
    # ══════════════════════════════════════════════════════════════════════════
    def _t_trends(self):
        tab = self.tv.tab("Trends"); tab.configure(fg_color=DARK)
        self._ph_trends = lbl(tab, "Load at least 2 sessions to see trends.", 14, color=DIM)
        self._ph_trends.pack(pady=40)
        self._trends_sc = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        self._trends_sc.pack(fill='both', expand=True, padx=10, pady=8)
        self._trends_chart = EmbedChart(self._trends_sc, figsize=(10, 3.5))
        self._trends_chart.pack(fill='x', pady=(0, 4))
        self._balance_trends_chart = EmbedChart(self._trends_sc, figsize=(10, 2.2))
        self._balance_trends_chart.pack(fill='x', pady=(0, 4))
        self._trends_cards = ctk.CTkFrame(self._trends_sc, fg_color="transparent")
        self._trends_cards.pack(fill='x')

    def _u_trends(self):
        if len(self.sessions) < 2:
            return
        try: self._ph_trends.pack_forget()
        except Exception: pass
        report = aggregate_sessions(self.sessions)
        if not report:
            return
        # Best lap trend chart
        c = self._trends_chart; c.clear()
        ax = c.std_ax("Session Trends", xlabel="Session #")
        x = list(range(1, report.num_sessions + 1))
        ax.plot(x, report.best_lap_trend, 'o-', color=GREEN, lw=2, label='Best Lap')
        ax.plot(x, report.avg_lap_trend, 's--', color=BLUE, lw=1.5, alpha=0.7, label='Avg Lap')
        ax.set_ylabel("Lap time (s)", color=DIM, fontsize=8)
        ax2 = ax.twinx()
        ax2.bar(x, report.consistency_trend, alpha=0.15, color=YELLOW, label='Consistency %')
        ax2.set_ylabel("Consistency (lower = better)", color=DIM, fontsize=8)
        ax2.tick_params(colors=DIM)
        ax.legend(fontsize=7, facecolor='#1e2845', edgecolor='#2a3050', labelcolor=TEXT, loc='upper left')
        c.fig.tight_layout(pad=0.8); c.draw()
        # Summary
        for w in self._trends_cards.winfo_children(): w.destroy()
        sf = ctk.CTkFrame(self._trends_cards, fg_color=PANEL, corner_radius=8); sf.pack(fill='x', pady=4)
        sr = ctk.CTkFrame(sf, fg_color="transparent"); sr.pack(fill='x', padx=12, pady=10)
        stat_blk(sr, "Sessions", str(report.num_sessions), BLUE)
        imp_col = GREEN if report.improving else RED
        stat_blk(sr, "Improvement", f"{report.total_improvement:+.3f}s", imp_col)
        stat_blk(sr, "Per Session", f"{report.improvement_per_session:+.3f}s", imp_col)
        best_s = min(report.summaries, key=lambda s: s.best_lap)
        stat_blk(sr, "Best Ever", f"{best_s.best_lap:.3f}s", GREEN)
        for s in report.summaries:
            sf2 = ctk.CTkFrame(self._trends_cards, fg_color="#1e2845", corner_radius=8); sf2.pack(fill='x', pady=2)
            mr = ctk.CTkFrame(sf2, fg_color="transparent"); mr.pack(fill='x', padx=8, pady=6)
            lbl(mr, f"S{s.index+1}: {s.car_name[:20]} @ {s.track_name[:20]}", 11,
                bold=True).pack(side='left', padx=8)
            stat_blk(mr, "Best", f"{s.best_lap:.3f}s", GREEN)
            stat_blk(mr, "Avg", f"{s.avg_lap:.3f}s")
            stat_blk(mr, "Laps", str(s.num_laps))
        if report.findings:
            sec_lbl(self._trends_cards, "📋 Trend Insights")
            for fn in report.findings:
                ff = ctk.CTkFrame(self._trends_cards, fg_color="#1e2845", corner_radius=6); ff.pack(fill='x', pady=2)
                lbl(ff, f"•  {fn}", 11, color=TEXT, wraplength=820,
                    justify='left', anchor='w').pack(padx=12, pady=6)

        # Balance trend per session
        balance_vals = [r.balance_score for _, r in self.sessions]
        entry_vals   = [r.balance_entry  for _, r in self.sessions]
        mid_vals     = [r.balance_mid    for _, r in self.sessions]
        exit_vals    = [r.balance_exit   for _, r in self.sessions]
        if len(balance_vals) >= 2:
            bc = self._balance_trends_chart; bc.clear()
            ax = bc.fig.add_subplot(111, facecolor=PANEL)
            sx = list(range(1, len(balance_vals) + 1))
            ax.plot(sx, balance_vals, 'o-', color=TEXT,  lw=2,   label='Overall',  zorder=4)
            ax.plot(sx, entry_vals,   's--', color=RED,   lw=1.5, label='Entry',    alpha=0.8)
            ax.plot(sx, mid_vals,     '^--', color=BLUE,  lw=1.5, label='Mid',      alpha=0.8)
            ax.plot(sx, exit_vals,    'D--', color=GREEN, lw=1.5, label='Exit',     alpha=0.8)
            ax.axhline(0, color=DIM, lw=0.8, ls=':')
            ax.axhspan(-0.05, 0.05, color=BLUE, alpha=0.07)
            ax.set_ylim(-1.1, 1.1)
            ax.set_ylabel("← US   OS →", color=DIM, fontsize=7)
            ax.set_xlabel("Session #", color=DIM, fontsize=8)
            ax.tick_params(colors=DIM, labelsize=7)
            for spine in ax.spines.values(): spine.set_edgecolor('#2a3050')
            ax.set_title("Balance Trend — Overall / Entry / Mid / Exit", color=TEXT, fontsize=9, pad=3)
            ax.legend(fontsize=7, facecolor='#1e2845', edgecolor='#2a3050', labelcolor=TEXT)
            ax.set_facecolor(PANEL); bc.fig.patch.set_facecolor(PANEL)
            bc.fig.tight_layout(pad=0.6); bc.draw()

    # ══════════════════════════════════════════════════════════════════════════
    # IMPACT TAB (Setup Change Impact Predictor)
    # ══════════════════════════════════════════════════════════════════════════
    # ══════════════════════════════════════════════════════════════════════════
    # IMPACT TAB  (3 modes: Predict · Sensitivity Matrix · Optimizer)
    # ══════════════════════════════════════════════════════════════════════════
    def _t_impact(self):
        tab = self.tv.tab("Impact"); tab.configure(fg_color=DARK)

        # Mode selector
        mode_bar = ctk.CTkFrame(tab, fg_color=PANEL, height=44, corner_radius=8)
        mode_bar.pack(fill='x', padx=10, pady=(8, 4)); mode_bar.pack_propagate(False)
        lbl(mode_bar, "Setup Intelligence:", 12, bold=True).pack(side='left', padx=12)
        self._impact_mode = ctk.StringVar(value="Predict")
        ctk.CTkSegmentedButton(
            mode_bar,
            values=["Predict", "Sensitivity Matrix", "Optimizer"],
            variable=self._impact_mode,
            fg_color=CARD, selected_color=ACCENT, selected_hover_color="#c0392b",
            command=self._switch_impact_mode,
        ).pack(side='left', padx=8)

        # ── Pane container ────────────────────────────────────────────────────
        self._impact_pane = ctk.CTkFrame(tab, fg_color="transparent")
        self._impact_pane.pack(fill='both', expand=True)

        # Build all three panes (only one visible at a time)
        self._build_impact_predict_pane()
        self._build_impact_heatmap_pane()
        self._build_impact_optimizer_pane()

        # Show default pane
        self._switch_impact_mode("Predict")

    def _switch_impact_mode(self, mode: str):
        self._impact_predict_frame.pack_forget()
        self._impact_heatmap_frame.pack_forget()
        self._impact_opt_frame.pack_forget()
        if mode == "Predict":
            self._impact_predict_frame.pack(fill='both', expand=True)
        elif mode == "Sensitivity Matrix":
            self._impact_heatmap_frame.pack(fill='both', expand=True)
            self._draw_sensitivity_matrix()
        else:
            self._impact_opt_frame.pack(fill='both', expand=True)

    # ── Predict pane (original functionality) ────────────────────────────────
    def _build_impact_predict_pane(self):
        f = ctk.CTkFrame(self._impact_pane, fg_color="transparent")
        self._impact_predict_frame = f
        lbl(f, "Predict effect of specific setup changes on lap time, balance, and tire wear.",
            11, color=DIM).pack(anchor='w', padx=12, pady=(6, 4))
        ctrl = ctk.CTkFrame(f, fg_color=PANEL, corner_radius=8); ctrl.pack(fill='x', padx=10, pady=4)
        self._impact_rows: list[tuple] = []
        params = get_available_parameters()
        for i in range(3):
            row = ctk.CTkFrame(ctrl, fg_color="transparent"); row.pack(fill='x', padx=8, pady=3)
            pvar = ctk.StringVar(value=params[i] if i < len(params) else params[0])
            ctk.CTkOptionMenu(row, values=params, variable=pvar, fg_color=CARD,
                              button_color=ACCENT, width=160).pack(side='left', padx=4)
            lbl(row, "Delta:", color=DIM).pack(side='left', padx=(8, 4))
            dentry = ctk.CTkEntry(row, width=60, fg_color=CARD); dentry.pack(side='left', padx=4)
            dentry.insert(0, "1" if i == 0 else "0")
            self._impact_rows.append((pvar, dentry))
        ctk.CTkButton(ctrl, text="Predict Impact", width=130, fg_color=ACCENT,
                      hover_color="#c0392b", command=self._run_impact).pack(padx=8, pady=8)
        sc = ctk.CTkScrollableFrame(f, fg_color="transparent")
        sc.pack(fill='both', expand=True, padx=10, pady=4)
        self._impact_cards = ctk.CTkFrame(sc, fg_color="transparent")
        self._impact_cards.pack(fill='x')

    def _run_impact(self):
        changes = []
        for pvar, dentry in self._impact_rows:
            try:
                delta = float(dentry.get())
            except ValueError:
                continue
            if delta != 0:
                changes.append({'parameter': pvar.get(), 'delta': delta})
        if not changes:
            messagebox.showwarning("No Changes", "Enter at least one non-zero delta.")
            return
        report = predict_impact(changes)
        for w in self._impact_cards.winfo_children(): w.destroy()
        sf = ctk.CTkFrame(self._impact_cards, fg_color=PANEL, corner_radius=8); sf.pack(fill='x', pady=4)
        sr = ctk.CTkFrame(sf, fg_color="transparent"); sr.pack(fill='x', padx=12, pady=10)
        net_col = GREEN if report.net_lap_time_delta_s < 0 else RED if report.net_lap_time_delta_s > 0 else DIM
        stat_blk(sr, "Net Lap Delta", f"{report.net_lap_time_delta_s:+.3f}s", net_col)
        stat_blk(sr, "Balance", report.net_balance_shift.title(), YELLOW)
        lbl(sf, report.summary, 11, color=TEXT, wraplength=800).pack(padx=12, pady=(0, 8))
        for p in report.predictions:
            cf = ctk.CTkFrame(self._impact_cards, fg_color="#1e2845", corner_radius=8); cf.pack(fill='x', pady=3)
            hdr = ctk.CTkFrame(cf, fg_color="transparent"); hdr.pack(fill='x', padx=12, pady=(8, 4))
            lbl(hdr, p.change_description, 13, bold=True).pack(side='left')
            lbl(hdr, f"Confidence: {p.confidence:.0%}", 10, color=DIM).pack(side='right')
            mr = ctk.CTkFrame(cf, fg_color="transparent"); mr.pack(fill='x', padx=8, pady=4)
            lt_col = GREEN if p.lap_time_delta_s < 0 else RED
            stat_blk(mr, "Lap Time", f"{p.lap_time_delta_s:+.3f}s", lt_col)
            stat_blk(mr, "Straight", f"{p.straight_speed_delta_kmh:+.1f} km/h", BLUE)
            stat_blk(mr, "Corner", f"{p.corner_speed_delta_kmh:+.1f} km/h", YELLOW)
            stat_blk(mr, "Balance", p.balance_shift.title(), PURPLE)
            stat_blk(mr, "Tire Wear", p.tire_wear_impact.title())
            nf = ctk.CTkFrame(cf, fg_color="#0d1b2a", corner_radius=6); nf.pack(fill='x', padx=12, pady=(4, 8))
            lbl(nf, p.explanation, 10, color=TEXT, wraplength=800,
                justify='left', anchor='w').pack(fill='x', padx=8, pady=6)

    # ── Sensitivity Matrix pane ───────────────────────────────────────────────
    def _build_impact_heatmap_pane(self):
        f = ctk.CTkFrame(self._impact_pane, fg_color="transparent")
        self._impact_heatmap_frame = f
        lbl(f, "Sensitivity of each parameter to a +1 unit change across all metrics.",
            11, color=DIM).pack(anchor='w', padx=12, pady=(6, 4))
        self._impact_heatmap_chart = EmbedChart(f, figsize=(10, 5))
        self._impact_heatmap_chart.pack(fill='both', expand=True, padx=10, pady=(0, 8))
        self._heatmap_drawn = False

    def _draw_sensitivity_matrix(self):
        if self._heatmap_drawn:
            return  # only draw once; static data doesn't change
        param_labels, metric_labels, matrix, norm = compute_sensitivity_matrix()
        c = self._impact_heatmap_chart
        c.clear()
        fig = c.fig
        ax = fig.add_subplot(111)
        ax.set_facecolor('#0d1b2a')
        fig.patch.set_facecolor('#0d1b2a')

        n_p, n_m = norm.shape

        # Draw each cell manually so we can use per-column coloring logic
        # Column colour rules:
        #   0 Lap Time     : red = high cost (bad), green = low cost
        #   1 Corner Speed : green = positive, red = negative
        #   2 Straight Spd : green = positive, red = negative
        #   3 Balance      : orange = oversteer (+), blue = understeer (-)
        #   4 Tire Wear    : red = increased (+1), green = decreased (-1)
        #   5 Confidence   : green = high

        _CMAPS = [
            plt.cm.RdYlGn_r,   # Lap Time: red=high cost
            plt.cm.RdYlGn,     # Corner Speed: green=good
            plt.cm.RdYlGn,     # Straight Speed
            plt.cm.RdYlBu_r,   # Balance: orange=OS, blue=US
            plt.cm.RdYlGn_r,   # Tire Wear: red=more wear
            plt.cm.RdYlGn,     # Confidence: green=high
        ]

        _BAL_LABELS = {1.0: 'OS', -1.0: 'US', 0.0: '—'}
        _WEAR_LABELS = {1.0: '+wear', 0.0: 'min', -1.0: '-wear'}

        for j in range(n_m):
            cmap = _CMAPS[j]
            for i in range(n_p):
                v = norm[i, j]  # -1 to 1
                raw = matrix[i, j]
                rgba = cmap((v + 1.0) / 2.0)
                rect = plt.Rectangle([j - 0.5, i - 0.5], 1, 1, color=rgba, zorder=1)
                ax.add_patch(rect)

                # Cell annotation
                if j == 3:
                    txt = _BAL_LABELS.get(raw, f'{raw:+.1f}')
                elif j == 4:
                    txt = _WEAR_LABELS.get(raw, f'{raw:+.1f}')
                elif j == 5:
                    txt = f'{raw:.0%}'
                elif j == 0:
                    txt = f'{raw:+.3f}s'
                else:
                    txt = f'{raw:+.1f}'

                brightness = 0.299 * rgba[0] + 0.587 * rgba[1] + 0.114 * rgba[2]
                txt_color = '#0d1b2a' if brightness > 0.55 else 'white'
                ax.text(j, i, txt, ha='center', va='center', fontsize=8,
                        color=txt_color, zorder=2)

        ax.set_xlim(-0.5, n_m - 0.5)
        ax.set_ylim(-0.5, n_p - 0.5)
        ax.set_xticks(range(n_m))
        ax.set_xticklabels(metric_labels, color=TEXT, fontsize=9)
        ax.set_yticks(range(n_p))
        ax.set_yticklabels(param_labels, color=TEXT, fontsize=9)
        ax.tick_params(length=0)
        ax.xaxis.tick_top()
        for sp in ax.spines.values():
            sp.set_visible(False)
        ax.set_title("Setup Sensitivity Matrix  (per +1 unit change)",
                     color=TEXT, fontsize=11, pad=14)

        # Divider lines between columns and rows
        for j in range(1, n_m):
            ax.axvline(j - 0.5, color='#0d1b2a', lw=1.5, zorder=3)
        for i in range(1, n_p):
            ax.axhline(i - 0.5, color='#0d1b2a', lw=0.8, zorder=3)

        fig.tight_layout(pad=0.5)
        c.draw()
        self._heatmap_drawn = True

    # ── Optimizer pane ────────────────────────────────────────────────────────
    def _build_impact_optimizer_pane(self):
        f = ctk.CTkFrame(self._impact_pane, fg_color="transparent")
        self._impact_opt_frame = f
        lbl(f, "Genetic Algorithm Setup Optimizer — finds the best combination of changes for your target.",
            11, color=DIM).pack(anchor='w', padx=12, pady=(6, 4))

        ctrl = ctk.CTkFrame(f, fg_color=PANEL, corner_radius=8); ctrl.pack(fill='x', padx=10, pady=4)

        row1 = ctk.CTkFrame(ctrl, fg_color="transparent"); row1.pack(fill='x', padx=8, pady=(8, 4))
        lbl(row1, "Target:", color=DIM).pack(side='left', padx=(0, 6))
        self._opt_target = ctk.StringVar(value="Balance + Lap Time")
        ctk.CTkOptionMenu(row1,
            values=["Balance + Lap Time", "Fix Understeer", "Fix Oversteer", "Minimize Lap Time"],
            variable=self._opt_target,
            fg_color=CARD, button_color=ACCENT, width=200).pack(side='left', padx=4)

        lbl(row1, "Max ± clicks:", color=DIM).pack(side='left', padx=(16, 4))
        self._opt_maxd = ctk.CTkEntry(row1, width=50, fg_color=CARD); self._opt_maxd.pack(side='left')
        self._opt_maxd.insert(0, "3")

        lbl(row1, "Generations:", color=DIM).pack(side='left', padx=(16, 4))
        self._opt_gens = ctk.CTkEntry(row1, width=50, fg_color=CARD); self._opt_gens.pack(side='left')
        self._opt_gens.insert(0, "60")

        row2 = ctk.CTkFrame(ctrl, fg_color="transparent"); row2.pack(fill='x', padx=8, pady=(0, 8))
        self._opt_btn = ctk.CTkButton(row2, text="Run Optimizer", width=140, fg_color=ACCENT,
                                      hover_color="#c0392b", command=self._run_optimizer)
        self._opt_btn.pack(side='left', padx=(0, 12))
        self._opt_status = lbl(row2, "Load a session, then run the optimizer.", 11, color=DIM)
        self._opt_status.pack(side='left')

        sc = ctk.CTkScrollableFrame(f, fg_color="transparent")
        sc.pack(fill='both', expand=True, padx=10, pady=4)
        self._opt_cards = ctk.CTkFrame(sc, fg_color="transparent")
        self._opt_cards.pack(fill='x')

    def _run_optimizer(self):
        balance = self.cur_rpt.balance_score if self.cur_rpt else 0.0
        issues = [i.title for i in self.cur_rpt.issues] if self.cur_rpt else []

        mode_map = {
            "Balance + Lap Time": "balance_and_time",
            "Fix Understeer": "fix_balance",
            "Fix Oversteer": "fix_balance",
            "Minimize Lap Time": "lap_time",
        }
        mode = mode_map.get(self._opt_target.get(), "balance_and_time")

        # For explicit fix targets, set a hard target balance
        target_bal = 0.0
        if self._opt_target.get() == "Fix Understeer":
            target_bal = 0.1   # slightly toward oversteer to correct
        elif self._opt_target.get() == "Fix Oversteer":
            target_bal = -0.1

        try:
            max_d = float(self._opt_maxd.get())
            gens = int(self._opt_gens.get())
        except ValueError:
            messagebox.showwarning("Invalid Input", "Max clicks and Generations must be numbers.")
            return

        target = OptimizationTarget(
            mode=mode,
            target_balance=target_bal,
            balance_weight=2.5 if mode == "fix_balance" else 1.5,
            max_delta_per_param=max(0.5, min(max_d, 5.0)),
        )

        self._opt_btn.configure(state='disabled', text="Optimizing…")
        self._opt_status.configure(text=f"⏳ Running {gens} generations…")
        for w in self._opt_cards.winfo_children(): w.destroy()

        def worker():
            result = optimize_setup(
                current_balance=balance,
                current_issues=issues,
                target=target,
                n_generations=gens,
                pop_size=80,
            )
            self.after(0, lambda r=result: self._show_optimizer_result(r, balance))

        threading.Thread(target=worker, daemon=True).start()

    def _show_optimizer_result(self, result: OptimizationResult, orig_balance: float):
        self._last_opt_result = result
        self._opt_btn.configure(state='normal', text="Run Optimizer")
        self._opt_status.configure(text="✅ Done")
        for w in self._opt_cards.winfo_children(): w.destroy()

        # Summary banner
        sf = ctk.CTkFrame(self._opt_cards, fg_color=PANEL, corner_radius=8); sf.pack(fill='x', pady=4)
        sr = ctk.CTkFrame(sf, fg_color="transparent"); sr.pack(fill='x', padx=12, pady=10)
        net_col = GREEN if result.impact.net_lap_time_delta_s <= 0 else RED
        stat_blk(sr, "Net Lap Delta", f"{result.impact.net_lap_time_delta_s:+.3f}s", net_col)
        stat_blk(sr, "Balance Before", f"{orig_balance:+.2f}", YELLOW)
        stat_blk(sr, "Balance After", f"{result.projected_balance:+.2f}",
                 GREEN if abs(result.projected_balance) < abs(orig_balance) else YELLOW)
        stat_blk(sr, "Changes", str(len(result.changes)), BLUE)
        lbl(sf, result.description, 11, color=TEXT, wraplength=900).pack(padx=12, pady=(0, 8))

        # Priority-ranked change cards
        PRIORITY_COLORS = [ACCENT, RED, YELLOW, BLUE, PURPLE]
        for rank, change in enumerate(result.changes):
            p_key = change['parameter']
            delta = change['delta']
            pred = next((p for p in result.impact.predictions if p.parameter == p_key), None)

            cf = ctk.CTkFrame(self._opt_cards, fg_color="#1e2845", corner_radius=8)
            cf.pack(fill='x', pady=3)
            hdr = ctk.CTkFrame(cf, fg_color="transparent"); hdr.pack(fill='x', padx=12, pady=(8, 4))

            p_col = PRIORITY_COLORS[rank % len(PRIORITY_COLORS)]
            lbl(hdr, f"P{rank + 1}", 13, bold=True, color=p_col).pack(side='left', padx=(0, 8))
            desc = f"{'+'if delta > 0 else ''}{delta:g}  {p_key.replace('_', ' ').title()}"
            lbl(hdr, desc, 13, bold=True).pack(side='left')

            if pred:
                lbl(hdr, f"Confidence: {pred.confidence:.0%}", 10, color=DIM).pack(side='right')
                mr = ctk.CTkFrame(cf, fg_color="transparent"); mr.pack(fill='x', padx=8, pady=4)
                lt_col = GREEN if pred.lap_time_delta_s <= 0 else RED
                stat_blk(mr, "Lap Time", f"{pred.lap_time_delta_s:+.3f}s", lt_col)
                stat_blk(mr, "Corner", f"{pred.corner_speed_delta_kmh:+.1f} km/h", YELLOW)
                stat_blk(mr, "Straight", f"{pred.straight_speed_delta_kmh:+.1f} km/h", BLUE)
                stat_blk(mr, "Balance", pred.balance_shift.title(), PURPLE)
                stat_blk(mr, "Tire Wear", pred.tire_wear_impact.title())
                nf = ctk.CTkFrame(cf, fg_color="#0d1b2a", corner_radius=6)
                nf.pack(fill='x', padx=12, pady=(0, 8))
                lbl(nf, pred.explanation, 10, color=TEXT, wraplength=900,
                    justify='left', anchor='w').pack(fill='x', padx=8, pady=6)

    # ══════════════════════════════════════════════════════════════════════════
    # FILE WATCHER
    # ══════════════════════════════════════════════════════════════════════════
    def _toggle_file_watcher(self):
        """Toggle auto-detect file watcher on/off."""
        if self._file_watcher and self._file_watcher.is_running:
            self._file_watcher.stop()
            self._file_watcher = None
            self._status_lbl.configure(text="👁 File watcher stopped")
            self.after(3000, lambda: self._status_lbl.configure(text=""))
        else:
            self._file_watcher = FileWatcher(
                on_new_telemetry=lambda p: self.after(0, lambda: self._process(p)),
                on_new_setup=lambda p: self.after(0, lambda: self._auto_load_setup(p)),
            )
            self._file_watcher.start()
            self._status_lbl.configure(text="👁 Watching for new files…")

    def _auto_load_setup(self, path: str):
        """Auto-load a detected setup file."""
        try:
            self.cur_setup = SetupParser().parse_file(path)
            self._render_setup(self.cur_setup)
            self.tv.set("Setup Files")
        except Exception as ex:
            logger.warning("Auto-load setup failed: %s", ex)

    # ══════════════════════════════════════════════════════════════════════════
    # LIVE TELEMETRY
    # ══════════════════════════════════════════════════════════════════════════
    def _toggle_live(self):
        """Start or stop the live iRacing telemetry monitor and dashboard window."""
        if self._live_monitor and self._live_monitor.is_running:
            self._live_monitor.stop()
            self._live_monitor = None
            if self._live_win and self._live_win.winfo_exists():
                self._live_win.destroy()
            self._live_win = None
            self._status_lbl.configure(text="🔴 Live telemetry stopped")
            self.after(3000, lambda: self._status_lbl.configure(text=""))
        else:
            self._live_monitor = LiveTelemetryMonitor(poll_hz=10.0)
            self._live_monitor.add_callback(lambda s: self.after(0, lambda sample=s: self._on_live_sample(sample)))
            self._live_monitor.start()
            self._status_lbl.configure(text="🔴 Live — waiting for iRacing…")
            self._open_live_window()

    def _open_live_window(self):
        """Create the live telemetry dashboard Toplevel window."""
        if self._live_win and self._live_win.winfo_exists():
            self._live_win.lift(); return

        win = ctk.CTkToplevel(self)
        win.title("🔴  Live Telemetry Dashboard")
        win.geometry("520x560")
        win.configure(fg_color=DARK)
        win.resizable(True, True)
        self._live_win = win

        def on_close():
            if self._live_monitor and self._live_monitor.is_running:
                self._live_monitor.stop()
                self._live_monitor = None
            self._live_win = None
            win.destroy()
        win.protocol("WM_DELETE_WINDOW", on_close)

        # Header
        hdr = ctk.CTkFrame(win, fg_color=PANEL, height=40, corner_radius=0)
        hdr.pack(fill='x'); hdr.pack_propagate(False)
        win._conn_lbl = lbl(hdr, "⏳ Connecting to iRacing…", 12, color=YELLOW)
        win._conn_lbl.pack(side='left', padx=12)
        win._car_lbl = lbl(hdr, "", 11, color=DIM)
        win._car_lbl.pack(side='right', padx=12)

        # Speed / Gear row
        sg = ctk.CTkFrame(win, fg_color=PANEL, corner_radius=8)
        sg.pack(fill='x', padx=10, pady=(8, 4))
        win._spd_lbl = lbl(sg, "-- km/h", 36, bold=True, color=GREEN)
        win._spd_lbl.pack(side='left', padx=20, pady=8)
        win._gear_lbl = lbl(sg, "G--", 36, bold=True, color=YELLOW)
        win._gear_lbl.pack(side='left', padx=20)
        win._rpm_lbl = lbl(sg, "RPM: ----", 14, color=TEXT)
        win._rpm_lbl.pack(side='left', padx=20)

        # Throttle / Brake bars
        bars = ctk.CTkFrame(win, fg_color=PANEL, corner_radius=8)
        bars.pack(fill='x', padx=10, pady=4)
        lbl(bars, "Throttle", 10, color=DIM).grid(row=0, column=0, padx=8, pady=(6,2), sticky='w')
        win._thr_bar = ctk.CTkProgressBar(bars, width=300, height=16, fg_color=CARD,
                                           progress_color=GREEN, mode='determinate')
        win._thr_bar.grid(row=0, column=1, padx=8, pady=(6,2))
        win._thr_bar.set(0)
        win._thr_pct = lbl(bars, "0%", 10, color=GREEN)
        win._thr_pct.grid(row=0, column=2, padx=4)
        lbl(bars, "Brake", 10, color=DIM).grid(row=1, column=0, padx=8, pady=(2,6), sticky='w')
        win._brk_bar = ctk.CTkProgressBar(bars, width=300, height=16, fg_color=CARD,
                                           progress_color=RED, mode='determinate')
        win._brk_bar.grid(row=1, column=1, padx=8, pady=(2,6))
        win._brk_bar.set(0)
        win._brk_pct = lbl(bars, "0%", 10, color=RED)
        win._brk_pct.grid(row=1, column=2, padx=4)

        # Lap times row
        lt = ctk.CTkFrame(win, fg_color=PANEL, corner_radius=8)
        lt.pack(fill='x', padx=10, pady=4)
        win._laptime_lbl = lbl(lt, "Lap: --:--.---", 16, bold=True, color=ACCENT)
        win._laptime_lbl.pack(side='left', padx=16, pady=8)
        win._lastlap_lbl = lbl(lt, "Last: --:--.---", 12, color=DIM)
        win._lastlap_lbl.pack(side='left', padx=12)
        win._bestlap_lbl = lbl(lt, "Best: --:--.---", 12, color=GREEN)
        win._bestlap_lbl.pack(side='left', padx=12)
        win._lap_num_lbl = lbl(lt, "Lap --", 11, color=DIM)
        win._lap_num_lbl.pack(side='right', padx=12)

        # Fuel row
        fl = ctk.CTkFrame(win, fg_color=PANEL, corner_radius=8)
        fl.pack(fill='x', padx=10, pady=4)
        win._fuel_lbl = lbl(fl, "Fuel: --L  (-- %)", 12, color=BLUE)
        win._fuel_lbl.pack(side='left', padx=16, pady=6)
        win._pos_lbl = lbl(fl, "Track: --%", 11, color=DIM)
        win._pos_lbl.pack(side='left', padx=12)

        # Tire temps grid
        tg_outer = ctk.CTkFrame(win, fg_color=PANEL, corner_radius=8)
        tg_outer.pack(fill='x', padx=10, pady=4)
        lbl(tg_outer, "Tire Temperatures (°C / °F)", 10, bold=True, color=DIM).pack(anchor='w', padx=10, pady=(6, 2))
        tg = ctk.CTkFrame(tg_outer, fg_color="transparent")
        tg.pack(padx=10, pady=(0, 8))
        win._tire_lbls = {}
        corners = [('LF', 0, 0), ('RF', 0, 1), ('LR', 1, 0), ('RR', 1, 1)]
        for corner, row, col in corners:
            f = ctk.CTkFrame(tg, fg_color=CARD, corner_radius=6, width=110, height=60)
            f.grid(row=row, column=col, padx=6, pady=4)
            f.grid_propagate(False)
            lbl(f, corner, 10, bold=True, color=DIM).pack(pady=(4, 0))
            t_lbl = lbl(f, "--°C\n--°F", 13, bold=True, color=TEXT)
            t_lbl.pack()
            win._tire_lbls[corner] = t_lbl

        # Not connected / install hint banner (hidden by default)
        win._hint_lbl = lbl(win, "", 10, color=YELLOW, justify='center')
        win._hint_lbl.pack(pady=4)

        win.lift()

    def _on_live_sample(self, sample: LiveSample):
        """Receive a live sample and update the dashboard window."""
        if self._live_win is None or not self._live_win.winfo_exists():
            return
        win = self._live_win

        if not sample.is_connected:
            if self._live_monitor and self._live_monitor.sdk_missing:
                win._conn_lbl.configure(
                    text="⚠ pyirsdk not installed",
                    text_color=RED)
                win._hint_lbl.configure(
                    text="Install with:  pip install pyirsdk  then restart the app.")
            else:
                win._conn_lbl.configure(
                    text="⏳ Waiting for iRacing…", text_color=YELLOW)
            return

        # Connected — update all widgets
        win._conn_lbl.configure(text="🟢 Connected", text_color=GREEN)
        win._hint_lbl.configure(text="")
        if sample.car_name:
            win._car_lbl.configure(text=f"{sample.car_name}  •  {sample.track_name}")

        spd_color = GREEN if sample.speed_kph > 10 else DIM
        win._spd_lbl.configure(text=f"{sample.speed_kph:.0f} km/h", text_color=spd_color)
        win._gear_lbl.configure(text=f"G{sample.gear}")
        win._rpm_lbl.configure(text=f"RPM: {sample.rpm:.0f}")

        win._thr_bar.set(sample.throttle)
        win._thr_pct.configure(text=f"{sample.throttle * 100:.0f}%")
        win._brk_bar.set(sample.brake)
        win._brk_pct.configure(text=f"{sample.brake * 100:.0f}%")

        win._laptime_lbl.configure(text=f"Lap: {format_laptime(sample.lap_time)}")
        win._lastlap_lbl.configure(text=f"Last: {format_laptime(sample.last_lap)}")
        win._bestlap_lbl.configure(text=f"Best: {format_laptime(sample.best_lap)}")
        win._lap_num_lbl.configure(text=f"Lap {sample.lap}")

        win._fuel_lbl.configure(text=f"Fuel: {sample.fuel_level:.1f}L  ({sample.fuel_pct * 100:.0f}%)")
        win._pos_lbl.configure(text=f"Track: {sample.lap_dist_pct * 100:.1f}%")

        self._status_lbl.configure(text=f"🔴 Live  {sample.speed_kph:.0f} km/h  Lap {sample.lap}")

        for corner, t_lbl in win._tire_lbls.items():
            temps = sample.tire_temps.get(corner, {})
            avg_t = (temps.get('inner', 0) + temps.get('mid', 0) + temps.get('outer', 0)) / 3
            if avg_t > 0:
                col = RED if avg_t > 105 else YELLOW if avg_t > 95 else GREEN if avg_t > 70 else BLUE
                t_lbl.configure(text=f"{avg_t:.0f}°C\n{avg_t*9/5+32:.0f}°F", text_color=col)

    # ══════════════════════════════════════════════════════════════════════════
    # REFERENCE LAP LOADING
    # ══════════════════════════════════════════════════════════════════════════
    def _load_ref_ibt(self):
        """Load an external IBT file as a reference lap for cross-session delta comparison."""
        path = filedialog.askopenfilename(
            title="Load Reference IBT",
            filetypes=[("iRacing Telemetry", "*.ibt"), ("All Files", "*.*")],
            initialdir=self.cfg.get('last_dir', ''))
        if not path:
            return
        try:
            ref = IBTParser(path).parse()
            self._ref_data = ref
            name = f"{ref.car_name} @ {ref.track_name} — best {format_laptime(min(ref.lap_times))}"
            self._ref_lbl.configure(text=name[:60])
            self._status_lbl.configure(text=f"Reference loaded: {os.path.basename(path)}")
            self.after(4000, lambda: self._status_lbl.configure(text=""))
            # Auto-switch to the external delta chart
            self._tv.set("Reference Lap — External Delta")
            self._redraw_telem("Reference Lap — External Delta")
        except Exception as ex:
            logger.exception("Failed to load reference IBT")
            messagebox.showerror("Error", f"Could not load reference IBT:\n{type(ex).__name__}: {ex}")

    # ══════════════════════════════════════════════════════════════════════════
    # AUTO SESSION NOTES
    # ══════════════════════════════════════════════════════════════════════════
    def _generate_note_bg(self, sess_idx, rpt, data, sec, style, api_key):
        """Background thread: generate a 3-sentence session diary note."""
        note_parts = []
        try:
            for chunk in generate_session_note_stream(
                    rpt, data.car_name, data.track_name, api_key,
                    sector_report=sec, style_report=style,
                    session_info=data.session_info):
                note_parts.append(chunk)
        except Exception as ex:
            logger.debug("Auto-note generation failed: %s", ex)
            return
        note = "".join(note_parts).strip()
        if note:
            self._session_notes[sess_idx] = note
            logger.info("Auto-note generated for session %d", sess_idx)

    # ══════════════════════════════════════════════════════════════════════════
    # MOTEC EXPORT
    # ══════════════════════════════════════════════════════════════════════════
    def _export_motec(self):
        """Export current session telemetry in Motec i2-compatible CSV format."""
        if not self.cur_data:
            messagebox.showwarning("No Session", "Load a session first.")
            return
        d = self.cur_data
        default_name = f"motec_{d.car_name}_{datetime.now():%Y%m%d_%H%M}.csv"
        path = filedialog.asksaveasfilename(
            title="Export Motec i2 CSV",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv"), ("All Files", "*.*")],
            initialfile=default_name,
        )
        if not path:
            return
        try:
            export_motec_csv(d, path, lap_idx=-1)
            messagebox.showinfo("Exported", f"Motec CSV saved to:\n{path}")
        except Exception as ex:
            logger.exception("Motec export failed")
            messagebox.showerror("Export Error", f"Motec export failed:\n{type(ex).__name__}: {ex}")

    # ══════════════════════════════════════════════════════════════════════════
    # COMMAND PALETTE  (Ctrl+K)
    # ══════════════════════════════════════════════════════════════════════════
    def _open_command_palette(self):
        """Open a fuzzy-search command palette popup (VS Code style)."""
        # All addressable commands
        _COMMANDS = [
            ("Load IBT File",              self._load_ibt),
            ("Load Demo Session",          self._load_demo),
            ("Batch Load IBT Files",       self._batch_load),
            ("Export CSV",                 self._export_csv),
            ("Export PDF Report",          self._export_pdf),
            ("Export Motec i2 CSV",        self._export_motec),
            ("Share / Export Summary",     self._share_export),
            ("Send to Discord",            self._discord_share),
            ("Load Reference Lap",         self._load_ref_ibt),
            ("Toggle Live Telemetry",      self._toggle_live),
            ("Toggle File Watcher",        self._toggle_file_watcher),
            ("Settings",                   self._settings),
            ("About",                      self._about),
        ] + [(f"Go to: {tab}", lambda t=tab: self.tv.set(t))
             for tab in ["Dashboard","Telemetry","Issues","Driver","Sectors","Corners",
                         "Stint & Tires","Lap Times","Brake Trace","Strategy","Trends",
                         "Impact","Setup Files","AI Advisor","Templates","History","Compare"]]

        win = ctk.CTkToplevel(self)
        win.title("Command Palette")
        win.geometry("540x380")
        win.configure(fg_color=DARK)
        win.resizable(False, True)
        win.transient(self)
        win.grab_set()

        search_var = ctk.StringVar()
        entry = ctk.CTkEntry(win, textvariable=search_var,
                              placeholder_text="Type a command…",
                              fg_color=PANEL, border_color=ACCENT,
                              font=ctk.CTkFont(size=14), height=40)
        entry.pack(fill='x', padx=10, pady=(10, 4))
        entry.focus_set()

        sc = ctk.CTkScrollableFrame(win, fg_color="transparent")
        sc.pack(fill='both', expand=True, padx=10, pady=(0, 10))

        _btns: list[ctk.CTkButton] = []

        def _refresh_list(*_):
            for b in _btns: b.destroy()
            _btns.clear()
            q = search_var.get().lower()
            for label, cmd in _COMMANDS:
                if q and q not in label.lower():
                    continue
                b = ctk.CTkButton(sc, text=label, anchor='w', height=34,
                                  fg_color="transparent", hover_color=PANEL,
                                  text_color=TEXT,
                                  font=ctk.CTkFont(size=12),
                                  command=lambda c=cmd: (win.destroy(), c()))
                b.pack(fill='x', pady=1)
                _btns.append(b)

        search_var.trace_add('write', _refresh_list)
        win.bind('<Escape>', lambda e: win.destroy())
        win.bind('<Return>', lambda e: (_btns[0].invoke() if _btns else None))
        _refresh_list()

    # ══════════════════════════════════════════════════════════════════════════
    # SHARE EXPORT
    # ══════════════════════════════════════════════════════════════════════════
    def _share_export(self):
        """One-click share: export session summary as JSON, clipboard, or Discord."""
        if not self.cur_data or not self.cur_rpt:
            messagebox.showwarning("No Session", "Load a session first.")
            return
        cs = self._compute_consistency_score()
        summary = build_share_summary(
            self.cur_data, self.cur_rpt,
            consistency=cs, sector_report=self.cur_sec,
            stint_report=self.cur_stint, setup=self.cur_setup,
            app_version=VERSION,
        )
        # Build a dialog with 4 options
        win = ctk.CTkToplevel(self)
        win.title("Share / Export"); win.geometry("340x200")
        win.configure(fg_color=DARK); win.resizable(False, False)
        win.transient(self); win.grab_set()
        lbl(win, "Export session summary:", 13, bold=True).pack(pady=(16, 8))
        btn_frame = ctk.CTkFrame(win, fg_color="transparent"); btn_frame.pack(pady=4)

        def _json():
            win.destroy()
            path = filedialog.asksaveasfilename(
                title="Export JSON", defaultextension=".json",
                filetypes=[("JSON", "*.json")],
                initialfile=f"share_{self.cur_data.car_name}_{datetime.now():%Y%m%d_%H%M}.json")
            if path:
                export_json(summary, path)
                messagebox.showinfo("Exported", f"Saved to:\n{path}")

        def _clip():
            win.destroy()
            text = export_clipboard_text(summary)
            self.clipboard_clear(); self.clipboard_append(text)
            messagebox.showinfo("Copied", "Session summary copied to clipboard!")

        def _discord():
            win.destroy()
            self._discord_share(summary)

        for txt, cmd, bg in [
            ("💾  Save JSON",        _json,    CARD),
            ("📋  Copy to Clipboard",_clip,    CARD),
            ("💬  Send to Discord",  _discord, BLUE),
        ]:
            ctk.CTkButton(btn_frame, text=txt, width=240, height=34,
                          fg_color=bg, hover_color=ACCENT,
                          command=cmd).pack(pady=3)

    def _discord_share(self, summary=None):
        """Send the current session summary to a Discord webhook."""
        if not self.cur_data or not self.cur_rpt:
            messagebox.showwarning("No Session", "Load a session first.")
            return
        if summary is None:
            cs = self._compute_consistency_score()
            summary = build_share_summary(
                self.cur_data, self.cur_rpt,
                consistency=cs, sector_report=self.cur_sec,
                stint_report=self.cur_stint, setup=self.cur_setup,
                app_version=VERSION)

        webhook = self.cfg.get('discord_webhook', '').strip()
        if not webhook:
            # Ask user to enter a webhook URL
            win = ctk.CTkToplevel(self)
            win.title("Discord Webhook"); win.geometry("460x140")
            win.configure(fg_color=DARK); win.resizable(False, False)
            win.transient(self); win.grab_set()
            lbl(win, "Enter your Discord channel webhook URL:", 12).pack(pady=(14, 6))
            url_entry = ctk.CTkEntry(win, width=400, fg_color=CARD,
                                      placeholder_text="https://discord.com/api/webhooks/…")
            url_entry.pack(pady=4)
            def _send():
                url = url_entry.get().strip()
                if not url.startswith("https://"):
                    messagebox.showwarning("Invalid URL", "Please enter a valid https:// webhook URL."); return
                self.cfg['discord_webhook'] = url
                save_cfg(self.cfg)
                win.destroy()
                self._do_discord_send(summary, url)
            ctk.CTkButton(win, text="Send", width=120, fg_color=ACCENT,
                          hover_color="#c0392b", command=_send).pack(pady=8)
            return
        self._do_discord_send(summary, webhook)

    def _do_discord_send(self, summary, webhook_url: str):
        """Fire the Discord webhook POST in a background thread."""
        self._status_lbl.configure(text="💬 Sending to Discord…")
        def worker():
            try:
                send_discord_webhook(summary, webhook_url)
                self.after(0, lambda: (
                    self._status_lbl.configure(text="✅ Sent to Discord"),
                    self.after(4000, lambda: self._status_lbl.configure(text=""))))
            except Exception as ex:
                self.after(0, lambda: messagebox.showerror(
                    "Discord Error", f"Failed to send:\n{ex}"))
        threading.Thread(target=worker, daemon=True).start()

    # ══════════════════════════════════════════════════════════════════════════
    # SESSION ORCHESTRATION
    # ══════════════════════════════════════════════════════════════════════════
    def _load_ibt(self):
        # Auto-detect iRacing telemetry directory
        init_dir = self.cfg.get('last_dir', '')
        if not init_dir or not os.path.isdir(init_dir):
            for base in [os.path.expanduser('~/Documents'), os.path.expanduser('~/OneDrive/Documents')]:
                candidate = os.path.join(base, 'iRacing', 'telemetry')
                if os.path.isdir(candidate):
                    init_dir = candidate
                    break
        path=filedialog.askopenfilename(title="Select IBT",initialdir=init_dir,
            filetypes=[("iRacing Telemetry","*.ibt"),("All","*.*")])
        if not path: return
        self.cfg['last_dir']=os.path.dirname(path); save_cfg(self.cfg); self._process(path)

    def _load_demo(self): self._process(None, demo=True)

    def _end_loading(self, error_msg=None):
        """Reset loading state and re-enable buttons."""
        self._loading = False
        for btn in self._load_btns:
            btn.configure(state='normal')
        self._progress.stop(); self._progress.pack_forget()
        self._status_lbl.configure(text="")
        if error_msg:
            messagebox.showerror("Error", error_msg)

    def _process(self,path,demo=False):
        if self._loading:
            return
        self._loading = True
        for btn in self._load_btns:
            btn.configure(state='disabled')
        self._status_lbl.configure(text="⏳ Loading telemetry…")
        self._progress.pack(side='left',padx=8)
        self._progress.start()
        if path and not demo:
            self._add_recent(path)
        cancel = threading.Event()
        def worker():
            try:
                if demo:
                    data = load_demo_data()
                else:
                    data = load_cached(path)
                    if data is None:
                        data = IBTParser(path).parse()
                        save_cached(path, data)
                if cancel.is_set(): return
                rpt=self.engine.analyze(data)
                if cancel.is_set(): return
                sec=SectorAnalyzer().analyze(data,3)
                best=BestLapAnalyzer().analyze(data)
                stint=StintAnalyzer().analyze(data)
                if cancel.is_set(): return
                style=DrivingStyleAnalyzer().analyze(data)
                fuel=FuelStrategyAnalyzer().analyze(data)
                if cancel.is_set(): return
                self.after(0,lambda:self._on_loaded(data,rpt,sec,best,stint,style,fuel))
            except Exception as ex:
                if cancel.is_set(): return
                logger.exception("Failed to process telemetry")
                err_msg = f"Failed to load telemetry:\n{type(ex).__name__}: {ex}"
                self.after(0, lambda err=err_msg: self._end_loading(err))
        t=threading.Thread(target=worker,daemon=True)
        t.start()
        def _check_timeout():
            if t.is_alive():
                cancel.set()
                logger.warning("Telemetry processing exceeded 120s timeout")
                self._end_loading()
                self._status_lbl.configure(text="⚠ Processing timed out")
        self.after(120_000, _check_timeout)

    def _on_loaded(self,data,rpt,sec,best,stint,style,fuel):
        self._end_loading()
        # LRU eviction: drop oldest session when over limit
        while len(self.sessions) >= MAX_SESSIONS:
            evicted_data, evicted_rpt = self.sessions.pop(0)
            logger.info("Evicted session: %s @ %s (limit: %d)",
                        evicted_data.car_name, evicted_data.track_name, MAX_SESSIONS)
            self._status_lbl.configure(
                text=f"⚠ Dropped oldest session: {evicted_data.car_name} — {evicted_data.track_name}")
            self.after(5000, lambda: self._status_lbl.configure(text=""))
            self._analysis_cache = {k-1: v for k, v in self._analysis_cache.items() if k > 0}
            self._ai_cache = {k-1: v for k, v in self._ai_cache.items() if k > 0}
            cards = [w for w in self._sf.winfo_children() if isinstance(w, ctk.CTkFrame)]
            if cards:
                cards[0].destroy()
            logger.info("Evicted oldest session (limit: %d)", MAX_SESSIONS)
        self.sessions.append((data,rpt))
        self._analysis_cache[len(self.sessions) - 1] = (sec, best, stint, style, fuel)
        self.cur_data=data; self.cur_rpt=rpt
        self.cur_sec=sec; self.cur_best=best
        self.cur_stint=stint; self.cur_style=style
        self.cur_fuel=fuel
        self._last_opt_result = None   # invalidate optimizer result for new session
        # Auto-load setup from IBT session info if CarSetup is embedded
        car_setup = data.session_info.get('car_setup')
        if car_setup:
            try:
                self.cur_setup = parsed_setup_from_ibt(
                    car_setup, data.car_name, data.track_name)
                self._render_setup(self.cur_setup)
            except Exception as e:
                logger.warning("Could not extract setup from IBT: %s", e)
        self._add_sess_card(data,rpt)
        self._refresh(); self._u_cmp_menus()
        # Feed ML predictor with new session features
        feat = self._ml_predictor.extract(data, rpt)
        if feat is not None:
            self._ml_features.append(feat)
            if len(self._ml_features) >= 3:
                self._ml_predictor.train(self._ml_features)
        # Auto-generate session note if enabled and API key present
        if self.cfg.get('auto_notes') and self.cfg.get('ai_consent'):
            key = _get_api_key().strip()
            if key:
                sess_idx = len(self.sessions) - 1
                threading.Thread(
                    target=self._generate_note_bg,
                    args=(sess_idx, rpt, data, sec, style, key),
                    daemon=True).start()
        # Chain next batch file if queued
        if self._batch_queue:
            self.after(50, self._batch_next)

    def _sel(self,data,rpt):
        if self._loading:
            return
        self.cur_data=data; self.cur_rpt=rpt
        self._highlight_card(data)
        idx = next((i for i,(d,_) in enumerate(self.sessions) if d is data), None)
        cached = self._analysis_cache.get(idx) if idx is not None else None
        if cached:
            self.cur_sec, self.cur_best, self.cur_stint, self.cur_style, self.cur_fuel = cached
            self._refresh()
        else:
            self._loading = True
            self._status_lbl.configure(text="⏳ Analyzing…")
            done = threading.Event()
            def worker():
                try:
                    sec=SectorAnalyzer().analyze(data,3)
                    best=BestLapAnalyzer().analyze(data)
                    stint=StintAnalyzer().analyze(data)
                    style=DrivingStyleAnalyzer().analyze(data)
                    fuel=FuelStrategyAnalyzer().analyze(data)
                    self.after(0,lambda:self._sel_done(idx,sec,best,stint,style,fuel))
                except Exception:
                    logger.exception("Background analysis failed in _sel")
                    self.after(0,lambda:(
                        setattr(self,'_loading',False),
                        setattr(self,'cur_sec',None),setattr(self,'cur_best',None),
                        setattr(self,'cur_stint',None),setattr(self,'cur_style',None),
                        setattr(self,'cur_fuel',None),
                        self._status_lbl.configure(text="⚠ Analysis failed")))
                finally:
                    done.set()
            t=threading.Thread(target=worker,daemon=True)
            t.start()
            def _sel_timeout():
                if not done.is_set():
                    self._loading = False
                    self._status_lbl.configure(text="⚠ Analysis timed out")
            self.after(60_000, _sel_timeout)

    def _sel_done(self,idx,sec,best,stint,style,fuel):
        self._loading = False
        if idx is not None:
            self._analysis_cache[idx] = (sec, best, stint, style, fuel)
        self.cur_sec=sec; self.cur_best=best
        self.cur_stint=stint; self.cur_style=style
        self.cur_fuel=fuel
        self._status_lbl.configure(text="")
        self._refresh()

    def _refresh(self):
        self._rebuild_lap_checks()
        self._stale_tabs = {"Dashboard","Telemetry","Issues","Driver",
                            "Sectors","Corners","Stint & Tires","Lap Times",
                            "Brake Trace","Trends","Impact"}
        self._refresh_active_tab()

    def _refresh_active_tab(self):
        tab = self.tv.get()
        # Ensure tab is built before updating
        if tab not in self._built_tabs:
            builder = self._tab_builders.get(tab)
            if builder:
                builder()
                self._built_tabs.add(tab)
        self._stale_tabs.discard(tab)
        _updaters = {
            "Dashboard": self._u_dashboard,
            "Telemetry": self._redraw_telem,
            "Issues": self._pop_issues,
            "Driver": self._u_driver,
            "Sectors": self._draw_sectors,
            "Corners": self._u_corners,
            "Stint & Tires": lambda: (self._u_stint(), self._u_fuel()),
            "Lap Times": self._u_laptimes,
            "Brake Trace": self._u_brake_trace,
            "Trends": self._u_trends,
        }
        updater = _updaters.get(tab)
        if updater:
            updater()

    def _on_tab_change(self):
        tab = self.tv.get()
        # Lazy build: construct tab UI on first visit
        if tab not in self._built_tabs:
            builder = self._tab_builders.get(tab)
            if builder:
                builder()
                self._built_tabs.add(tab)
        if hasattr(self, '_stale_tabs') and tab in self._stale_tabs:
            self._refresh_active_tab()

    def _u_cmp_menus(self):
        if not hasattr(self, '_cam'):
            return
        vals=[f"#{i+1} {d.car_name} — {format_laptime(r.best_lap)}" for i,(d,r) in enumerate(self.sessions)]
        if vals:
            self._cam.configure(values=vals); self._ca.set(vals[0])
            self._cbm.configure(values=vals); self._cb.set(vals[-1])


if __name__ == "__main__":
    try:
        App().mainloop()
    except Exception:
        crash_msg = traceback.format_exc()
        logger.critical("UNHANDLED CRASH:\n%s", crash_msg)
        # Write crash report
        crash_file = os.path.join(_LOG_DIR, f"crash_{datetime.now():%Y%m%d_%H%M%S}.txt")
        try:
            with open(crash_file, 'w') as f:
                f.write(f"{APP_NAME} v{VERSION} — Crash Report\n")
                f.write(f"Time: {datetime.now()}\n\n")
                f.write(crash_msg)
        except Exception:
            pass
        # Show error dialog if possible
        try:
            import tkinter as tk
            root = tk.Tk(); root.withdraw()
            messagebox.showerror("Crash Report",
                f"{APP_NAME} encountered an unexpected error.\n\n"
                f"Crash log saved to:\n{crash_file}\n\n"
                f"Please include this file when reporting the issue.")
            root.destroy()
        except Exception:
            pass
        sys.exit(1)
