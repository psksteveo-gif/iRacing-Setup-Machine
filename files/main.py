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
from core.setup_parser        import SetupParser, SetupExporter, SetupDiffer, ParsedSetup, create_demo_setup
from core.ai_advisor          import get_ai_recommendations_sync, get_ai_recommendations_stream
from data.templates.track_templates import get_setup_template, get_track_info, list_tracks

# ── Theme ─────────────────────────────────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")
DARK="#1a1a2e"; PANEL="#16213e"; CARD="#0f3460"
ACCENT="#e94560"; BLUE="#00b4d8"; TEXT="#eaeaea"
DIM="#8a8fa3"; GREEN="#2ecc71"; YELLOW="#f39c12"
RED="#e74c3c"; PURPLE="#9b59b6"
SEV_COLOR={Severity.CRITICAL:RED,Severity.WARNING:YELLOW,Severity.INFO:BLUE}
MAX_SESSIONS = 20  # LRU eviction when exceeded
CONFIG_FILE=os.path.expanduser("~/.iracing_setup_advisor.json")
_KEYRING_SERVICE = "iracing_setup_advisor"
_KEYRING_USER = "anthropic_api_key"

def _get_api_key() -> str:
    """Retrieve API key from OS credential store, falling back to config file."""
    try:
        import keyring
        key = keyring.get_password(_KEYRING_SERVICE, _KEYRING_USER)
        if key:
            return key
    except Exception:
        pass
    # Fallback: read from legacy config (for migration)
    cfg = load_cfg()
    return cfg.get("api_key", "")

def _set_api_key(key: str):
    """Store API key in OS credential store. Never stores in plaintext."""
    try:
        import keyring
        if key:
            keyring.set_password(_KEYRING_SERVICE, _KEYRING_USER, key)
        else:
            try:
                keyring.delete_password(_KEYRING_SERVICE, _KEYRING_USER)
            except Exception:
                pass
    except ImportError:
        logger.warning("keyring package not available — API key will NOT be saved.")
        messagebox.showwarning("Security Warning",
            "The 'keyring' package is not installed.\n"
            "Your API key will only be used for this session and NOT saved.\n\n"
            "Install it with: pip install keyring")
    except Exception as e:
        logger.warning("Failed to store API key in keyring: %s", e)

def load_cfg():
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                cfg = json.load(f)
            # Migrate plaintext API key to keyring if present
            if cfg.get("api_key"):
                try:
                    import keyring
                    keyring.set_password(_KEYRING_SERVICE, _KEYRING_USER, cfg["api_key"])
                    cfg.pop("api_key", None)
                    save_cfg(cfg)
                except Exception:
                    pass
            else:
                cfg.pop("api_key", None)
            return cfg
    except (json.JSONDecodeError, IOError, OSError) as e:
        logger.warning("Could not load config: %s", e)
    return {"last_dir":""}

def save_cfg(c):
    try:
        # Never persist API key to JSON — it goes in keyring only
        to_save = {k: v for k, v in c.items() if k != "api_key"}
        with open(CONFIG_FILE, "w") as f:
            json.dump(to_save, f)
    except (IOError, OSError) as e:
        logger.warning("Could not save config: %s", e)

# ── Helpers ───────────────────────────────────────────────────────────────────

def lbl(parent,text,size=11,bold=False,color=TEXT,**kw):
    return ctk.CTkLabel(parent,text=text,
        font=ctk.CTkFont(size=size,weight="bold" if bold else "normal"),
        text_color=color,**kw)

def card_frame(parent,**kw):
    return ctk.CTkFrame(parent,fg_color=CARD,corner_radius=8,**kw)

def sec_lbl(parent,text):
    lbl(parent,text,12,bold=True,color=BLUE).pack(anchor='w',pady=(10,2))

def stat_blk(parent,label_text,val,color=TEXT,tooltip=None):
    f=ctk.CTkFrame(parent,fg_color="transparent"); f.pack(side='left',padx=10)
    l=lbl(f,label_text,9,color=DIM); l.pack()
    v=lbl(f,val,13,bold=True,color=color); v.pack()
    if tooltip:
        _Tooltip(f, tooltip)
    return f

class _Tooltip:
    """Simple hover tooltip for any widget."""
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tw = None
        widget.bind("<Enter>", self._show)
        widget.bind("<Leave>", self._hide)
    def _show(self, event=None):
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self.tw = tw = ctk.CTkToplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.configure(fg_color="#2a3050")
        lbl(tw, self.text, 9, color=TEXT).pack(padx=8, pady=4)
        tw.update_idletasks()
        # Clamp to screen bounds
        sw = tw.winfo_screenwidth()
        sh = tw.winfo_screenheight()
        tw_w = tw.winfo_reqwidth()
        tw_h = tw.winfo_reqheight()
        if x + tw_w > sw:
            x = sw - tw_w - 4
        if y + tw_h > sh:
            y = self.widget.winfo_rooty() - tw_h - 4
        tw.wm_geometry(f"+{x}+{y}")
    def _hide(self, event=None):
        if self.tw:
            self.tw.destroy()
            self.tw = None

class EmbedChart(ctk.CTkFrame):
    def __init__(self,parent,figsize=(9,3),**kw):
        super().__init__(parent,fg_color=PANEL,**kw)
        self.fig=Figure(figsize=figsize,facecolor=PANEL)
        self.canvas=FigureCanvasTkAgg(self.fig,master=self)
        self.canvas.get_tk_widget().pack(fill='both',expand=True)
    def clear(self): self.fig.clear()
    def draw(self): self.canvas.draw()
    def destroy(self):
        plt.close(self.fig)
        super().destroy()
    def std_ax(self,title="",xlabel="Track %"):
        ax=self.fig.add_subplot(111,facecolor='#0d1b2a')
        ax.set_title(title,color=TEXT,fontsize=11,pad=6)
        ax.tick_params(colors=DIM,labelsize=8)
        for sp in ax.spines.values(): sp.set_color('#2a3050')
        ax.spines['top'].set_visible(False); ax.spines['right'].set_visible(False)
        ax.set_xlabel(xlabel,color=DIM,fontsize=9)
        ax.grid(True,alpha=0.1,color='#3a4a6a')
        return ax

class IssueCard(ctk.CTkFrame):
    def __init__(self,parent,issue,**kw):
        super().__init__(parent,fg_color="#1e2845",corner_radius=6,**kw)
        c=SEV_COLOR[issue.severity]
        icon={"critical":"🔴","warning":"🟡","info":"🔵"}[issue.severity.value]
        hdr=ctk.CTkFrame(self,fg_color="transparent",cursor="hand2"); hdr.pack(fill='x',padx=8,pady=5)
        lbl(hdr,f"{icon}  {issue.title}",12,bold=True,color=c,anchor='w').pack(side='left',fill='x',expand=True)
        ctk.CTkLabel(hdr,text=issue.category.value,font=ctk.CTkFont(size=9),
            text_color=DIM,fg_color="#2a3050",corner_radius=4).pack(side='right',padx=4)
        self._d=ctk.CTkFrame(self,fg_color="transparent")
        lbl(self._d,issue.description,11,color=DIM,wraplength=520,justify='left',anchor='w').pack(fill='x',padx=8,pady=(0,3))
        lbl(self._d,f"💡 {issue.recommendation}",11,color=BLUE,wraplength=520,justify='left',anchor='w').pack(fill='x',padx=8,pady=(0,6))
        self._open=False
        for w in [hdr]+list(hdr.winfo_children()): w.bind("<Button-1>",self._toggle)
    def _toggle(self,_=None):
        self._open=not self._open
        (self._d.pack(fill='x') if self._open else self._d.pack_forget())

# ══════════════════════════════════════════════════════════════════════════════
class App(ctk.CTk):
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
        tabs=["Dashboard","Telemetry","Issues","Driver","Sectors",
              "Stint & Tires","Lap Times","Setup Files","AI Advisor","Templates","History","Compare"]
        for t in tabs: self.tv.add(t)
        self.tv.configure(command=self._on_tab_change)
        self._t_dashboard(); self._t_telemetry(); self._t_issues()
        self._t_driver(); self._t_sectors(); self._t_stint()
        self._t_laptimes(); self._t_setup(); self._t_ai()
        self._t_templates(); self._t_history(); self._t_compare()

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

    # ══════════════════════════════════════════════════════════════════════════
    # TELEMETRY
    # ══════════════════════════════════════════════════════════════════════════
    CDEFS={
        "Speed + Throttle + Brake":(['Speed','Throttle','Brake'],['Speed m/s','Throttle','Brake'],[BLUE,GREEN,RED]),
        "Tire Temps (Front)":(['LFtempCL','LFtempCM','LFtempCR','RFtempCL','RFtempCM','RFtempCR'],
                              ['LF-In','LF-Mid','LF-Out','RF-In','RF-Mid','RF-Out'],
                              ['#3498db','#2980b9','#1a5276','#e74c3c','#c0392b','#922b21']),
        "Tire Temps (Rear)":(['LRtempCL','LRtempCM','LRtempCR','RRtempCL','RRtempCM','RRtempCR'],
                             ['LR-In','LR-Mid','LR-Out','RR-In','RR-Mid','RR-Out'],
                             ['#1abc9c','#16a085','#0e6655','#f39c12','#d68910','#9a7d0a']),
        "Suspension Travel":(['LFshockDefl','RFshockDefl','LRshockDefl','RRshockDefl'],['LF','RF','LR','RR'],[BLUE,RED,GREEN,YELLOW]),
        "G-Forces":(['LatAccel','LongAccel'],['Lateral G','Long G'],[ACCENT,BLUE]),
        "G-G Diagram (Friction Circle)":None,  # special scatter renderer
        "Tire Pressures":(['LFpress','RFpress','LRpress','RRpress'],['LF','RF','LR','RR'],[BLUE,RED,GREEN,YELLOW]),
        "RPM + Gear":(['RPM','Gear'],['RPM','Gear'],[BLUE,YELLOW]),
        "Lap Overlay — Speed":None,   # per-lap overlay
        "Lap Overlay — Throttle/Brake":None,
        "Track Map — Speed":None,       # 2D track map colored by speed
        "Track Map — Braking":None,      # 2D track map colored by brake
    }
    _OVERLAY_CHANNELS = {
        "Lap Overlay — Speed": ('Speed', 'Speed (m/s)'),
        "Lap Overlay — Throttle/Brake": (None, ''),  # special: two channels
    }

    def _t_telemetry(self):
        tab=self.tv.tab("Telemetry"); tab.configure(fg_color=DARK)
        self._ph_telem=lbl(tab,"Load a session to view telemetry charts.",14,color=DIM)
        self._ph_telem.pack(pady=40)
        ctrl=ctk.CTkFrame(tab,fg_color=PANEL,height=46,corner_radius=8)
        ctrl.pack(fill='x',padx=10,pady=(8,4)); ctrl.pack_propagate(False)
        lbl(ctrl,"Chart:",color=DIM).pack(side='left',padx=10)
        self._tv=ctk.StringVar(value="Speed + Throttle + Brake")
        ctk.CTkOptionMenu(ctrl,values=list(self.CDEFS.keys()),variable=self._tv,
            fg_color=CARD,button_color=ACCENT,command=self._redraw_telem).pack(side='left',padx=8)
        # Lap selector for overlay modes
        lbl(ctrl,"Laps:",color=DIM).pack(side='left',padx=(16,4))
        self._lap_checks:list[ctk.CTkCheckBox]=[]
        self._lap_frame=ctk.CTkFrame(ctrl,fg_color="transparent")
        self._lap_frame.pack(side='left',padx=4)
        # Replay controls
        replay=ctk.CTkFrame(tab,fg_color=PANEL,height=36,corner_radius=8)
        replay.pack(fill='x',padx=10,pady=(0,2)); replay.pack_propagate(False)
        self._rp_btn=ctk.CTkButton(replay,text="▶ Play",width=70,height=26,fg_color=CARD,
            hover_color="#1a5a8a",command=self._toggle_replay)
        self._rp_btn.pack(side='left',padx=8)
        self._rp_spd=ctk.StringVar(value="1×")
        ctk.CTkOptionMenu(replay,values=["0.5×","1×","2×","4×"],variable=self._rp_spd,
            fg_color=CARD,button_color=ACCENT,width=60).pack(side='left',padx=4)
        self._rp_slider=ctk.CTkSlider(replay,from_=0,to=100,number_of_steps=500,
            fg_color=CARD,progress_color=ACCENT,button_color=BLUE,
            command=self._seek_replay)
        self._rp_slider.pack(side='left',fill='x',expand=True,padx=8)
        self._rp_slider.set(0)
        self._rp_lbl=lbl(replay,"",10,color=DIM)
        self._rp_lbl.pack(side='right',padx=8)
        self._rp_playing=False
        self._rp_pos=0  # current position (0-1 fraction of lap)
        self._rp_line=None  # matplotlib vertical line
        self._rp_last_tick=0.0
        self._tc=EmbedChart(tab,figsize=(10,4)); self._tc.pack(fill='both',expand=True,padx=10,pady=(4,8))

    def _rebuild_lap_checks(self):
        """Populate lap checkboxes when data changes."""
        for w in self._lap_frame.winfo_children(): w.destroy()
        self._lap_checks = []
        if not self.cur_data:
            return
        num = min(self.cur_data.num_laps, 20)  # cap for UI space
        for i in range(num):
            var = ctk.BooleanVar(value=(i == 0))  # first lap checked by default
            cb = ctk.CTkCheckBox(self._lap_frame, text=str(i+1), variable=var,
                width=40, height=22, checkbox_width=16, checkbox_height=16,
                font=ctk.CTkFont(size=9), command=self._redraw_telem)
            cb.pack(side='left', padx=1)
            cb._var = var  # keep reference
            self._lap_checks.append(cb)

    def _get_selected_laps(self) -> list[int]:
        """Return 0-based indices of checked laps."""
        return [i for i, cb in enumerate(self._lap_checks) if cb._var.get()]

    def _redraw_telem(self,sel=None):
        sel=sel or self._tv.get()
        if not self.cur_data: return
        try: self._ph_telem.pack_forget()
        except Exception: pass

        # Special: G-G Diagram scatter plot
        if sel == "G-G Diagram (Friction Circle)":
            self._draw_gg_diagram()
            return

        # Special: Lap overlay modes
        if sel in self._OVERLAY_CHANNELS:
            self._draw_lap_overlay(sel)
            return

        # Special: Track map
        if sel.startswith("Track Map"):
            self._draw_track_map(sel)
            return

        chs,labs,cols=self.CDEFS[sel]
        c=self._tc; c.clear(); ax=c.std_ax(sel)
        ld=self.cur_data.get_channel('LapDistPct')
        x=ld*100 if ld is not None else None
        for ch,lab,col in zip(chs,labs,cols):
            arr=self.cur_data.get_channel(ch)
            if arr is None: continue
            step=max(1,len(arr)//DOWNSAMPLE_CHART)
            xd=x[::step] if x is not None else np.arange(len(arr[::step]))
            ax.plot(xd,arr[::step],label=lab,color=col,lw=1.2,alpha=0.9)
        ax.legend(loc='upper right',fontsize=8,facecolor='#1e2845',edgecolor='#2a3050',labelcolor=TEXT)
        c.fig.tight_layout(pad=1.0); c.draw()

    def _draw_lap_overlay(self, sel: str):
        """Overlay per-lap telemetry traces on the same axes."""
        d = self.cur_data
        if not d or d.num_laps < 1:
            return
        laps = self._get_selected_laps()
        if not laps:
            laps = list(range(min(d.num_laps, 5)))  # default: first 5

        c = self._tc; c.clear()
        palette = ['#e94560','#00b4d8','#2ecc71','#f39c12','#9b59b6',
                   '#e74c3c','#1abc9c','#3498db','#d35400','#8e44ad',
                   '#27ae60','#c0392b','#16a085','#2980b9','#f1c40f',
                   '#e67e22','#2c3e50','#7f8c8d','#1a5276','#922b21']

        lap_dist = d.get_channel('LapDistPct')

        if sel == "Lap Overlay — Throttle/Brake":
            ax = c.std_ax("Lap Overlay — Throttle & Brake")
            for idx, li in enumerate(laps):
                if li >= d.num_laps:
                    continue
                s, e = d.lap_boundaries[li], d.lap_boundaries[li + 1]
                x = lap_dist[s:e] * 100 if lap_dist is not None else np.linspace(0, 100, e - s)
                col = palette[idx % len(palette)]
                thr = d.get_channel('Throttle')
                brk = d.get_channel('Brake')
                step = max(1, (e - s) // DOWNSAMPLE_LAP)
                if thr is not None:
                    ax.plot(x[::step], thr[s:e][::step], color=col, lw=1.2, alpha=0.8, label=f'L{li+1} Thr')
                if brk is not None:
                    ax.plot(x[::step], -brk[s:e][::step], color=col, lw=0.8, alpha=0.5, ls='--')
            ax.set_ylabel("Throttle / -Brake", color=DIM, fontsize=9)
            ax.legend(fontsize=7, facecolor='#1e2845', edgecolor='#2a3050', labelcolor=TEXT, ncol=2, loc='upper right')
        else:
            ch_name, ylabel = self._OVERLAY_CHANNELS[sel]
            ax = c.std_ax(sel)
            arr = d.get_channel(ch_name)
            if arr is None:
                c.draw()
                return
            for idx, li in enumerate(laps):
                if li >= d.num_laps:
                    continue
                s, e = d.lap_boundaries[li], d.lap_boundaries[li + 1]
                x = lap_dist[s:e] * 100 if lap_dist is not None else np.linspace(0, 100, e - s)
                col = palette[idx % len(palette)]
                step = max(1, (e - s) // DOWNSAMPLE_LAP)
                ax.plot(x[::step], arr[s:e][::step], color=col, lw=1.2, alpha=0.85, label=f'Lap {li+1}')
            ax.set_ylabel(ylabel, color=DIM, fontsize=9)
            ax.legend(fontsize=7, facecolor='#1e2845', edgecolor='#2a3050', labelcolor=TEXT, ncol=2, loc='upper right')

        c.fig.tight_layout(pad=1.0)
        c.draw()

    def _draw_gg_diagram(self):
        """Render G-G scatter plot (friction circle) colored by speed."""
        d=self.cur_data
        lat=d.get_channel('LatAccel'); lon=d.get_channel('LongAccel')
        speed=d.get_channel('Speed')
        if lat is None or lon is None: return
        c=self._tc; c.clear()
        ax=c.fig.add_subplot(111,facecolor='#0d1b2a',aspect='equal')
        ax.set_title("G-G Diagram (Friction Circle)",color=TEXT,fontsize=11,pad=6)
        ax.tick_params(colors=DIM,labelsize=8)
        for sp in ax.spines.values(): sp.set_color('#2a3050')
        ax.grid(True,alpha=0.15,color='#3a4a6a')
        # Downsample for performance
        step=max(1,len(lat)//4000)
        lx=lat[::step]; ly=lon[::step]
        if speed is not None:
            sv=speed[::step]*3.6  # m/s → km/h
            sc=ax.scatter(lx,ly,c=sv,cmap='plasma',s=1.5,alpha=0.6,rasterized=True)
            cb=c.fig.colorbar(sc,ax=ax,pad=0.02,shrink=0.8)
            cb.set_label('Speed (km/h)',color=DIM,fontsize=8)
            cb.ax.tick_params(colors=DIM,labelsize=7)
        else:
            ax.scatter(lx,ly,color=BLUE,s=1.5,alpha=0.5,rasterized=True)
        # Draw friction circle reference
        max_g=float(np.percentile(np.sqrt(lx**2+ly**2),99))
        if max_g>0.1:
            theta=np.linspace(0,2*np.pi,100)
            ax.plot(max_g*np.cos(theta),max_g*np.sin(theta),'--',color=RED,lw=1,alpha=0.6,label=f'Max {max_g:.1f} G')
            ax.legend(fontsize=8,facecolor='#1e2845',edgecolor='#2a3050',labelcolor=TEXT)
        ax.set_xlabel("Lateral G",color=DIM,fontsize=9)
        ax.set_ylabel("Longitudinal G",color=DIM,fontsize=9)
        ax.axhline(0,color='#3a4a6a',lw=0.5); ax.axvline(0,color='#3a4a6a',lw=0.5)
        c.fig.tight_layout(pad=1.0); c.draw()

    def _draw_track_map(self, sel: str):
        """Render a 2D track map colored by speed or braking."""
        d = self.cur_data
        if not d: return
        lat = d.get_channel('Lat')
        lon = d.get_channel('Lon')
        speed = d.get_channel('Speed')
        brake = d.get_channel('Brake')
        lap_dist = d.get_channel('LapDistPct')

        # Determine which lap to display (best lap)
        if d.lap_times and len(d.lap_boundaries) >= 2:
            best_idx = int(np.argmin(d.lap_times))
            if best_idx + 1 < len(d.lap_boundaries):
                s, e = d.lap_boundaries[best_idx], d.lap_boundaries[best_idx + 1]
            else:
                s, e = 0, min(len(lap_dist), 5000) if lap_dist is not None else 5000
        else:
            s, e = 0, min(len(lap_dist), 5000) if lap_dist is not None else 5000

        # Try real GPS lat/lon first
        if lat is not None and lon is not None and len(lat) > e:
            x = lon[s:e]
            y = lat[s:e]
            # Reject flat GPS (all same value)
            if np.std(x) < 1e-6 or np.std(y) < 1e-6:
                x = y = None
        else:
            x = y = None

        # Fallback: reconstruct from speed + lateral accel
        track_estimated = False
        if x is None:
            track_estimated = True
            spd = speed[s:e] if speed is not None else None
            la = d.get_channel('LatAccel')
            if spd is not None and la is not None and len(la) > e:
                la_seg = la[s:e]
                dt = 1.0 / max(d.tick_rate, 1)
                heading = np.cumsum(np.where(spd > 1.0, la_seg / np.maximum(spd, 1.0), 0.0) * dt)
                x = np.cumsum(spd * np.cos(heading) * dt)
                y = np.cumsum(spd * np.sin(heading) * dt)
            elif lap_dist is not None:
                # Last resort: simple circle from LapDistPct
                pct = lap_dist[s:e]
                x = np.cos(pct * 2 * np.pi)
                y = np.sin(pct * 2 * np.pi)

        if x is None or y is None:
            return

        c = self._tc; c.clear()
        ax = c.fig.add_subplot(111, facecolor='#0d1b2a', aspect='equal')
        ax.set_title(sel, color=TEXT, fontsize=11, pad=6)
        ax.tick_params(colors=DIM, labelsize=7)
        for sp in ax.spines.values(): sp.set_color('#2a3050')
        ax.set_xticks([]); ax.set_yticks([])
        if track_estimated:
            ax.text(0.5, 0.02, "\u26a0 Estimated track shape (no GPS data)",
                    transform=ax.transAxes, ha='center', fontsize=8,
                    color=YELLOW, alpha=0.8)

        step = max(1, len(x) // DOWNSAMPLE_CHART)
        xs, ys = x[::step], y[::step]

        if "Braking" in sel and brake is not None and len(brake) > e:
            cv = brake[s:e][::step]
            cmap_name = 'Reds'
            clabel = 'Brake Pressure'
        elif speed is not None and len(speed) > e:
            cv = speed[s:e][::step] * 3.6  # km/h
            cmap_name = 'plasma'
            clabel = 'Speed (km/h)'
        else:
            ax.plot(xs, ys, color=BLUE, lw=1.5, alpha=0.9)
            c.fig.tight_layout(pad=0.5); c.draw()
            return

        sc = ax.scatter(xs, ys, c=cv, cmap=cmap_name, s=2, alpha=0.85, rasterized=True)
        cb = c.fig.colorbar(sc, ax=ax, pad=0.02, shrink=0.8)
        cb.set_label(clabel, color=DIM, fontsize=8)
        cb.ax.tick_params(colors=DIM, labelsize=7)
        c.fig.tight_layout(pad=0.5); c.draw()

    def _toggle_replay(self):
        """Start/stop lap replay animation."""
        if self._rp_playing:
            self._rp_playing = False
            self._rp_btn.configure(text="▶ Play")
            return
        if not self.cur_data:
            return
        self._rp_playing = True
        self._rp_btn.configure(text="⏸ Pause")
        self._rp_last_tick = time.perf_counter()
        # Redraw chart first to ensure we have axes
        self._redraw_telem()
        self._replay_tick()

    def _replay_tick(self):
        """Advance replay using time-based delta for frame-rate independence."""
        if not self._rp_playing or not self.cur_data:
            return
        if self.tv.get() != "Telemetry":
            self.after(100, self._replay_tick)
            return
        now = time.perf_counter()
        dt = now - self._rp_last_tick
        self._rp_last_tick = now
        # Speed in fraction-of-session per second
        speed_map = {"0.5×": 0.03, "1×": 0.06, "2×": 0.12, "4×": 0.24}
        rate = speed_map.get(self._rp_spd.get(), 0.06)
        step = rate * dt
        self._rp_pos = min(1.0, self._rp_pos + step)
        self._rp_slider.set(self._rp_pos * 100)
        self._draw_replay_marker(self._rp_pos)
        if self._rp_pos >= 1.0:
            self._rp_playing = False
            self._rp_btn.configure(text="▶ Play")
            self._rp_pos = 0
            return
        self.after(33, self._replay_tick)  # ~30fps

    def _seek_replay(self, val):
        """Handle slider seek."""
        self._rp_pos = float(val) / 100.0
        if not self._rp_playing:
            self._draw_replay_marker(self._rp_pos)

    def _draw_replay_marker(self, pct):
        """Draw a vertical marker on the current telemetry chart at position pct (0-1)."""
        d = self.cur_data
        if not d:
            return
        c = self._tc
        if not c.fig.axes:
            return
        ax = c.fig.axes[0]
        # Remove old marker line
        if self._rp_line and self._rp_line in ax.lines:
            self._rp_line.remove()
            self._rp_line = None
        # Position in track % (0-100)
        xpos = pct * 100.0
        ylim = ax.get_ylim()
        self._rp_line, = ax.plot([xpos, xpos], ylim, color=YELLOW, lw=1.5, alpha=0.8, ls='--')
        # Update readout label
        speed = d.get_channel('Speed')
        throttle = d.get_channel('Throttle')
        brake = d.get_channel('Brake')
        lap_dist = d.get_channel('LapDistPct')
        info_parts = [f"Pos: {pct*100:.1f}%"]
        if lap_dist is not None:
            # Scope lookup to best lap slice to avoid cross-lap misread
            s = e = None
            if d.lap_times and len(d.lap_boundaries) > 1:
                best_li = int(np.argmin(d.lap_times))
                if best_li < len(d.lap_boundaries) - 1:
                    s = d.lap_boundaries[best_li]
                    e = d.lap_boundaries[best_li + 1]
            if s is not None and e is not None:
                seg = lap_dist[s:e]
                idx = s + int(np.argmin(np.abs(seg - pct)))
            else:
                idx = int(np.argmin(np.abs(lap_dist - pct)))
            if speed is not None and idx < len(speed):
                info_parts.append(f"Spd: {speed[idx]*3.6:.0f}km/h")
            if throttle is not None and idx < len(throttle):
                info_parts.append(f"Thr: {throttle[idx]*100:.0f}%")
            if brake is not None and idx < len(brake):
                info_parts.append(f"Brk: {brake[idx]*100:.0f}%")
        self._rp_lbl.configure(text="  |  ".join(info_parts))
        c.canvas.draw_idle()

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
    # STINT & TIRES
    # ══════════════════════════════════════════════════════════════════════════
    def _t_stint(self):
        tab=self.tv.tab("Stint & Tires"); tab.configure(fg_color=DARK)
        self._ph_stint=lbl(tab,"Load a session to see stint & tire analysis.",14,color=DIM)
        self._ph_stint.pack(pady=40)
        self._stsc=ctk.CTkScrollableFrame(tab,fg_color="transparent")
        self._stsc.pack(fill='both',expand=True,padx=10,pady=8)
        self._stpc=EmbedChart(self._stsc,figsize=(10,2.8)); self._stpc.pack(fill='x',pady=(0,4))
        self._stdc=EmbedChart(self._stsc,figsize=(10,2.8)); self._stdc.pack(fill='x',pady=(0,4))
        self._stdf=ctk.CTkFrame(self._stsc,fg_color="transparent"); self._stdf.pack(fill='x')

    def _u_stint(self):
        r=self.cur_stint
        if not r: return
        try: self._ph_stint.pack_forget()
        except Exception: pass
        # Pressure chart
        c=self._stpc; c.clear(); ax=c.std_ax("Tire Pressures — Recommended Cold vs Actual Hot (PSI)",xlabel="Corner")
        corners=['LF','RF','LR','RR']
        cold=[r.pressure_cold_targets.get(co,0) for co in corners]
        hot=[r.pressure_hot_actuals.get(co,0) for co in corners]
        x=np.arange(4)
        ax.bar(x-0.2,cold,0.35,label='Rec. Cold',color=BLUE,alpha=0.85)
        ax.bar(x+0.2,hot,0.35,label='Actual Hot',color=RED,alpha=0.85)
        ax.set_xticks(x); ax.set_xticklabels(corners,color=DIM)
        ax.set_ylabel("PSI",color=DIM,fontsize=8)
        ax.legend(fontsize=8,facecolor='#1e2845',edgecolor='#2a3050',labelcolor=TEXT)
        c.fig.tight_layout(pad=0.8); c.draw()
        # Temp progression
        c2=self._stdc; c2.clear(); ax2=c2.std_ax("Tire Temp Progression by Lap",xlabel="Lap")
        lps=None
        for corner,col in [('LF',BLUE),('RF',RED),('LR',GREEN),('RR',YELLOW)]:
            vals=r.tire_temp_progression.get(corner,[])
            if vals:
                lps=lps or list(range(1,len(vals)+1))
                ax2.plot(lps,vals,marker='o',color=col,label=corner,lw=1.5)
        if r.lap_times and len(r.lap_times)>=3:
            ax2b=ax2.twinx()
            ax2b.plot(range(1,len(r.lap_times)+1),r.lap_times,'--',color='white',alpha=0.4,lw=1,label='Lap time')
            ax2b.set_ylabel("Lap time (s)",color=DIM,fontsize=8); ax2b.tick_params(colors=DIM)
        ax2.legend(fontsize=8,facecolor='#1e2845',edgecolor='#2a3050',labelcolor=TEXT,loc='upper left')
        c2.fig.tight_layout(pad=0.8); c2.draw()
        # Detail
        for w in self._stdf.winfo_children(): w.destroy()
        sec_lbl(self._stdf,"🌡 Cold Pressure Recommendations (to hit hot target)")
        pt=ctk.CTkFrame(self._stdf,fg_color=PANEL,corner_radius=8); pt.pack(fill='x',pady=4)
        cr=ctk.CTkFrame(pt,fg_color="transparent"); cr.pack(fill='x',padx=12,pady=10)
        for corner in ['LF','RF','LR','RR']:
            cf=card_frame(cr); cf.pack(side='left',fill='both',expand=True,padx=4)
            lbl(cf,corner,14,bold=True,color=BLUE).pack(pady=(8,2))
            lbl(cf,f"Cold: {r.pressure_cold_targets.get(corner,0):.1f} PSI",12,bold=True,color=GREEN).pack()
            lbl(cf,f"Hot:  {r.pressure_hot_actuals.get(corner,0):.1f} PSI",11).pack(pady=(0,8))
        if r.findings:
            sec_lbl(self._stdf,"📋 Pressure Findings")
            for fn in r.findings:
                ff=ctk.CTkFrame(self._stdf,fg_color="#1e2845",corner_radius=6); ff.pack(fill='x',pady=2)
                lbl(ff,f"•  {fn}",11,color=TEXT,wraplength=820,justify='left',anchor='w').pack(padx=12,pady=6)
        if r.deg_rate>0:
            sec_lbl(self._stdf,"📉 Degradation")
            dg=ctk.CTkFrame(self._stdf,fg_color=PANEL,corner_radius=8); dg.pack(fill='x',pady=4)
            dr=ctk.CTkFrame(dg,fg_color="transparent"); dr.pack(fill='x',padx=12,pady=10)
            stat_blk(dr,"Deg Rate",f"+{r.deg_rate:.3f}s/lap",YELLOW)
            stat_blk(dr,"Optimal Stint",f"{r.optimal_stint_length} laps",GREEN)
            stat_blk(dr,"Cliff Lap",str(r.cliff_lap),RED)
        # Multi-stint comparison
        self._draw_stint_comparison(self._stdf)

    def _draw_stint_comparison(self, parent):
        """Detect stints (pit boundaries) and compare performance across them."""
        d = self.cur_data
        b = self.cur_best
        if not d or not b or not b.lap_times or len(b.lap_times) < 4:
            return
        lts = b.lap_times
        # Detect stints: split where lap time > 2× median (pit lap) or large gap
        med = np.median(lts)
        stints: list[list[tuple[int, float]]] = []  # list of [(lap_idx, time), ...]
        cur_stint: list[tuple[int, float]] = []
        for i, lt in enumerate(lts):
            if lt > med * 2.0 and cur_stint:
                stints.append(cur_stint)
                cur_stint = []
            else:
                cur_stint.append((i, lt))
        if cur_stint:
            stints.append(cur_stint)
        if len(stints) < 2:
            return  # Only one stint, nothing to compare

        sec_lbl(parent, f"🔄 Multi-Stint Comparison ({len(stints)} stints)")
        # Stats table
        row = ctk.CTkFrame(parent, fg_color="transparent"); row.pack(fill='x', pady=4)
        for si, stint in enumerate(stints):
            times = [t for _, t in stint]
            sf = card_frame(row); sf.pack(side='left', fill='both', expand=True, padx=4, pady=4)
            lbl(sf, f"Stint {si+1}", 13, bold=True, color=BLUE).pack(pady=(8, 3))
            lbl(sf, f"Laps: {stint[0][0]+1}–{stint[-1][0]+1} ({len(stint)})", 10, color=DIM).pack()
            lbl(sf, f"Best: {format_laptime(min(times))}", 11, color=GREEN).pack()
            lbl(sf, f"Avg:  {format_laptime(np.mean(times))}", 11).pack()
            if len(times) >= 3:
                trend = np.polyfit(range(len(times)), times, 1)[0]
                tc = GREEN if trend < -0.02 else RED if trend > 0.02 else TEXT
                lbl(sf, f"Trend: {trend:+.3f}s/lap", 11, color=tc).pack()
            lbl(sf, f"Std: {np.std(times):.3f}s", 10, color=DIM).pack(pady=(0, 8))

        # Overlay chart: all stints
        ch = EmbedChart(parent, figsize=(10, 2.5)); ch.pack(fill='x', pady=4)
        ax = ch.std_ax("Stint-by-Stint Lap Times", xlabel="Lap in Stint")
        colors = [BLUE, RED, GREEN, YELLOW, '#ff69b4', '#00ced1']
        for si, stint in enumerate(stints):
            times = [t for _, t in stint]
            col = colors[si % len(colors)]
            ax.plot(range(1, len(times)+1), times, 'o-', color=col, lw=1.5,
                    label=f"Stint {si+1}", alpha=0.85)
        ax.set_ylabel("seconds", color=DIM, fontsize=8)
        ax.legend(fontsize=8, facecolor='#1e2845', edgecolor='#2a3050', labelcolor=TEXT)
        ch.fig.tight_layout(pad=0.8); ch.draw()

    def _u_fuel(self):
        """Render the fuel strategy section in the Stint & Tires tab."""
        fr = self.cur_fuel
        if not fr or fr.fuel_per_lap_l <= 0:
            return
        f = self._stdf
        sec_lbl(f, "⛽ Fuel Strategy")
        ff = ctk.CTkFrame(f, fg_color=PANEL, corner_radius=8); ff.pack(fill='x', pady=4)
        sr = ctk.CTkFrame(ff, fg_color="transparent"); sr.pack(fill='x', padx=12, pady=10)
        stat_blk(sr, "Fuel/Lap", f"{fr.fuel_per_lap_l:.2f} L", BLUE)
        stat_blk(sr, "Remaining", f"{fr.fuel_remaining_l:.1f} L", GREEN)
        stat_blk(sr, "Laps Left", str(fr.laps_remaining), YELLOW)
        stat_blk(sr, "Tank", f"{fr.fuel_capacity_l:.0f} L", DIM)
        # Race planner input
        sec_lbl(f, "🏁 Race Planner")
        pf = ctk.CTkFrame(f, fg_color=PANEL, corner_radius=8); pf.pack(fill='x', pady=4)
        row = ctk.CTkFrame(pf, fg_color="transparent"); row.pack(fill='x', padx=12, pady=8)
        lbl(row, "Race Length (laps):", color=DIM).pack(side='left')
        self._fuel_laps_var = ctk.StringVar(value="30")
        ctk.CTkEntry(row, textvariable=self._fuel_laps_var, width=70, fg_color=CARD).pack(side='left', padx=8)
        ctk.CTkButton(row, text="Calculate Strategy", height=28, fg_color=ACCENT,
            hover_color="#c0392b", command=self._calc_fuel_strategy).pack(side='left', padx=8)
        self._fuel_result = ctk.CTkFrame(pf, fg_color="transparent")
        self._fuel_result.pack(fill='x', padx=12, pady=(0, 8))

    def _calc_fuel_strategy(self):
        if not self.cur_data:
            return
        try:
            race_laps = int(self._fuel_laps_var.get())
        except ValueError:
            messagebox.showwarning("Invalid Input", "Enter a whole number of laps.")
            return
        if race_laps < 1 or race_laps > 1000:
            messagebox.showwarning("Invalid Input", "Race length must be 1–1000 laps.")
            return
        fr = FuelStrategyAnalyzer().analyze(self.cur_data, race_laps=race_laps)
        # Display results
        for w in self._fuel_result.winfo_children():
            w.destroy()
        if fr.num_stops == 0 and fr.race_laps > 0:
            lbl(self._fuel_result, "✅ No pit stop needed!", 12, bold=True, color=GREEN).pack(anchor='w', pady=4)
        elif fr.num_stops > 0:
            sr = ctk.CTkFrame(self._fuel_result, fg_color="transparent"); sr.pack(fill='x', pady=4)
            stat_blk(sr, "Stops", str(fr.num_stops), ACCENT)
            stat_blk(sr, "Total Fuel", f"{fr.total_fuel_needed_l:.1f} L", BLUE)
            stat_blk(sr, "Finish Fuel", f"{fr.finish_fuel_l:.1f} L", GREEN)
            for i, (pl, fl) in enumerate(zip(fr.pit_laps, fr.fuel_per_stop_l)):
                lbl(self._fuel_result, f"  Stop {i+1}: Pit on lap {pl}, add {fl:.1f} L",
                    11, color=YELLOW).pack(anchor='w', padx=4)
        for fn in fr.findings:
            lbl(self._fuel_result, f"• {fn}", 10, color=DIM, wraplength=780,
                justify='left', anchor='w').pack(anchor='w', padx=4)

    # ══════════════════════════════════════════════════════════════════════════
    # LAP TIMES
    # ══════════════════════════════════════════════════════════════════════════
    def _t_laptimes(self):
        tab=self.tv.tab("Lap Times"); tab.configure(fg_color=DARK)
        self._ph_laptimes=lbl(tab,"Load a session to see lap time analysis.",14,color=DIM)
        self._ph_laptimes.pack(pady=40)
        self._ltsc=ctk.CTkScrollableFrame(tab,fg_color="transparent")
        self._ltsc.pack(fill='both',expand=True,padx=10,pady=8)
        self._ltc=EmbedChart(self._ltsc,figsize=(10,3.5)); self._ltc.pack(fill='x',pady=(0,8))
        self._ltd=ctk.CTkFrame(self._ltsc,fg_color="transparent"); self._ltd.pack(fill='x')

    def _u_laptimes(self):
        r=self.cur_best
        if not r or not r.lap_times: return
        try: self._ph_laptimes.pack_forget()
        except Exception: pass
        c=self._ltc; c.clear(); ax=c.std_ax("Lap Times — Raw vs Fuel Corrected",xlabel="Lap")
        lps=list(range(1,len(r.lap_times)+1))
        ax.plot(lps,r.lap_times,'o-',color=BLUE,label='Raw',lw=1.5)
        if r.fuel_corrected and len(r.fuel_corrected)==len(lps):
            ax.plot(lps,r.fuel_corrected,'s--',color=GREEN,label='Fuel Corrected',lw=1.5,alpha=0.85)
        ax.axhline(r.actual_best,color=RED,lw=1,ls=':',alpha=0.7,label=f'Best {format_laptime(r.actual_best)}')
        ax.set_ylabel("seconds",color=DIM,fontsize=8)
        ax.legend(fontsize=8,facecolor='#1e2845',edgecolor='#2a3050',labelcolor=TEXT)
        c.fig.tight_layout(pad=0.8); c.draw()
        for w in self._ltd.winfo_children(): w.destroy()
        sr=ctk.CTkFrame(self._ltd,fg_color=PANEL,corner_radius=8); sr.pack(fill='x',pady=4)
        sr2=ctk.CTkFrame(sr,fg_color="transparent"); sr2.pack(fill='x',padx=12,pady=10)
        stat_blk(sr2,"Best (Raw)",format_laptime(r.actual_best),GREEN)
        stat_blk(sr2,"Best (FC)",format_laptime(r.fuel_corrected_best),BLUE)
        stat_blk(sr2,"Fuel/Lap",f"{r.fuel_per_lap_kg:.2f} kg" if r.fuel_per_lap_kg else "—")
        tc=GREEN if r.improvement_trend<-0.05 else RED if r.improvement_trend>0.05 else TEXT
        stat_blk(sr2,"Trend",f"{r.improvement_trend:+.3f}s/lap",tc)
        stat_blk(sr2,"Improving?","Yes ↓" if r.laps_improving else "No",GREEN if r.laps_improving else DIM)
        sec_lbl(self._ltd,"📋 Lap-by-Lap")
        fc=r.fuel_corrected or r.lap_times
        rpt_mask=self.cur_rpt.valid_lap_mask if self.cur_rpt and self.cur_rpt.valid_lap_mask else [True]*len(r.lap_times)
        for i,(raw,fcc) in enumerate(zip(r.lap_times,fc)):
            is_outlier=i<len(rpt_mask) and not rpt_mask[i]
            bg="#3a2020" if is_outlier else ("#1e2845" if i%2==0 else PANEL)
            rw=ctk.CTkFrame(self._ltd,fg_color=bg,corner_radius=4)
            rw.pack(fill='x',pady=1)
            delta=raw-r.actual_best
            lbl(rw,f"Lap {i+1}",11,color=DIM).pack(side='left',padx=12,pady=4)
            lbl(rw,format_laptime(raw),11,bold=True,color=GREEN if raw==r.actual_best else (DIM if is_outlier else TEXT)).pack(side='left',padx=8)
            lbl(rw,f"+{delta:.3f}s" if delta>0 else "BEST",10,color=YELLOW if delta>0 else GREEN).pack(side='left',padx=8)
            lbl(rw,f"FC: {format_laptime(fcc)}",10,color=BLUE).pack(side='left',padx=8)
            if is_outlier: lbl(rw,"⚠ outlier",9,color=YELLOW).pack(side='left',padx=8)

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
                        best_report=self.cur_best):
                    if cancel.is_set():
                        return
                    self.after(0, lambda c=chunk: self._on_ai_chunk(c))
            except Exception as ex:
                logger.warning("AI streaming failed: %s", ex)
                if not cancel.is_set():
                    self.after(0, lambda: self._on_ai_chunk(
                        "\n\n⚠ AI request failed. Check your API key and internet connection.\n"))
            if not cancel.is_set():
                self.after(0, self._on_ai_done)
        t = threading.Thread(target=worker, daemon=True)
        t.start()
        def _ai_timeout():
            if t.is_alive():
                cancel.set()
                self.after(0, lambda: (
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
            self.sessions.pop(0)
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
                            "Sectors","Stint & Tires","Lap Times"}
        self._refresh_active_tab()

    def _refresh_active_tab(self):
        tab = self.tv.get()
        self._stale_tabs.discard(tab)
        _updaters = {
            "Dashboard": self._u_dashboard,
            "Telemetry": self._redraw_telem,
            "Issues": self._pop_issues,
            "Driver": self._u_driver,
            "Sectors": self._draw_sectors,
            "Stint & Tires": lambda: (self._u_stint(), self._u_fuel()),
            "Lap Times": self._u_laptimes,
        }
        updater = _updaters.get(tab)
        if updater:
            updater()

    def _on_tab_change(self):
        tab = self.tv.get()
        if hasattr(self, '_stale_tabs') and tab in self._stale_tabs:
            self._refresh_active_tab()

    def _u_cmp_menus(self):
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
