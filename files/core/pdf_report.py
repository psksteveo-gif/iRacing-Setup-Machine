"""
PDF Session Report Generator
Uses ReportLab to generate professional session reports.
"""

import os
import io
import logging
from datetime import datetime
from typing import Optional
import numpy as np

logger = logging.getLogger(__name__)

from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak, KeepTogether
)
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import Flowable
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.figure import Figure
from io import BytesIO
from reportlab.platypus import Image as RLImage

from typing import List
from core.ibt_parser import TelemetryData
from core.analysis_engine import AnalysisReport, Severity, format_laptime
from core.advanced_analysis import SectorAnalysisReport, BestLapReport, TireDegReport
from core.driving_style import DriverStyleReport
from core.consistency_score import ConsistencyBreakdown

# Optional rich-analysis types — imported conditionally so pdf_report has no hard deps on them
try:
    from core.steering_torque import SteeringTorqueReport
except ImportError:
    SteeringTorqueReport = None  # type: ignore
try:
    from core.fuel_economy import FuelEconomyReport
except ImportError:
    FuelEconomyReport = None  # type: ignore
try:
    from core.brake_pressure import BrakePressureReport
except ImportError:
    BrakePressureReport = None  # type: ignore
try:
    from core.vehicle_dynamics import DynamicsReport, AidTrackingReport, ShiftAnalysis
    from core.vehicle_dynamics import WheelSlipReport, KerbReport  # type: ignore
except ImportError:
    DynamicsReport = AidTrackingReport = ShiftAnalysis = None  # type: ignore
    WheelSlipReport = KerbReport = None  # type: ignore
try:
    from core.setup_optimizer import OptimizationResult
except ImportError:
    OptimizationResult = None  # type: ignore


# ── Colors ────────────────────────────────────────────────────────────────────
DARK = colors.HexColor('#1a1a2e')
PANEL = colors.HexColor('#16213e')
ACCENT = colors.HexColor('#e94560')
ACCENT2 = colors.HexColor('#00b4d8')
GREEN = colors.HexColor('#2ecc71')
YELLOW = colors.HexColor('#f39c12')
RED = colors.HexColor('#e74c3c')
LIGHT_GRAY = colors.HexColor('#f0f2f5')
MID_GRAY = colors.HexColor('#8a8fa3')
TEXT_DARK = colors.HexColor('#1a1a2e')


def _make_styles():
    styles = getSampleStyleSheet()
    custom = {
        'ReportTitle': ParagraphStyle('ReportTitle', parent=styles['Title'],
                                       fontSize=22, textColor=DARK,
                                       spaceAfter=4, alignment=TA_LEFT),
        'SectionHead': ParagraphStyle('SectionHead', parent=styles['Heading1'],
                                       fontSize=13, textColor=ACCENT,
                                       spaceBefore=14, spaceAfter=4,
                                       borderPad=2),
        'SubHead': ParagraphStyle('SubHead', parent=styles['Heading2'],
                                   fontSize=11, textColor=colors.HexColor('#0f3460'),
                                   spaceBefore=8, spaceAfter=2),
        'Body': ParagraphStyle('Body', parent=styles['Normal'],
                                fontSize=10, textColor=TEXT_DARK,
                                leading=14, spaceAfter=3),
        'Small': ParagraphStyle('Small', parent=styles['Normal'],
                                 fontSize=9, textColor=MID_GRAY, leading=12),
        'Verdict': ParagraphStyle('Verdict', parent=styles['Normal'],
                                   fontSize=11, textColor=colors.HexColor('#1a4a1a'),
                                   backColor=colors.HexColor('#e8f8e8'),
                                   borderPad=6, leading=15),
        'Critical': ParagraphStyle('Critical', parent=styles['Normal'],
                                    fontSize=10, textColor=RED, leading=13),
        'Warning': ParagraphStyle('Warning', parent=styles['Normal'],
                                   fontSize=10, textColor=YELLOW, leading=13),
        'Info': ParagraphStyle('Info', parent=styles['Normal'],
                                fontSize=10, textColor=ACCENT2, leading=13),
    }
    styles.add(custom['ReportTitle'])
    for k, v in custom.items():
        if k != 'ReportTitle':
            try:
                styles.add(v)
            except Exception:
                pass
    return styles, custom


def _header_table(car: str, track: str, session_info: dict) -> Table:
    track_temp = session_info.get('track_temp_c', '—')
    air_temp = session_info.get('air_temp_c', '—')
    config = session_info.get('track_config', '')
    track_full = f"{track} — {config}" if config else track
    now = datetime.now().strftime("%d %b %Y, %H:%M")

    data = [
        [Paragraph(f"<b>{car.replace('_', ' ').title()}</b>", ParagraphStyle('H', fontSize=14, textColor=colors.white)),
         Paragraph(f"<b>Track:</b> {track_full}", ParagraphStyle('H2', fontSize=10, textColor=colors.white)),
         Paragraph(f"Track: {track_temp}°C  |  Air: {air_temp}°C", ParagraphStyle('H3', fontSize=9, textColor=colors.HexColor('#aaaaaa'))),
         Paragraph(f"Generated: {now}", ParagraphStyle('H4', fontSize=9, textColor=colors.HexColor('#aaaaaa'), alignment=TA_RIGHT))],
    ]
    t = Table(data, colWidths=[2.2*inch, 2.5*inch, 1.8*inch, 1.5*inch])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), DARK),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    return t


def _lap_table(report: AnalysisReport, best_report: BestLapReport, styles, custom) -> Table:
    rows = [['Lap', 'Lap Time', 'Fuel Corrected', 'Delta to Best', 'Status']]
    best = report.best_lap
    corrected = best_report.fuel_corrected

    for i, t in enumerate(report.lap_times[:15]):
        delta = t - best
        corr = corrected[i] if i < len(corrected) else t
        status = "BEST" if t == best else ("+%.3fs" % delta)
        color = '#2ecc71' if t == best else ('#e74c3c' if delta > 2 else '#333333')
        rows.append([
            str(i + 1),
            format_laptime(t),
            format_laptime(corr),
            f"+{delta:.3f}s" if delta > 0 else "—",
            status,
        ])

    tbl = Table(rows, colWidths=[0.5*inch, 1.2*inch, 1.4*inch, 1.2*inch, 1.2*inch])
    style = [
        ('BACKGROUND', (0, 0), (-1, 0), DARK),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#dddddd')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, LIGHT_GRAY]),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]
    # Highlight best lap
    for i, t in enumerate(report.lap_times[:15]):
        if t == best:
            style.append(('BACKGROUND', (0, i+1), (-1, i+1), colors.HexColor('#d5f5e3')))
            style.append(('TEXTCOLOR', (0, i+1), (-1, i+1), colors.HexColor('#1a7a40')))
    tbl.setStyle(TableStyle(style))
    return tbl


def _tire_table(tire_summary: Optional[dict], styles, custom) -> Optional[Table]:
    if not tire_summary:
        return None
    rows = [['Corner', 'Inner °C', 'Mid °C', 'Outer °C', 'Avg °C', 'Status']]
    for corner in ['LF', 'RF', 'LR', 'RR']:
        temps = tire_summary.get(corner, {})
        if not temps:
            continue
        inner = temps.get('inner', 0)
        mid = temps.get('mid', 0)
        outer = temps.get('outer', 0)
        avg = temps.get('avg', 0)
        delta = abs(inner - outer)
        status = "OK" if delta < 12 else ("CAMBER ⚠" if delta < 20 else "CRITICAL ✗")
        rows.append([corner, f"{inner:.1f}", f"{mid:.1f}", f"{outer:.1f}", f"{avg:.1f}", status])

    t = Table(rows, colWidths=[0.7*inch, 1.0*inch, 1.0*inch, 1.0*inch, 1.0*inch, 1.3*inch])
    style = [
        ('BACKGROUND', (0, 0), (-1, 0), PANEL),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#dddddd')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, LIGHT_GRAY]),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]
    for i, corner in enumerate(['LF', 'RF', 'LR', 'RR']):
        temps = tire_summary.get(corner, {})
        delta = abs(temps.get('inner', 0) - temps.get('outer', 0))
        if delta > 20:
            style.append(('TEXTCOLOR', (-1, i+1), (-1, i+1), RED))
        elif delta > 12:
            style.append(('TEXTCOLOR', (-1, i+1), (-1, i+1), YELLOW))
        else:
            style.append(('TEXTCOLOR', (-1, i+1), (-1, i+1), GREEN))
    t.setStyle(TableStyle(style))
    return t


def _fmt_axis_time(s, _pos=None):
    """Matplotlib tick formatter: M:SS for ≥60s, else Xs."""
    m = int(s // 60)
    sec = s - m * 60
    return f"{m}:{sec:05.2f}" if m > 0 else f"{sec:.1f}s"


def _make_laptime_chart(report: AnalysisReport, best_report: BestLapReport) -> Optional[RLImage]:
    if len(report.lap_times) < 2:
        return None
    try:
        import matplotlib.ticker as mticker
        # Filter out extreme outlier laps (< 60% of best lap — incomplete/pit laps)
        threshold = report.best_lap * 0.6
        filtered_times = [t for t in report.lap_times if t >= threshold]
        filtered_laps  = [i + 1 for i, t in enumerate(report.lap_times) if t >= threshold]
        if len(filtered_laps) < 2:
            filtered_times = report.lap_times
            filtered_laps  = list(range(1, len(report.lap_times) + 1))

        fig = Figure(figsize=(6, 2.2), facecolor='white')
        ax = fig.add_subplot(111)
        ax.set_facecolor('#f8f9fa')
        ax.plot(filtered_laps, filtered_times, 'o-', color='#1a1a2e',
                linewidth=1.5, markersize=4, label='Lap time')
        if best_report.fuel_corrected and len(best_report.fuel_corrected) == len(report.lap_times):
            fc_filtered = [best_report.fuel_corrected[i - 1] for i in filtered_laps
                           if best_report.fuel_corrected[i - 1] >= threshold]
            fc_laps_filtered = [i for i in filtered_laps
                                if best_report.fuel_corrected[i - 1] >= threshold]
            if fc_laps_filtered:
                ax.plot(fc_laps_filtered, fc_filtered, 's--', color='#00b4d8',
                        linewidth=1.2, markersize=3, alpha=0.8, label='Fuel corrected')
        if report.best_lap >= threshold:
            ax.axhline(report.best_lap, color='#2ecc71', linestyle=':', linewidth=1, alpha=0.7)
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(_fmt_axis_time))
        ax.set_xlabel("Lap", fontsize=9)
        ax.set_ylabel("Lap Time", fontsize=9)
        ax.set_title("Lap Time Progression", fontsize=10)
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)
        ax.tick_params(labelsize=8)
        fig.tight_layout(pad=0.8)

        buf = BytesIO()
        fig.savefig(buf, format='png', dpi=120, bbox_inches='tight')
        buf.seek(0)
        return RLImage(buf, width=5.5*inch, height=2.0*inch)
    except Exception:
        logger.warning("Failed to generate lap time chart", exc_info=True)
        return None
    finally:
        fig.clear()


def _make_balance_chart(report: AnalysisReport) -> Optional[RLImage]:
    """Four balance gauges: Overall, Entry, Mid, Exit."""
    try:
        fig = Figure(figsize=(6.5, 1.5), facecolor='white')
        phases = [
            ("Overall",   report.balance_score),
            ("Entry",     report.balance_entry),
            ("Mid-Corner",report.balance_mid),
            ("Exit",      report.balance_exit),
        ]
        for idx, (name, val) in enumerate(phases):
            ax = fig.add_subplot(1, 4, idx + 1)
            ax.set_facecolor('#f8f9fa'); ax.axis('off')
            grad = np.linspace(-1, 1, 200).reshape(1, -1)
            ax.imshow(grad, aspect='auto', cmap='RdYlGn_r',
                      extent=(-1, 1, -0.2, 0.2), vmin=-1, vmax=1)
            ax.axvline(val, color='black', lw=2.5, zorder=5)
            ax.set_xlim(-1.5, 1.5); ax.set_ylim(-0.6, 0.6)
            verdict = "US" if val < -0.15 else "OS" if val > 0.15 else "OK"
            v_color = '#c0392b' if verdict == 'US' else '#27ae60' if verdict == 'OS' else '#2980b9'
            ax.text(0, 0.42, verdict, ha='center', fontsize=9, fontweight='bold', color=v_color)
            ax.text(-1.2, -0.45, "US", fontsize=7, color='#27ae60')
            ax.text(0.9, -0.45, "OS", fontsize=7, color='#c0392b')
            ax.set_title(name, fontsize=8, pad=2)
        fig.suptitle("Balance  (US = Understeer / OS = Oversteer)", fontsize=8, y=0.04)
        fig.tight_layout(pad=0.3)
        buf = BytesIO(); fig.savefig(buf, format='png', dpi=130); buf.seek(0)
        return RLImage(buf, width=5.8*inch, height=1.3*inch)
    except Exception:
        logger.warning("Failed to generate balance chart", exc_info=True)
        return None
    finally:
        try: fig.clear()
        except Exception: pass


def _make_tire_heatmap_chart(tire_summary: dict) -> Optional[RLImage]:
    """4-corner tire temp heatmap (inner / mid / outer per corner)."""
    if not tire_summary:
        return None
    try:
        import matplotlib.cm as _cm
        fig = Figure(figsize=(5.5, 1.9), facecolor='white')
        ax = fig.add_subplot(111)
        ax.set_facecolor('white'); ax.axis('off')
        ax.set_title("Tire Temperature Map (°C) — Inner / Mid / Outer", fontsize=9, pad=3)
        cmap = _cm.RdYlGn_r
        # layout: [LF  RF]  top row;  [LR  RR]  bottom row
        positions = {'LF': (0, 1.3), 'RF': (2.1, 1.3),
                     'LR': (0, 0.0), 'RR': (2.1, 0.0)}
        zones = ['inner', 'mid', 'outer']
        for corner, (cx, cy) in positions.items():
            temps = tire_summary.get(corner, {})
            for zi, zone in enumerate(zones):
                temp = temps.get(zone, 75.0)
                norm_v = max(0.0, min(1.0, (temp - 65.0) / 50.0))
                color = cmap(norm_v)
                rect = mpatches.Rectangle((cx + zi * 0.46, cy), 0.42, 0.95,
                                          facecolor=color, edgecolor='white', lw=1.2)
                ax.add_patch(rect)
                ax.text(cx + zi * 0.46 + 0.21, cy + 0.475, f"{temp:.0f}",
                        ha='center', va='center', fontsize=7,
                        color='white', fontweight='bold')
            ax.text(cx + 0.63, cy + 0.475, corner, ha='left', va='center',
                    fontsize=9, fontweight='bold', color='#1a1a2e')
            avg = temps.get('avg', 0.0)
            ax.text(cx + 0.63, cy + 0.05, f"avg {avg:.1f}°", ha='left', va='bottom',
                    fontsize=7, color='#555555')
        ax.set_xlim(-0.2, 4.2); ax.set_ylim(-0.3, 2.7)
        fig.tight_layout(pad=0.3)
        buf = BytesIO(); fig.savefig(buf, format='png', dpi=130); buf.seek(0)
        return RLImage(buf, width=5.0*inch, height=1.7*inch)
    except Exception:
        logger.warning("Failed to generate tire heatmap", exc_info=True)
        return None
    finally:
        try: fig.clear()
        except Exception: pass


def _make_balance_timeline_chart(balance_timeline: list) -> Optional[RLImage]:
    """Per-lap balance bar chart."""
    if len(balance_timeline) < 2:
        return None
    try:
        fig = Figure(figsize=(6.5, 1.5), facecolor='white')
        ax = fig.add_subplot(111)
        ax.set_facecolor('#f8f9fa')
        laps = list(range(1, len(balance_timeline) + 1))
        colors = ['#c0392b' if v < -0.05 else '#27ae60' if v > 0.05 else '#2980b9'
                  for v in balance_timeline]
        ax.bar(laps, balance_timeline, color=colors, alpha=0.82, width=0.65)
        ax.axhline(0, color='#555', lw=0.8, ls='--')
        ax.axhspan(-0.05, 0.05, color='#aaaaee', alpha=0.15)
        ax.set_xlim(0.3, len(laps) + 0.7); ax.set_ylim(-1.1, 1.1)
        ax.set_xlabel("Lap", fontsize=8); ax.tick_params(labelsize=7)
        ax.set_ylabel("← US  |  OS →", fontsize=7)
        ax.set_title("Balance Timeline — per lap", fontsize=9)
        ax.grid(True, axis='y', alpha=0.3)
        fig.tight_layout(pad=0.5)
        buf = BytesIO(); fig.savefig(buf, format='png', dpi=120); buf.seek(0)
        return RLImage(buf, width=5.8*inch, height=1.3*inch)
    except Exception:
        logger.warning("Failed to generate balance timeline chart", exc_info=True)
        return None
    finally:
        try: fig.clear()
        except Exception: pass


def _make_sector_chart(sector_report: SectorAnalysisReport) -> Optional[RLImage]:
    if not sector_report.sectors:
        return None
    try:
        fig = Figure(figsize=(5.5, 2.0), facecolor='white')
        ax = fig.add_subplot(111)
        ax.set_facecolor('#f8f9fa')
        sectors = sector_report.sectors
        x = [f"S{s.sector_num+1}" for s in sectors]
        avg_times = [s.avg_time for s in sectors]
        best_times = [s.best_time for s in sectors]
        w = 0.35
        xs = np.arange(len(x))
        ax.bar(xs - w/2, avg_times, w, label='Avg', color='#1a1a2e', alpha=0.8)
        ax.bar(xs + w/2, best_times, w, label='Best', color='#2ecc71', alpha=0.8)
        ax.set_xticks(xs)
        ax.set_xticklabels(x)
        ax.set_title("Sector Time Comparison", fontsize=10)
        ax.set_ylabel("Time (s)", fontsize=9)
        ax.legend(fontsize=8)
        ax.tick_params(labelsize=8)
        ax.grid(True, axis='y', alpha=0.3)
        fig.tight_layout(pad=0.5)
        buf = BytesIO()
        fig.savefig(buf, format='png', dpi=120)
        buf.seek(0)
        return RLImage(buf, width=4.5*inch, height=1.8*inch)
    except Exception:
        logger.warning("Failed to generate sector chart", exc_info=True)
        return None
    finally:
        fig.clear()


def _make_track_map_image(data, best_lap_idx: int = 0) -> Optional[RLImage]:
    """Render a speed-coloured racing line for the best lap."""
    try:
        from core.racing_line import reconstruct_racing_line, speed_colormap
        from matplotlib.collections import LineCollection
        rl = reconstruct_racing_line(data, best_lap_idx)
        if rl is None:
            return None
        fig = Figure(figsize=(3.5, 2.5), facecolor='#1a1a2e')
        ax = fig.add_subplot(111, facecolor='#1a1a2e')
        # Build (N-1, 2, 2) segments for LineCollection
        pts = np.column_stack([rl.x, rl.y]).reshape(-1, 1, 2)
        segs = np.concatenate([pts[:-1], pts[1:]], axis=1)
        lc = LineCollection(segs, colors=speed_colormap(rl.speed[:-1]),
                            linewidths=1.8, capstyle='round')
        ax.add_collection(lc)
        ax.autoscale()
        ax.set_aspect('equal', 'datalim')
        ax.axis('off')
        src = rl.source.upper()
        ax.set_title(f"Racing Line  [{src}]", fontsize=8, color='#cccccc', pad=3)
        fig.tight_layout(pad=0.3)
        buf = BytesIO()
        fig.savefig(buf, format='png', dpi=120, facecolor='#1a1a2e')
        buf.seek(0)
        return RLImage(buf, width=3.2*inch, height=2.3*inch)
    except Exception:
        logger.warning("Failed to generate track map image", exc_info=True)
        return None
    finally:
        try: fig.clear()
        except Exception: pass


def _make_lap_delta_image(data, best_lap_idx: int = 0,
                          second_lap_idx: int = 1) -> Optional[RLImage]:
    """Render a cumulative lap delta chart (best vs 2nd-best)."""
    if data.num_laps < 2:
        return None
    try:
        from core.corner_analysis import LapDeltaAnalyzer
        result = LapDeltaAnalyzer().analyze(data, best_lap_idx, second_lap_idx)
        if result is None:
            return None
        fig = Figure(figsize=(5.5, 1.8), facecolor='white')
        ax = fig.add_subplot(111)
        ax.set_facecolor('#f8f9fa')
        x = result.dist_pct * 100
        y = result.delta_s
        ax.fill_between(x, y, 0, where=(y >= 0),
                        color='#e74c3c', alpha=0.55, label='Cmp slower')
        ax.fill_between(x, y, 0, where=(y < 0),
                        color='#2ecc71', alpha=0.55, label='Cmp faster')
        ax.plot(x, y, color='#333333', linewidth=0.8, alpha=0.6)
        ax.axhline(0, color='#555555', linewidth=0.8)
        ax.set_xlabel("Track %", fontsize=8)
        ax.set_ylabel("Delta (s)", fontsize=8)
        ax.set_title(
            f"Lap Delta — Lap {best_lap_idx+1} (ref) vs Lap {second_lap_idx+1}",
            fontsize=9)
        ax.legend(fontsize=7, loc='upper right')
        ax.tick_params(labelsize=7)
        ax.grid(True, alpha=0.25)
        fig.tight_layout(pad=0.4)
        buf = BytesIO()
        fig.savefig(buf, format='png', dpi=120)
        buf.seek(0)
        return RLImage(buf, width=5.2*inch, height=1.6*inch)
    except Exception:
        logger.warning("Failed to generate lap delta image", exc_info=True)
        return None
    finally:
        try: fig.clear()
        except Exception: pass


def _make_torque_chart(torque_rpt) -> Optional[RLImage]:
    """US/OS heatmap bars across track position."""
    if not torque_rpt or not torque_rpt.has_data:
        return None
    try:
        us = np.asarray(torque_rpt.understeer_map, dtype=float)
        os_ = np.asarray(torque_rpt.oversteer_map, dtype=float)
        if len(us) == 0:
            return None
        x = np.linspace(0, 100, len(us))
        fig = Figure(figsize=(6.5, 1.6), facecolor='white')
        ax = fig.add_subplot(111)
        ax.set_facecolor('#f8f9fa')
        ax.fill_between(x, us, alpha=0.75, color='#e74c3c', label=f'Understeer ({torque_rpt.us_fraction:.0%})')
        ax.fill_between(x, -os_, alpha=0.75, color='#f39c12', label=f'Oversteer ({torque_rpt.os_fraction:.0%})')
        ax.axhline(0, color='#aaaaaa', lw=0.6)
        ax.set_xlim(0, 100); ax.set_xlabel("Track %", fontsize=8)
        ax.set_ylabel("Intensity", fontsize=8)
        ax.set_title("Steering Torque Balance Map  (US ↑ / OS ↓)", fontsize=9)
        ax.legend(fontsize=7, loc='upper right')
        ax.tick_params(labelsize=7)
        fig.tight_layout(pad=0.4)
        buf = BytesIO(); fig.savefig(buf, format='png', dpi=120); buf.seek(0)
        return RLImage(buf, width=5.8*inch, height=1.4*inch)
    except Exception:
        logger.warning("Failed to generate torque chart", exc_info=True)
        return None
    finally:
        try: fig.clear()
        except Exception: pass


def _make_fuel_eco_chart(fuel_rpt) -> Optional[RLImage]:
    """Per-lap fuel use bars."""
    if not fuel_rpt or not fuel_rpt.has_data or not fuel_rpt.lap_records:
        return None
    try:
        laps = [r.lap + 1 for r in fuel_rpt.lap_records]
        used = [r.fuel_used_l for r in fuel_rpt.lap_records]
        avg  = fuel_rpt.avg_fuel_per_lap_l
        fig = Figure(figsize=(6.5, 1.8), facecolor='white')
        ax = fig.add_subplot(111)
        ax.set_facecolor('#f8f9fa')
        bar_colors = ['#e74c3c' if u > avg * 1.05 else '#27ae60' if u < avg * 0.95 else '#2980b9' for u in used]
        ax.bar(laps, used, color=bar_colors, alpha=0.8, width=0.7)
        ax.axhline(avg, color='#555555', lw=1.2, ls='--', label=f'Avg {avg:.3f} L')
        ax.set_xlabel("Lap", fontsize=8); ax.set_ylabel("Fuel Used (L)", fontsize=8)
        ax.set_title("Fuel Economy — Per Lap", fontsize=9)
        ax.legend(fontsize=7)
        ax.tick_params(labelsize=7)
        ax.grid(True, axis='y', alpha=0.3)
        fig.tight_layout(pad=0.4)
        buf = BytesIO(); fig.savefig(buf, format='png', dpi=120); buf.seek(0)
        return RLImage(buf, width=5.8*inch, height=1.6*inch)
    except Exception:
        logger.warning("Failed to generate fuel economy chart", exc_info=True)
        return None
    finally:
        try: fig.clear()
        except Exception: pass


def _make_brake_map_chart(brake_rpt) -> Optional[RLImage]:
    """LF/RF brake pressure map across track position."""
    if not brake_rpt or not brake_rpt.has_data:
        return None
    try:
        lf = np.asarray(brake_rpt.lf_pressure_map, dtype=float)
        rf = np.asarray(brake_rpt.rf_pressure_map, dtype=float)
        if len(lf) == 0:
            return None
        x = np.linspace(0, 100, len(lf))
        fig = Figure(figsize=(6.5, 1.6), facecolor='white')
        ax = fig.add_subplot(111)
        ax.set_facecolor('#f8f9fa')
        if brake_rpt.has_lf:
            ax.plot(x, lf, color='#3498db', lw=1.2, label='LF')
        if brake_rpt.has_rf:
            ax.plot(x, rf, color='#e74c3c', lw=1.2, label='RF')
        for fz in brake_rpt.fade_zones:
            ax.axvline(fz * 100, color='#f39c12', lw=1, ls=':', alpha=0.8)
        ax.set_xlabel("Track %", fontsize=8); ax.set_ylabel("Pressure (kPa)", fontsize=8)
        ax.set_title("Brake Line Pressure Map", fontsize=9)
        ax.legend(fontsize=7)
        ax.tick_params(labelsize=7)
        ax.grid(True, alpha=0.25)
        fig.tight_layout(pad=0.4)
        buf = BytesIO(); fig.savefig(buf, format='png', dpi=120); buf.seek(0)
        return RLImage(buf, width=5.8*inch, height=1.4*inch)
    except Exception:
        logger.warning("Failed to generate brake map chart", exc_info=True)
        return None
    finally:
        try: fig.clear()
        except Exception: pass


def _setup_result_table(opt_result, setup_checklist, styles, custom, title: str, is_fixed: bool) -> list:
    """Build story elements for one optimizer result (open or fixed)."""
    story = []
    badge_color = colors.HexColor('#7f3f98') if is_fixed else PANEL
    story.append(Paragraph(
        f"<b>{'🔒 ' if is_fixed else '⚙ '}{title}</b>",
        ParagraphStyle('OptHead', parent=custom['Body'],
                       backColor=badge_color, textColor=colors.white,
                       fontName='Helvetica-Bold', borderPad=5, spaceBefore=4)))
    story.append(Spacer(1, 3))
    story.append(Paragraph(opt_result.description, custom['Small']))
    story.append(Spacer(1, 4))

    if setup_checklist:
        rows = [['Parameter', 'Change', 'Expected Effect']]
        for item in setup_checklist:
            arrow = '▲' if item.direction == 'increase' else '▼'
            rows.append([item.label, f"{arrow} {item.display}", item.hint])
        tbl = Table(rows, colWidths=[1.8*inch, 1.1*inch, 4.1*inch])
        tbl.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), PANEL),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('ALIGN', (1, 0), (1, -1), 'CENTER'),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (2, 0), (2, -1), 'LEFT'),
            ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#cccccc')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, LIGHT_GRAY]),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('FONTNAME', (1, 1), (1, -1), 'Helvetica-Bold'),
        ]))
        for ri, item in enumerate(setup_checklist, start=1):
            c = colors.HexColor('#e8f8e8') if item.direction == 'increase' else colors.HexColor('#fde8e8')
            tbl.setStyle(TableStyle([('BACKGROUND', (1, ri), (1, ri), c)]))
        story.append(tbl)
    else:
        # Fallback: raw changes from optimizer
        rows = [['Parameter', 'Delta', 'Direction']]
        for ch in opt_result.changes:
            delta = ch.get('delta', 0)
            rows.append([ch.get('parameter', ''), f"{delta:+.1f}", '▲ Increase' if delta > 0 else '▼ Decrease'])
        tbl = Table(rows, colWidths=[2.5*inch, 1.2*inch, 3.3*inch])
        tbl.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), PANEL),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('ALIGN', (1, 0), (1, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#cccccc')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, LIGHT_GRAY]),
        ]))
        story.append(tbl)

    story.append(Spacer(1, 8))
    return story


def generate_pdf_report(
    output_path: str,
    data: TelemetryData,
    report: AnalysisReport,
    sector_report: Optional[SectorAnalysisReport] = None,
    best_report: Optional[BestLapReport] = None,
    tire_deg: Optional[TireDegReport] = None,
    driver_report: Optional[DriverStyleReport] = None,
    ai_text: str = "",
    consistency: Optional[ConsistencyBreakdown] = None,
    ml_result=None,
    session_note: str = "",
    setup_checklist: Optional[List] = None,
    # Extended analysis
    opt_result=None,
    opt_result_fixed=None,
    torque_report=None,
    fuel_eco_report=None,
    brake_press_report=None,
    dyn_report=None,
    aid_report=None,
    shift_report=None,
    slip_report=None,
    kerb_report=None,
    engineer_report=None,
) -> str:
    """Generate a complete PDF session report. Returns output_path."""

    styles, custom = _make_styles()
    story = []

    # Pre-compute best / 2nd-best lap indices for chart helpers
    _best_lap_idx = 0
    _second_lap_idx = 1
    if report.lap_times and len(report.lap_times) >= 2:
        _sorted = sorted(range(len(report.lap_times)), key=lambda i: report.lap_times[i])
        _best_lap_idx = _sorted[0]
        _second_lap_idx = _sorted[1]

    # ── Header ────────────────────────────────────────────────────────
    story.append(_header_table(data.car_name, data.track_name, data.session_info))
    story.append(Spacer(1, 12))

    # ── Summary row ───────────────────────────────────────────────────
    best_str = format_laptime(report.best_lap)
    avg_str = format_laptime(report.avg_lap)
    bal = report.balance_score
    bal_str = ("Understeer" if bal < -0.2 else "Oversteer" if bal > 0.2 else "Neutral")

    con_str = (f"{consistency.overall:.0f}/100 ({consistency.grade})"
               if consistency else "—")
    car_class_str = report.car_class.upper().replace('_', ' ') if report.car_class != 'default' else ''

    summary_data = [
        ['Best Lap', 'Avg Lap', 'Laps', 'Consistency', 'Balance', 'Issues Found'],
        [best_str, avg_str, str(data.num_laps), con_str,
         bal_str,
         f"{report.critical_count} Crit / {report.warning_count} Warn / {report.info_count} Info"],
    ]
    st = Table(summary_data, colWidths=[1.1*inch, 1.1*inch, 0.7*inch, 1.4*inch, 1.1*inch, 2.6*inch])
    st.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), ACCENT),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTNAME', (0, 1), (-1, 1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('BACKGROUND', (0, 1), (-1, 1), LIGHT_GRAY),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#dddddd')),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(st)
    story.append(Spacer(1, 6))

    # Car class badge
    if car_class_str:
        story.append(Paragraph(
            f"Car Class: <b>{car_class_str}</b>",
            ParagraphStyle('CC', parent=custom['Small'],
                           textColor=colors.HexColor('#6c3483'),
                           fontName='Helvetica-Bold')))
        story.append(Spacer(1, 4))

    # ── Session Note (AI-generated) ───────────────────────────────────
    if session_note:
        story.append(Paragraph("Session Note", custom['SubHead']))
        story.append(Paragraph(session_note, custom['Verdict']))
        story.append(Spacer(1, 6))

    # ── ML Prediction ─────────────────────────────────────────────────
    if ml_result is not None:
        pred_str = format_laptime(ml_result.predicted_lap_s)
        delta = ml_result.delta_vs_actual
        delta_str = (f"{delta:+.3f}s — {ml_result.insight}" if abs(delta) > 0.01
                     else "Near theoretical pace for these conditions.")
        story.append(Paragraph(
            f"🤖 ML Predicted Pace: <b>{pred_str}</b>  |  {delta_str}  "
            f"(confidence {ml_result.confidence:.0%}, n={ml_result.n_sessions} sessions)",
            custom['Small']))
        story.append(Spacer(1, 6))

    # ── Lap Times ─────────────────────────────────────────────────────
    story.append(Paragraph("Lap Times", custom['SectionHead']))
    story.append(HRFlowable(width="100%", thickness=0.5, color=ACCENT))
    story.append(Spacer(1, 6))

    if best_report is None:
        from core.advanced_analysis import BestLapReport
        best_report = BestLapReport(lap_times=report.lap_times,
                                     fuel_corrected=report.lap_times,
                                     actual_best=report.best_lap,
                                     fuel_corrected_best=report.best_lap)

    lap_chart = _make_laptime_chart(report, best_report)
    if lap_chart:
        story.append(lap_chart)
        story.append(Spacer(1, 6))

    story.append(_lap_table(report, best_report, styles, custom))

    delta_img = _make_lap_delta_image(data, _best_lap_idx, _second_lap_idx)
    if delta_img:
        trend_block = [Spacer(1, 8), delta_img]
        if best_report.improvement_trend:
            trend_str = (f"Improving {abs(best_report.improvement_trend):.3f}s/lap ✓"
                         if best_report.improvement_trend < -0.05
                         else f"Degrading {best_report.improvement_trend:.3f}s/lap")
            trend_block.append(Spacer(1, 4))
            trend_block.append(Paragraph(f"Trend: {trend_str}", custom['Small']))
        story.append(KeepTogether(trend_block))
    elif best_report.improvement_trend:
        trend_str = (f"Improving {abs(best_report.improvement_trend):.3f}s/lap ✓"
                     if best_report.improvement_trend < -0.05
                     else f"Degrading {best_report.improvement_trend:.3f}s/lap")
        story.append(Spacer(1, 4))
        story.append(Paragraph(f"Trend: {trend_str}", custom['Small']))

    # ── Sector Analysis ───────────────────────────────────────────────
    if sector_report and sector_report.sectors:
        story.append(Spacer(1, 10))
        story.append(Paragraph("Sector Analysis", custom['SectionHead']))
        story.append(HRFlowable(width="100%", thickness=0.5, color=ACCENT))
        story.append(Spacer(1, 6))

        sec_block = []
        if sector_report.theoretical_best > 0:
            sec_block.append(Paragraph(
                f"Theoretical best: <b>{format_laptime(sector_report.theoretical_best)}</b> &nbsp;|&nbsp; "
                f"Actual best: <b>{format_laptime(sector_report.actual_best)}</b> &nbsp;|&nbsp; "
                f"Time left on table: <b>+{sector_report.time_left_on_table:.3f}s</b>",
                custom['Body']))
            sec_block.append(Spacer(1, 6))

        chart = _make_sector_chart(sector_report)
        if chart:
            sec_block.append(chart)
        if sec_block:
            story.append(KeepTogether(sec_block))

    # ── Balance Analysis ──────────────────────────────────────────────
    story.append(Spacer(1, 10))
    story.append(Paragraph("Balance Analysis", custom['SectionHead']))
    story.append(HRFlowable(width="100%", thickness=0.5, color=ACCENT))
    story.append(Spacer(1, 6))
    bal_chart = _make_balance_chart(report)
    if bal_chart:
        story.append(bal_chart)
        story.append(Spacer(1, 4))
    if report.balance_timeline:
        bal_timeline = _make_balance_timeline_chart(report.balance_timeline)
        if bal_timeline:
            story.append(bal_timeline)
            story.append(Spacer(1, 4))

    # ── Tire Temperatures ─────────────────────────────────────────────
    story.append(Spacer(1, 6))
    story.append(Paragraph("Tire Temperatures", custom['SectionHead']))
    story.append(HRFlowable(width="100%", thickness=0.5, color=ACCENT))
    story.append(Spacer(1, 6))
    heatmap = _make_tire_heatmap_chart(report.tire_summary)
    if heatmap:
        story.append(heatmap)
        story.append(Spacer(1, 4))
    tire_tbl = _tire_table(report.tire_summary, styles, custom)
    if tire_tbl:
        story.append(tire_tbl)
    else:
        story.append(Paragraph("No tire temperature data available.", custom['Small']))

    # ── Pressure Recommendations ──────────────────────────────────────
    if tire_deg and tire_deg.pressure_cold_targets:
        story.append(Spacer(1, 8))
        story.append(Paragraph("Tire Pressure Recommendations (Cold Set)", custom['SubHead']))
        p = tire_deg.pressure_cold_targets
        h = tire_deg.pressure_hot_actuals
        rows = [['Corner', 'Actual Hot PSI', 'Target Hot PSI', 'Recommended Cold PSI']]
        from core.car_classifier import classify_car, PRESSURE_TARGETS
        targets = PRESSURE_TARGETS[classify_car(data.car_name)]
        for corner in ['LF', 'RF', 'LR', 'RR']:
            rows.append([corner,
                         f"{h.get(corner, 0):.1f}" if corner in h else "—",
                         f"{targets.get(corner, 32):.1f}",
                         f"{p.get(corner, 0):.1f}"])
        pt = Table(rows, colWidths=[0.8*inch, 1.4*inch, 1.4*inch, 1.8*inch])
        pt.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), PANEL),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#dddddd')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, LIGHT_GRAY]),
            ('BACKGROUND', (-1, 1), (-1, -1), colors.HexColor('#e8f4fd')),
            ('FONTNAME', (-1, 1), (-1, -1), 'Helvetica-Bold'),
        ]))
        story.append(pt)

    # ── Engineer Notes ────────────────────────────────────────────────
    if engineer_report:
        story.append(PageBreak())
        story.append(Paragraph("Race Engineer Analysis", custom['SectionHead']))
        story.append(HRFlowable(width="100%", thickness=0.5, color=ACCENT))
        story.append(Spacer(1, 6))
        story.append(Paragraph(
            "The following findings are derived from your telemetry data and presented "
            "as plain-language observations — the kind an engineer would walk you through "
            "before or after a session.",
            custom['Body']
        ))
        story.append(Spacer(1, 8))

        _pri_label = {1: "MUST ADDRESS", 2: "IMPORTANT", 3: "WORTH NOTING"}
        _pri_color = {
            1: colors.HexColor('#e74c3c'),
            2: colors.HexColor('#f39c12'),
            3: colors.HexColor('#3498db'),
        }
        _cat_label = {
            'pace': 'Pace', 'technique': 'Technique', 'consistency': 'Consistency',
            'setup': 'Setup', 'fuel': 'Fuel', 'tires': 'Tires', 'info': 'Info',
        }

        for finding in engineer_report:
            pri_col = _pri_color.get(finding.priority, colors.grey)
            pri_text = _pri_label.get(finding.priority, "NOTE")
            cat_text = _cat_label.get(finding.category, finding.category.title())
            gain_text = (f"  (~{finding.time_gain_s:.2f}s available)"
                         if finding.time_gain_s >= 0.05 else "")

            header_style = ParagraphStyle(
                'EngHdr',
                parent=custom['Body'],
                textColor=pri_col,
                fontName='Helvetica-Bold',
                fontSize=10,
                spaceBefore=4,
                spaceAfter=2,
            )
            title_style = ParagraphStyle(
                'EngTitle',
                parent=custom['Body'],
                fontName='Helvetica-Bold',
                fontSize=11,
                spaceAfter=2,
            )
            block = [
                Paragraph(f"[{pri_text}]  {cat_text}{gain_text}", header_style),
                Paragraph(finding.title, title_style),
                Paragraph(finding.body, custom['Body']),
                Spacer(1, 8),
            ]
            story.append(KeepTogether(block))

    # ── Issues ────────────────────────────────────────────────────────
    story.append(PageBreak())
    story.append(Paragraph("Setup Issues & Recommendations", custom['SectionHead']))
    story.append(HRFlowable(width="100%", thickness=0.5, color=ACCENT))
    story.append(Spacer(1, 6))

    sev_style = {
        Severity.CRITICAL: custom['Critical'],
        Severity.WARNING: custom['Warning'],
        Severity.INFO: custom['Info'],
    }
    sev_icon = {Severity.CRITICAL: "🔴 CRITICAL", Severity.WARNING: "🟡 WARNING", Severity.INFO: "🔵 INFO"}

    for issue in report.issues:
        block = []
        label = sev_icon[issue.severity]
        block.append(Paragraph(f"<b>{label}: {issue.title}</b>", sev_style[issue.severity]))
        block.append(Paragraph(issue.description, custom['Body']))
        block.append(Paragraph(f"<b>Recommendation:</b> {issue.recommendation}",
                                ParagraphStyle('Rec', parent=custom['Body'],
                                               textColor=colors.HexColor('#0f3460'))))
        block.append(Spacer(1, 6))
        story.append(KeepTogether(block))

    # ── Setup Optimizer Recommendations ──────────────────────────────
    _has_opt = opt_result is not None and opt_result.changes
    _has_opt_fixed = opt_result_fixed is not None and opt_result_fixed.changes
    _has_checklist = bool(setup_checklist)

    if _has_opt or _has_checklist:
        story.append(Spacer(1, 8))
        story.append(Paragraph("Recommended Setup Changes", custom['SectionHead']))
        story.append(HRFlowable(width="100%", thickness=0.5, color=ACCENT))
        story.append(Spacer(1, 4))
        story.append(Paragraph(
            "Adjustments derived from telemetry analysis and the GA optimizer. "
            "Apply in your iRacing garage before the next session.",
            custom['Small']))
        story.append(Spacer(1, 6))

    # Open-setup block (detailed checklist or raw changes)
    if _has_opt:
        try:
            from core.setup_recommend import build_checklist
            _open_cl = build_checklist(opt_result.changes, None) if not _has_checklist else setup_checklist
        except Exception:
            _open_cl = None
        story.extend(_setup_result_table(opt_result, _open_cl, styles, custom,
                                         "Open Setup Recommendations", is_fixed=False))
    elif _has_checklist:
        # Legacy path: checklist passed without opt_result
        story.append(Paragraph("<b>⚙ Open Setup Recommendations</b>",
                                ParagraphStyle('OptHead', parent=custom['Body'],
                                               backColor=PANEL, textColor=colors.white,
                                               fontName='Helvetica-Bold', borderPad=5)))
        story.append(Spacer(1, 4))
        tab_order = ['TIRES/AERO', 'CHASSIS', 'DAMPERS', '']
        seen_tabs = []
        for item in setup_checklist:
            tab = (item.garage_tab or '').upper()
            if tab not in seen_tabs:
                seen_tabs.append(tab)
        ordered_tabs = [t for t in tab_order if t in seen_tabs] + \
                       [t for t in seen_tabs if t not in tab_order]
        tab_colors = {'TIRES/AERO': colors.HexColor('#1a3a5c'),
                      'CHASSIS': colors.HexColor('#3a1a5c'),
                      'DAMPERS': colors.HexColor('#1a5c3a')}
        for tab in ordered_tabs:
            items = [i for i in setup_checklist if (i.garage_tab or '').upper() == tab]
            if not items: continue
            tab_label = tab if tab else 'OTHER'
            story.append(Paragraph(f"<b>{'⚙ ' + tab_label}</b>",
                ParagraphStyle('TabHead', parent=custom['Body'],
                               backColor=tab_colors.get(tab, PANEL), textColor=colors.white,
                               fontName='Helvetica-Bold', borderPad=4, spaceBefore=6)))
            story.append(Spacer(1, 2))
            rows = [['Parameter', 'Change', 'Current', 'Target', 'Expected Effect']]
            for item in items:
                arr = '▲' if item.direction == 'increase' else '▼'
                rows.append([item.label, f"{arr} {item.display}",
                              item.current_value or '—', item.recommended_value or '—', item.hint])
            col_w = [1.6*inch, 0.9*inch, 0.8*inch, 0.8*inch, 2.9*inch]
            tbl = Table(rows, colWidths=col_w)
            tbl.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), PANEL), ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('ALIGN', (1, 0), (3, -1), 'CENTER'), ('ALIGN', (0, 0), (0, -1), 'LEFT'),
                ('ALIGN', (4, 0), (4, -1), 'LEFT'), ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#cccccc')),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, LIGHT_GRAY]),
                ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ('FONTNAME', (1, 1), (1, -1), 'Helvetica-Bold'),
            ]))
            for ri, item in enumerate(items, start=1):
                c = colors.HexColor('#e8f8e8') if item.direction == 'increase' else colors.HexColor('#fde8e8')
                tbl.setStyle(TableStyle([('BACKGROUND', (1, ri), (1, ri), c)]))
            story.append(tbl); story.append(Spacer(1, 6))

    # Fixed-setup block
    if _has_opt_fixed:
        try:
            from core.setup_recommend import build_checklist
            _fixed_cl = build_checklist(opt_result_fixed.changes, None)
        except Exception:
            _fixed_cl = None
        story.extend(_setup_result_table(opt_result_fixed, _fixed_cl, styles, custom,
                                         "Fixed Setup Recommendations (In-Car Adjustments Only)",
                                         is_fixed=True))

    # ── Driving Style ─────────────────────────────────────────────────
    if driver_report:
        story.append(Spacer(1, 6))
        story.append(Paragraph("Driving Style Analysis", custom['SectionHead']))
        story.append(HRFlowable(width="100%", thickness=0.5, color=ACCENT))
        story.append(Spacer(1, 6))

        scores = [
            ('Brake Consistency', driver_report.brake_consistency),
            ('Throttle Smoothness', driver_report.throttle_smoothness),
            ('Steering Smoothness', driver_report.steering_smoothness),
            ('Trail Braking', driver_report.trail_braking_score),
            ('Stability Management', driver_report.oversteer_management),
            ('Overall', driver_report.overall_score),
        ]
        score_rows = [['Metric', 'Score', 'Grade']]
        for name, score in scores:
            grade = 'A' if score >= 85 else 'B' if score >= 70 else 'C' if score >= 55 else 'D'
            score_rows.append([name, f"{score:.0f}/100", grade])

        dt = Table(score_rows, colWidths=[2.5*inch, 1.2*inch, 0.8*inch])
        dt.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), PANEL),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#dddddd')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, LIGHT_GRAY]),
            ('BACKGROUND', (0, len(scores)), (-1, len(scores)), colors.HexColor('#e8f4fd')),
            ('FONTNAME', (0, len(scores)), (-1, len(scores)), 'Helvetica-Bold'),
        ]))
        story.append(dt)

        if driver_report.style_profile:
            story.append(Spacer(1, 6))
            story.append(Paragraph(f"Style: <i>{driver_report.style_profile}</i>", custom['Body']))
        if driver_report.balance_verdict:
            story.append(Paragraph(f"Balance verdict: <b>{driver_report.balance_verdict}</b>", custom['Body']))

        if driver_report.recommendations:
            story.append(Spacer(1, 4))
            story.append(Paragraph("Driver Recommendations:", custom['SubHead']))
            for rec in driver_report.recommendations:
                story.append(Paragraph(f"• {rec}", custom['Body']))

    # ── Advanced Analysis Page ────────────────────────────────────────
    _has_adv = any([
        dyn_report and getattr(dyn_report, 'has_attitude_data', False),
        torque_report and getattr(torque_report, 'has_data', False),
        brake_press_report and getattr(brake_press_report, 'has_data', False),
        fuel_eco_report and getattr(fuel_eco_report, 'has_data', False),
        aid_report and getattr(aid_report, 'has_data', False),
        shift_report and getattr(shift_report, 'has_data', False),
    ])
    if _has_adv:
        story.append(PageBreak())
        story.append(Paragraph("Advanced Telemetry Analysis", custom['SectionHead']))
        story.append(HRFlowable(width="100%", thickness=0.5, color=ACCENT))
        story.append(Spacer(1, 6))

        # ── Roll / Pitch Dynamics ─────────────────────────────────────
        if dyn_report and getattr(dyn_report, 'has_attitude_data', False):
            story.append(Paragraph("Body Dynamics (Roll / Pitch)", custom['SubHead']))
            dyn_rows = [
                ['Metric', 'Peak', 'Average', 'Summary'],
                ['Body Roll', f"{dyn_report.max_roll_deg:.1f}°", f"{dyn_report.avg_roll_deg:.1f}°", dyn_report.roll_summary],
                ['Pitch', f"{dyn_report.max_pitch_deg:.1f}°", f"{dyn_report.avg_pitch_deg:.1f}°", dyn_report.pitch_summary],
            ]
            dt = Table(dyn_rows, colWidths=[1.2*inch, 1.0*inch, 1.0*inch, 4.8*inch])
            dt.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), PANEL), ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('ALIGN', (1, 0), (2, -1), 'CENTER'), ('ALIGN', (0, 0), (0, -1), 'LEFT'),
                ('ALIGN', (3, 0), (3, -1), 'LEFT'),
                ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#cccccc')),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, LIGHT_GRAY]),
                ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ]))
            story.append(dt); story.append(Spacer(1, 8))

        # ── Steering Torque Balance ───────────────────────────────────
        if torque_report and getattr(torque_report, 'has_data', False):
            story.append(Paragraph("Steering Torque Balance", custom['SubHead']))
            story.append(Paragraph(
                f"Understeer: <b>{torque_report.us_fraction:.0%}</b> &nbsp;|&nbsp; "
                f"Oversteer: <b>{torque_report.os_fraction:.0%}</b> &nbsp;|&nbsp; "
                f"Avg: <b>{torque_report.avg_torque_nm:.1f} N·m</b> &nbsp;|&nbsp; "
                f"Peak: <b>{torque_report.peak_torque_nm:.1f} N·m</b>",
                custom['Body']))
            if torque_report.balance_summary:
                story.append(Paragraph(torque_report.balance_summary, custom['Body']))
            if torque_report.setup_hint:
                story.append(Paragraph(f"Setup hint: <i>{torque_report.setup_hint}</i>", custom['Small']))
            t_chart = _make_torque_chart(torque_report)
            if t_chart:
                story.append(Spacer(1, 4)); story.append(t_chart)
            story.append(Spacer(1, 8))

        # ── Brake Pressure ────────────────────────────────────────────
        if brake_press_report and getattr(brake_press_report, 'has_data', False):
            story.append(Paragraph("Brake Pressure Analysis", custom['SubHead']))
            bp = brake_press_report
            story.append(Paragraph(
                f"Peak: <b>{bp.peak_pressure_kpa:.0f} kPa</b> &nbsp;|&nbsp; "
                f"Avg application: <b>{bp.avg_application_kpa:.0f} kPa</b> &nbsp;|&nbsp; "
                f"Hard brakes: <b>{bp.hard_brake_count}</b> &nbsp;|&nbsp; "
                f"LF share: <b>{bp.avg_lf_fraction:.0%}</b> &nbsp;RF share: <b>{bp.avg_rf_fraction:.0%}</b>",
                custom['Body']))
            if abs(bp.bias_vs_setting) > 0.02:
                direction = "more" if bp.bias_vs_setting > 0 else "less"
                story.append(Paragraph(
                    f"⚠ Actual bias {direction} front than dc setting by {abs(bp.bias_vs_setting):.0%}",
                    custom['Warning']))
            if bp.fade_count > 0:
                story.append(Paragraph(
                    f"🔥 Brake fade detected in <b>{bp.fade_count}</b> zone(s) — "
                    f"check pad/fluid temps and cooling",
                    custom['Critical']))
            if bp.summary:
                story.append(Paragraph(bp.summary, custom['Small']))
            b_chart = _make_brake_map_chart(brake_press_report)
            if b_chart:
                story.append(Spacer(1, 4)); story.append(b_chart)
            story.append(Spacer(1, 8))

        # ── Fuel Economy ──────────────────────────────────────────────
        if fuel_eco_report and getattr(fuel_eco_report, 'has_data', False):
            story.append(Paragraph("Fuel Economy", custom['SubHead']))
            fe = fuel_eco_report
            story.append(Paragraph(
                f"Avg per lap: <b>{fe.avg_fuel_per_lap_l:.3f} L</b> &nbsp;|&nbsp; "
                f"Total used: <b>{fe.total_fuel_used_l:.2f} L</b> &nbsp;|&nbsp; "
                f"Best economy: Lap <b>{fe.best_economy_lap + 1}</b> &nbsp;|&nbsp; "
                f"Worst: Lap <b>{fe.worst_economy_lap + 1}</b>",
                custom['Body']))
            if fe.hot_zones:
                zone_strs = [f"{s*100:.0f}–{e*100:.0f}% ({lph:.1f} L/hr)"
                             for s, e, lph in fe.hot_zones[:3]]
                story.append(Paragraph(f"High-consumption zones: {', '.join(zone_strs)}", custom['Small']))
            if fe.coast_opportunities:
                opp_strs = [f"{s*100:.0f}–{e*100:.0f}%" for s, e in fe.coast_opportunities[:3]]
                story.append(Paragraph(f"Lift-and-coast opportunities: {', '.join(opp_strs)}", custom['Small']))
            f_chart = _make_fuel_eco_chart(fuel_eco_report)
            if f_chart:
                story.append(Spacer(1, 4)); story.append(f_chart)
            story.append(Spacer(1, 8))

        # ── Driver Aids ───────────────────────────────────────────────
        if aid_report and getattr(aid_report, 'has_data', False):
            story.append(Paragraph("Driver Aid Adjustments", custom['SubHead']))
            if aid_report.summary:
                story.append(Paragraph(aid_report.summary, custom['Body']))
            _bb = aid_report.brake_bias_range
            _tc = aid_report.tc_range
            _abs = aid_report.abs_range
            aid_info = []
            if _bb != (0.0, 0.0):
                aid_info.append(f"Brake Bias: {_bb[0]:.3f}–{_bb[1]:.3f}")
            if _tc != (0.0, 0.0):
                aid_info.append(f"TC: {_tc[0]:.0f}–{_tc[1]:.0f}")
            if _abs != (0.0, 0.0):
                aid_info.append(f"ABS: {_abs[0]:.0f}–{_abs[1]:.0f}")
            if aid_info:
                story.append(Paragraph("Ranges used: " + "  |  ".join(aid_info), custom['Small']))
            if aid_report.adjustments:
                adj_rows = [['Lap', 'Track %', 'Aid', 'Old', 'New', 'Delta']]
                for a in aid_report.adjustments[:15]:
                    adj_rows.append([str(a.lap), f"{a.lap_dist_pct:.0%}",
                                     a.aid, f"{a.old_value}", f"{a.new_value}",
                                     f"{a.delta:+.3f}"])
                at = Table(adj_rows, colWidths=[0.5*inch, 0.7*inch, 1.0*inch, 0.9*inch, 0.9*inch, 0.8*inch])
                at.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), PANEL), ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), ('FONTSIZE', (0, 0), (-1, -1), 8),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#cccccc')),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, LIGHT_GRAY]),
                ]))
                story.append(Spacer(1, 4)); story.append(at)
            story.append(Spacer(1, 8))

        # ── Shift Analysis ────────────────────────────────────────────
        if shift_report and getattr(shift_report, 'has_data', False):
            story.append(Paragraph("Shift Analysis", custom['SubHead']))
            sh = shift_report
            story.append(Paragraph(
                f"Total shifts: <b>{sh.shift_count}</b> &nbsp;|&nbsp; "
                f"Avg RPM: <b>{sh.avg_shift_rpm:.0f}</b> &nbsp;|&nbsp; "
                f"Optimal RPM: <b>{sh.optimal_shift_rpm:.0f}</b> &nbsp;|&nbsp; "
                f"Early: <b>{sh.early_shift_count}</b> &nbsp;Late: <b>{sh.late_shift_count}</b>",
                custom['Body']))
            if sh.summary:
                story.append(Paragraph(sh.summary, custom['Small']))
            story.append(Spacer(1, 8))

    # ── AI Advisor ────────────────────────────────────────────────────
    if ai_text:
        story.append(PageBreak())
        story.append(Paragraph("Optimal Sector", custom['SectionHead']))
        story.append(HRFlowable(width="100%", thickness=0.5, color=ACCENT))
        story.append(Spacer(1, 6))
        for line in ai_text.split('\n'):
            line = line.strip()
            if not line:
                story.append(Spacer(1, 4))
                continue
            if line.startswith('**') and line.endswith('**'):
                story.append(Paragraph(f"<b>{line[2:-2]}</b>",
                                        ParagraphStyle('AH', parent=custom['Body'],
                                                       textColor=ACCENT, fontName='Helvetica-Bold')))
            else:
                clean = line.replace('**', '<b>', 1).replace('**', '</b>', 1)
                story.append(Paragraph(clean, custom['Body']))

    # ── Footer note ───────────────────────────────────────────────────
    story.append(Spacer(1, 20))
    story.append(HRFlowable(width="100%", thickness=0.5, color=MID_GRAY))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        "Generated by Optimal Sector — For sim racing use only.",
        ParagraphStyle('Footer', parent=custom['Small'], alignment=TA_CENTER)))

    # ── Build PDF ─────────────────────────────────────────────────────
    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        leftMargin=0.75*inch, rightMargin=0.75*inch,
        topMargin=0.75*inch, bottomMargin=0.75*inch,
        title=f"Setup Report — {data.car_name} @ {data.track_name}",
        author="Optimal Sector",
    )
    doc.build(story)
    return output_path
