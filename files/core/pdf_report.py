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

from core.ibt_parser import TelemetryData
from core.analysis_engine import AnalysisReport, Severity, format_laptime
from core.advanced_analysis import SectorAnalysisReport, BestLapReport, TireDegReport
from core.driving_style import DriverStyleReport


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


def _make_laptime_chart(report: AnalysisReport, best_report: BestLapReport) -> Optional[RLImage]:
    if len(report.lap_times) < 2:
        return None
    try:
        fig = Figure(figsize=(6, 2.2), facecolor='white')
        ax = fig.add_subplot(111)
        ax.set_facecolor('#f8f9fa')
        laps = list(range(1, len(report.lap_times) + 1))
        ax.plot(laps, report.lap_times, 'o-', color='#1a1a2e', linewidth=1.5, markersize=4, label='Lap time')
        if best_report.fuel_corrected and len(best_report.fuel_corrected) == len(laps):
            ax.plot(laps, best_report.fuel_corrected, 's--', color='#00b4d8', linewidth=1.2,
                    markersize=3, alpha=0.8, label='Fuel corrected')
        ax.axhline(report.best_lap, color='#2ecc71', linestyle=':', linewidth=1, alpha=0.7)
        ax.set_xlabel("Lap", fontsize=9)
        ax.set_ylabel("Time (s)", fontsize=9)
        ax.set_title("Lap Time Progression", fontsize=10)
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)
        ax.tick_params(labelsize=8)
        fig.tight_layout(pad=0.5)

        buf = BytesIO()
        fig.savefig(buf, format='png', dpi=120)
        buf.seek(0)
        return RLImage(buf, width=5.5*inch, height=2.0*inch)
    except Exception:
        logger.warning("Failed to generate lap time chart", exc_info=True)
        return None
    finally:
        fig.clear()


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


def generate_pdf_report(
    output_path: str,
    data: TelemetryData,
    report: AnalysisReport,
    sector_report: Optional[SectorAnalysisReport] = None,
    best_report: Optional[BestLapReport] = None,
    tire_deg: Optional[TireDegReport] = None,
    driver_report: Optional[DriverStyleReport] = None,
    ai_text: str = "",
) -> str:
    """Generate a complete PDF session report. Returns output_path."""

    styles, custom = _make_styles()
    story = []

    # ── Header ────────────────────────────────────────────────────────
    story.append(_header_table(data.car_name, data.track_name, data.session_info))
    story.append(Spacer(1, 12))

    # ── Summary row ───────────────────────────────────────────────────
    best_str = format_laptime(report.best_lap)
    avg_str = format_laptime(report.avg_lap)
    bal = report.balance_score
    bal_str = ("Understeer" if bal < -0.2 else "Oversteer" if bal > 0.2 else "Neutral")

    summary_data = [
        ['Best Lap', 'Avg Lap', 'Laps', 'Balance', 'Issues Found'],
        [best_str, avg_str, str(data.num_laps),
         bal_str,
         f"{report.critical_count} Crit / {report.warning_count} Warn / {report.info_count} Info"],
    ]
    st = Table(summary_data, colWidths=[1.2*inch, 1.2*inch, 0.8*inch, 1.2*inch, 2.6*inch])
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
    story.append(Spacer(1, 10))

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

    if best_report.improvement_trend:
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

        if sector_report.theoretical_best > 0:
            story.append(Paragraph(
                f"Theoretical best: <b>{format_laptime(sector_report.theoretical_best)}</b> &nbsp;|&nbsp; "
                f"Actual best: <b>{format_laptime(sector_report.actual_best)}</b> &nbsp;|&nbsp; "
                f"Time left on table: <b>+{sector_report.time_left_on_table:.3f}s</b>",
                custom['Body']))

        chart = _make_sector_chart(sector_report)
        if chart:
            story.append(chart)

    # ── Tire Temperatures ─────────────────────────────────────────────
    story.append(Spacer(1, 10))
    story.append(Paragraph("Tire Temperatures", custom['SectionHead']))
    story.append(HRFlowable(width="100%", thickness=0.5, color=ACCENT))
    story.append(Spacer(1, 6))

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

    # ── AI Advisor ────────────────────────────────────────────────────
    if ai_text:
        story.append(PageBreak())
        story.append(Paragraph("AI Setup Advisor", custom['SectionHead']))
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
        "Generated by iRacing Setup Advisor — For sim racing use only.",
        ParagraphStyle('Footer', parent=custom['Small'], alignment=TA_CENTER)))

    # ── Build PDF ─────────────────────────────────────────────────────
    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        leftMargin=0.75*inch, rightMargin=0.75*inch,
        topMargin=0.75*inch, bottomMargin=0.75*inch,
        title=f"Setup Report — {data.car_name} @ {data.track_name}",
        author="iRacing Setup Advisor",
    )
    doc.build(story)
    return output_path
