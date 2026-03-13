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
from core.setup_parser        import SetupParser, SetupExporter, SetupDiffer, ParsedSetup, create_demo_setup
from core.ai_advisor          import get_ai_recommendations_sync, get_ai_recommendations_stream
from data.templates.track_templates import get_setup_template, get_track_info, list_tracks
from core.lap_overlay         import extract_lap_trace, compare_laps
from core.brake_analysis      import analyze_braking, BrakeAnalysisReport
from core.session_aggregator  import aggregate_sessions, AggregationReport
from core.stint_strategy      import calculate_strategy, StrategyReport
from core.file_watcher        import FileWatcher
from core.setup_impact        import predict_impact, get_available_parameters, ImpactReport
from core.racing_line         import reconstruct_racing_line, speed_colormap
from core.gg_diagram          import analyze_gg_per_corner, GGReport
from core.share_export        import build_share_summary, export_json, export_clipboard_text

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
        self._batch_queue: list[str] = []
        self._batch_total = 0
        self._file_watcher: FileWatcher | None = None
        self._build()
        self._bind_shortcuts()
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
        self._dif=ctk.CTkFrame(self._dash_sc,fg_color="transparent"); self._dif.pack(fill='x',padx=10,pady=(4,10))

    def _u_dashboard(self):
        d,r=self.cur_data,self.cur_rpt
        if d is None or r is None:
            return
        self._dash_ph.pack_forget(); self._dash_sc.pack(fill='both',expand=True)
        for w in self._di.winfo_children(): w.destroy()
        lbl(self._di,d.car_name.replace('_',' ').title(),15,bold=True).pack(anchor='w',padx=12,pady=(10,0))
        lbl(self._di,d.track_name,12,color=DIM).pack(anchor='w',padx=12)
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
        if at: stat_blk(sr,"Air Temp",f"{at:.1f}°C",tooltip="Ambient air temperature")
        if tt: stat_blk(sr,"Track Temp",f"{tt:.1f}°C",YELLOW,tooltip="Track surface temperature")
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

    def _draw_tires(self,ts):
        c=self._dth; c.clear(); ax=c.fig.add_subplot(111,facecolor=PANEL)
        ax.set_title("Tire Temps (°C)",color=TEXT,fontsize=11); ax.set_xlim(0,4); ax.set_ylim(0,3); ax.axis('off')
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
            ax.text(cx,cy-0.18,f"avg {t.get('avg',0):.1f}°C",ha='center',fontsize=8,color=DIM)
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
                          ("🏁 Save to iRacing",self._save_to_iracing,CARD),
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

    def _save_to_iracing(self):
        if not self.cur_setup:
            messagebox.showwarning("No Setup", "Load a setup first.")
            return
        setups_dir = self._find_iracing_setups_dir()
        if not setups_dir:
            messagebox.showerror("iRacing Not Found",
                "Could not find iRacing setups folder.\n\n"
                "Expected at:\n  Documents/iRacing/setups/\n\n"
                "Use 'Export Setup' to save to a custom location.")
            return
        # Determine car subfolder from the setup's car name
        car = (self.cur_setup.car or '').strip()
        if not car and self.cur_data:
            car = self.cur_data.car_name or ''
        # Sanitize into a safe folder name (keep alphanumeric, underscores, hyphens, spaces)
        car_folder = re.sub(r'[^\w\s\-]', '', car).strip() or 'unknown_car'
        target_dir = os.path.join(setups_dir, car_folder)
        os.makedirs(target_dir, exist_ok=True)
        default_name = f"setup_{datetime.now():%Y%m%d_%H%M}.htm"
        path = filedialog.asksaveasfilename(
            title="Save Setup to iRacing", defaultextension=".htm",
            initialdir=target_dir,
            filetypes=[("iRacing Setup", "*.htm")],
            initialfile=default_name)
        if not path:
            return
        try:
            SetupExporter().export_htm(self.cur_setup, path)
            messagebox.showinfo("Saved to iRacing",
                f"Setup saved!\n\n{path}\n\n"
                "It will appear in the iRacing garage\nunder this car's setup list.")
        except Exception:
            logger.exception("Failed to save setup to iRacing")
            messagebox.showerror("Error", "Failed to save setup file.")

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
        self._ait=ctk.CTkTextbox(tab,fg_color=PANEL,text_color=TEXT,
            font=ctk.CTkFont(family="Helvetica",size=13),wrap='word')
        self._ait.pack(fill='both',expand=True,padx=10,pady=(4,8))
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
        path = self._batch_queue.pop(0)
        self._process(path)

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
        win=ctk.CTkToplevel(self); win.title("Settings"); win.geometry("540x400")
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
        def save(): _set_api_key(e.get().strip()); save_cfg(self.cfg); win.destroy()
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
                generate_pdf_report(output_path=path,data=self.cur_data,report=self.cur_rpt,
                    sector_report=self.cur_sec,best_report=self.cur_best,
                    tire_deg=self.cur_stint,
                    driver_report=self.cur_style,ai_text=self._ai_last_text)
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

    # ══════════════════════════════════════════════════════════════════════════
    # IMPACT TAB (Setup Change Impact Predictor)
    # ══════════════════════════════════════════════════════════════════════════
    def _t_impact(self):
        tab = self.tv.tab("Impact"); tab.configure(fg_color=DARK)
        lbl(tab, "Setup Change Impact Predictor", 15, bold=True, color=ACCENT).pack(anchor='w', padx=12, pady=(8, 2))
        lbl(tab, "Predict effect of setup changes on lap time, balance, and tire wear.", 11,
            color=DIM).pack(anchor='w', padx=12, pady=(0, 8))
        # Input controls
        ctrl = ctk.CTkFrame(tab, fg_color=PANEL, corner_radius=8); ctrl.pack(fill='x', padx=10, pady=4)
        self._impact_rows: list[tuple] = []
        params = get_available_parameters()
        for i in range(3):  # 3 change slots
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
        self._impact_sc = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        self._impact_sc.pack(fill='both', expand=True, padx=10, pady=4)
        self._impact_cards = ctk.CTkFrame(self._impact_sc, fg_color="transparent")
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
        # Summary
        sf = ctk.CTkFrame(self._impact_cards, fg_color=PANEL, corner_radius=8); sf.pack(fill='x', pady=4)
        sr = ctk.CTkFrame(sf, fg_color="transparent"); sr.pack(fill='x', padx=12, pady=10)
        net_col = GREEN if report.net_lap_time_delta_s < 0 else RED if report.net_lap_time_delta_s > 0 else DIM
        stat_blk(sr, "Net Lap Delta", f"{report.net_lap_time_delta_s:+.3f}s", net_col)
        stat_blk(sr, "Balance", report.net_balance_shift.title(), YELLOW)
        lbl(sf, report.summary, 11, color=TEXT, wraplength=800).pack(padx=12, pady=(0, 8))
        # Per-change cards
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
    # SHARE EXPORT
    # ══════════════════════════════════════════════════════════════════════════
    def _share_export(self):
        """One-click share: export session summary as JSON or copy to clipboard."""
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
        choice = messagebox.askyesnocancel(
            "Share Export",
            "Export session summary:\n\n"
            "Yes = Save as JSON file\n"
            "No = Copy text to clipboard\n"
            "Cancel = Cancel",
        )
        if choice is True:
            path = filedialog.asksaveasfilename(
                title="Export JSON", defaultextension=".json",
                filetypes=[("JSON", "*.json")],
                initialfile=f"share_{self.cur_data.car_name}_{datetime.now():%Y%m%d_%H%M}.json",
            )
            if path:
                export_json(summary, path)
                messagebox.showinfo("Exported", f"Saved to:\n{path}")
        elif choice is False:
            text = export_clipboard_text(summary)
            self.clipboard_clear()
            self.clipboard_append(text)
            messagebox.showinfo("Copied", "Session summary copied to clipboard!")

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

    def _load_demo(self): self._process("",demo=True)

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
                data=load_demo_data() if demo else IBTParser(path).parse()
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
                self.after(0,lambda:self._end_loading(
                    f"Failed to load telemetry:\n{type(ex).__name__}: {ex}"))
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
        self._add_sess_card(data,rpt)
        self._refresh(); self._u_cmp_menus()
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
