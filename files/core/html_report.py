"""
HTML Report Generator
=====================
Generates a self-contained HTML file with embedded charts and statistics
from a session. The report can be shared or opened in any browser without
requiring the app to be installed.
"""

from __future__ import annotations

import base64
import io
import os
from datetime import datetime
from typing import Optional

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches


def generate_html_report(
    output_path: str,
    data,        # TelemetryData
    report,      # AnalysisReport
    sector_report=None,
    best_report=None,
    driver_report=None,
    stint_report=None,
    fuel_report=None,
    session_note: str = "",
    app_version: str = "",
) -> None:
    """Generate a shareable HTML report and write to output_path."""
    charts = {}

    # ── Chart 1: Lap times ────────────────────────────────────────────────────
    if report and report.lap_times:
        charts['lap_times'] = _chart_lap_times(report.lap_times, report.valid_lap_mask)

    # ── Chart 2: Tire temps heatmap ───────────────────────────────────────────
    if report and report.tire_summary:
        charts['tire_temps'] = _chart_tire_temps(report.tire_summary)

    # ── Chart 3: Sector comparison ────────────────────────────────────────────
    if sector_report and sector_report.sectors:
        charts['sectors'] = _chart_sectors(sector_report)

    # ── Chart 4: Driver scores radar ─────────────────────────────────────────
    if driver_report:
        charts['driver'] = _chart_driver_radar(driver_report)

    html = _build_html(data, report, sector_report, driver_report, stint_report,
                       fuel_report, session_note, app_version, charts)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)


# ── Chart generators ──────────────────────────────────────────────────────────

def _chart_lap_times(lap_times, valid_mask=None) -> str:
    fig, ax = plt.subplots(figsize=(9, 3), facecolor='#0c0a12')
    ax.set_facecolor('#100c18')
    laps = list(range(1, len(lap_times) + 1))
    mask = valid_mask or [True] * len(lap_times)
    colors = ['#2ecc71' if (i < len(mask) and mask[i]) else '#e74c3c'
              for i in range(len(laps))]
    ax.bar(laps, lap_times, color=colors, alpha=0.85, width=0.7)
    if any(t and t > 0 for t in lap_times):
        best = min(t for t in lap_times if t and t > 0)
        ax.axhline(best, color='#c85a17', lw=1.2, ls='--', label=f'Best {best:.3f}s')
    ax.tick_params(colors='#7a6b8a', labelsize=9)
    for sp in ax.spines.values(): sp.set_color('#2a1a38')
    ax.set_xlabel('Lap', color='#7a6b8a', fontsize=10)
    ax.set_ylabel('Lap time (s)', color='#7a6b8a', fontsize=10)
    ax.set_title('Lap Times', color='#f0e8ff', fontsize=12, pad=6)
    ax.legend(fontsize=9, facecolor='#1c1228', edgecolor='#2a1a38', labelcolor='#f0e8ff')
    fig.tight_layout(pad=0.8)
    return _fig_to_b64(fig)


def _chart_tire_temps(tire_summary) -> str:
    fig, ax = plt.subplots(figsize=(5, 3), facecolor='#0c0a12')
    ax.set_facecolor('#0c0a12')
    ax.set_xlim(0, 4); ax.set_ylim(0, 3); ax.axis('off')
    ax.set_title('Tire Temps (°C)', color='#f0e8ff', fontsize=12)
    cmap = plt.get_cmap('RdYlGn_r')
    pos = {'LF': (0.5, 2.2), 'RF': (2.5, 2.2), 'LR': (0.5, 0.2), 'RR': (2.5, 0.2)}
    for corner, (cx, cy) in pos.items():
        t = tire_summary.get(corner, {})
        if not t: continue
        for i, zone in enumerate(['inner', 'mid', 'outer']):
            tv = t.get(zone, 75)
            norm = np.clip((tv - 70) / 40, 0, 1)
            rect = mpatches.Rectangle((cx + i*0.28 - 0.42, cy), 0.28, 0.5,
                                       facecolor=cmap(norm), edgecolor='#2a1a38', lw=0.5)
            ax.add_patch(rect)
            ax.text(cx + i*0.28 - 0.28, cy + 0.25, f'{tv:.0f}',
                    ha='center', va='center', fontsize=8, color='white', fontweight='bold')
        ax.text(cx, cy + 0.72, corner, ha='center', fontsize=11,
                color='#f0e8ff', fontweight='bold')
    fig.tight_layout(pad=0.3)
    return _fig_to_b64(fig)


def _chart_sectors(sector_report) -> str:
    S = sector_report.sectors
    fig, ax = plt.subplots(figsize=(9, 3), facecolor='#0c0a12')
    ax.set_facecolor('#100c18')
    x = np.arange(len(S)); w = 0.35
    avgs  = [s.avg_time  for s in S]
    bests = [s.best_time for s in S]
    worst_idx = sector_report.worst_sector
    colors = ['#e74c3c' if i == worst_idx else '#9d4edd' for i in range(len(S))]
    ax.bar(x - w/2, avgs,  w, label='Avg',  color=colors, alpha=0.85)
    ax.bar(x + w/2, bests, w, label='Best', color='#2ecc71', alpha=0.85)
    xlabs = [f'S{i+1}' for i in range(len(S))]
    ax.set_xticks(x); ax.set_xticklabels(xlabs, color='#7a6b8a')
    ax.tick_params(colors='#7a6b8a', labelsize=9)
    for sp in ax.spines.values(): sp.set_color('#2a1a38')
    ax.set_ylabel('seconds', color='#7a6b8a', fontsize=10)
    ax.set_title('Sector Times — Avg vs Best', color='#f0e8ff', fontsize=12)
    ax.legend(fontsize=9, facecolor='#1c1228', edgecolor='#2a1a38', labelcolor='#f0e8ff')
    fig.tight_layout(pad=0.8)
    return _fig_to_b64(fig)


def _chart_driver_radar(driver_report) -> str:
    labels   = ['Braking', 'Throttle', 'Steering', 'Trail Brake', 'Stability', 'Overall']
    values   = [
        driver_report.brake_consistency,
        driver_report.throttle_smoothness,
        driver_report.steering_smoothness,
        driver_report.trail_braking_score,
        driver_report.oversteer_management,
        driver_report.overall_score,
    ]
    N = len(labels)
    angles = [n / N * 2 * np.pi for n in range(N)]
    angles += angles[:1]
    vals = [v / 100 for v in values]
    vals += vals[:1]

    fig, ax = plt.subplots(figsize=(4, 4), subplot_kw=dict(polar=True), facecolor='#0c0a12')
    ax.set_facecolor('#100c18')
    ax.plot(angles, vals, color='#c85a17', lw=2)
    ax.fill(angles, vals, color='#c85a17', alpha=0.25)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels, color='#f0e8ff', fontsize=9)
    ax.set_ylim(0, 1)
    ax.set_yticks([0.25, 0.5, 0.75, 1.0])
    ax.set_yticklabels(['25', '50', '75', '100'], color='#7a6b8a', fontsize=7)
    ax.grid(color='#2a1a38', alpha=0.5)
    ax.spines['polar'].set_color('#2a1a38')
    ax.set_title('Driver Scores', color='#f0e8ff', fontsize=12, pad=15)
    fig.tight_layout()
    return _fig_to_b64(fig)


def _fig_to_b64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=110, bbox_inches='tight',
                facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode('ascii')


# ── HTML template ─────────────────────────────────────────────────────────────

def _build_html(data, report, sector_report, driver_report, stint_report,
                fuel_report, session_note, app_version, charts) -> str:
    from core.analysis_engine import format_laptime

    si = data.session_info or {}
    car    = (data.car_name or 'Unknown Car').replace('_', ' ').title()
    track  = data.track_name or 'Unknown Track'
    driver = si.get('driver_name', '')
    sess_type = si.get('session_type', '')
    date_str  = datetime.now().strftime('%Y-%m-%d %H:%M')
    version   = app_version or 'Optimal Sector'

    best_lap  = format_laptime(report.best_lap) if report else '—'
    avg_lap   = format_laptime(report.avg_lap)  if report else '—'
    num_laps  = data.num_laps
    air_temp  = f"{si.get('air_temp_c', '?')}°C"
    track_temp = f"{si.get('track_temp_c', '?')}°C"

    def img(key):
        if key not in charts:
            return ''
        return f'<img src="data:image/png;base64,{charts[key]}" style="width:100%;border-radius:8px;margin:8px 0;">'

    issues_html = ''
    if report and report.issues:
        rows = ''
        sev_colors = {'critical': '#e74c3c', 'warning': '#f39c12', 'info': '#9d4edd'}
        for iss in report.issues[:10]:
            c = sev_colors.get(iss.severity.value, '#7a6b8a')
            rows += f'''<tr>
              <td style="color:{c};padding:6px 10px;font-weight:bold">{iss.severity.value.upper()}</td>
              <td style="padding:6px 10px;color:#f0e8ff">{iss.title}</td>
              <td style="padding:6px 10px;color:#7a6b8a;font-size:12px">{iss.description[:80]}</td>
            </tr>'''
        issues_html = f'''<h2 style="color:#b06fe0;margin-top:28px">Analysis Findings</h2>
        <table style="width:100%;border-collapse:collapse;background:#1e1530;border-radius:8px;overflow:hidden">
          <thead><tr style="background:#140e1e">
            <th style="padding:8px 10px;color:#7a6b8a;text-align:left">Severity</th>
            <th style="padding:8px 10px;color:#7a6b8a;text-align:left">Issue</th>
            <th style="padding:8px 10px;color:#7a6b8a;text-align:left">Detail</th>
          </tr></thead>
          <tbody>{rows}</tbody>
        </table>'''

    stint_html = ''
    if stint_report and hasattr(stint_report, 'deg_rate') and stint_report.deg_rate > 0:
        stint_html = f'''<div class="stat-card">
          <div class="stat-label">Tire Deg Rate</div>
          <div class="stat-value" style="color:#f39c12">{stint_report.deg_rate:.4f}s/lap</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Cliff Lap</div>
          <div class="stat-value" style="color:#e74c3c">{stint_report.cliff_lap}</div>
        </div>'''

    note_html = ''
    if session_note:
        note_html = f'''<h2 style="color:#b06fe0;margin-top:28px">Session Notes</h2>
        <div style="background:#1e1530;border-radius:8px;padding:16px;color:#f0e8ff;
                    white-space:pre-wrap;font-size:13px;line-height:1.6">{session_note}</div>'''

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{car} @ {track} — {version}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: #0c0a12; color: #f0e8ff; font-family: "Segoe UI", system-ui, sans-serif;
         font-size: 14px; line-height: 1.5; }}
  .container {{ max-width: 1100px; margin: 0 auto; padding: 24px 16px; }}
  .header {{ background: #140e1e; border-radius: 12px; padding: 24px; margin-bottom: 24px;
             border-left: 4px solid #c85a17; }}
  .header h1 {{ font-size: 22px; color: #f0e8ff; }}
  .header .sub {{ color: #7a6b8a; margin-top: 4px; }}
  .stats-row {{ display: flex; flex-wrap: wrap; gap: 12px; margin: 16px 0; }}
  .stat-card {{ background: #1e1530; border-radius: 8px; padding: 12px 18px; min-width: 120px; }}
  .stat-label {{ color: #7a6b8a; font-size: 11px; margin-bottom: 4px; }}
  .stat-value {{ font-size: 20px; font-weight: bold; color: #f0e8ff; }}
  h2 {{ color: #b06fe0; margin: 24px 0 12px; font-size: 16px; }}
  .chart-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin: 16px 0; }}
  .chart-box {{ background: #140e1e; border-radius: 8px; padding: 8px; }}
  .chart-full {{ background: #140e1e; border-radius: 8px; padding: 8px; margin: 8px 0; }}
  .footer {{ text-align: center; color: #7a6b8a; font-size: 11px; margin-top: 40px; padding-top: 16px;
             border-top: 1px solid #2a1a38; }}
  @media (max-width: 700px) {{ .chart-grid {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>
<div class="container">

  <div class="header">
    <h1>🏁 {car}</h1>
    <div class="sub">{track}  ·  {sess_type}  ·  {driver}  ·  {date_str}</div>
    <div class="sub" style="margin-top:6px">Air: {air_temp}  ·  Track: {track_temp}</div>
  </div>

  <h2>Session Overview</h2>
  <div class="stats-row">
    <div class="stat-card">
      <div class="stat-label">Best Lap</div>
      <div class="stat-value" style="color:#2ecc71">{best_lap}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Avg Lap</div>
      <div class="stat-value">{avg_lap}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Laps</div>
      <div class="stat-value">{num_laps}</div>
    </div>
    {stint_html}
  </div>

  <div class="chart-full">{img("lap_times")}</div>

  <div class="chart-grid">
    <div class="chart-box">{img("sectors")}</div>
    <div class="chart-box">{img("tire_temps")}</div>
  </div>

  <div class="chart-grid">
    <div class="chart-box">{img("driver")}</div>
    <div class="chart-box"></div>
  </div>

  {issues_html}
  {note_html}

  <div class="footer">
    Generated by {version}  ·  {date_str}
  </div>
</div>
</body>
</html>'''
