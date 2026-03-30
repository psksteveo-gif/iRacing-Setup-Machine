# ai_renderer.py — Renders structured AI JSON responses as CTk widgets
# Replaces all raw text/markdown output in the AI tab

import json
import customtkinter as ctk
from ui.ds_theme import COLORS, FONTS, RADIUS
from ui.ds_components import (Card, SectionLabel, MicroLabel, MonoValue,
                        Badge, Divider, ChangeBlock, ProgressBar,
                        AccentButton, StatChip)


# ─────────────────────────────────────────────
# SYSTEM PROMPT — paste into your AI API call
# ─────────────────────────────────────────────

AI_SYSTEM_PROMPT = """
You are Claude, an expert motorsport data engineer and race engineer AI embedded in Optimal Sector, a professional iRacing telemetry application.

CRITICAL: You must ALWAYS respond with valid JSON only.
Never use markdown. Never use ** or ## or --- or | table syntax.
Never add any text outside the JSON structure.

Return this exact JSON structure:

{
  "summary": {
    "entry_oversteer": "+0.00",
    "mid_corner_oversteer": "+0.00",
    "braking_score": "00/100",
    "biggest_opportunity": "Corner name or description"
  },
  "data_warnings": [
    "Warning text if data quality issues exist"
  ],
  "reliable_signals": [
    {
      "signal": "Signal name",
      "value": "Value string",
      "reliability": "high"
    }
  ],
  "recommendations": [
    {
      "priority": 1,
      "title": "Short title e.g. Front Brake Bias",
      "subtitle": "Category e.g. Brake system · Entry stability",
      "severity": "critical",
      "parameter": "Parameter name",
      "from_value": "Current value",
      "to_value": "Recommended value",
      "reasons": [
        "Specific data-backed reason 1",
        "Specific data-backed reason 2"
      ],
      "impact_metric": "What improves e.g. Entry oversteer score",
      "impact_value": "Expected change e.g. +1.00 → +0.40–0.50",
      "driver_note": "Specific note to the driver about feel or technique"
    }
  ],
  "focus_areas": [
    {
      "area": "Corner or area name",
      "time_loss": "-0.000s",
      "description": "One sentence description"
    }
  ]
}

Severity must be one of: critical, medium, advisory
Priority must be integers starting at 1
All values must be strings
If data is unavailable for a field use null
"""


# ─────────────────────────────────────────────
# MAIN RENDERER
# ─────────────────────────────────────────────

def render_ai_response(parent_frame: ctk.CTkFrame, response_str: str):
    """
    Clear parent_frame and render a structured AI response.
    Call this whenever a new AI response arrives.

    Args:
        parent_frame: The scrollable frame to render into
        response_str: Raw string from Claude API (should be JSON)
    """
    # Clear existing content
    for widget in parent_frame.winfo_children():
        widget.destroy()

    # Parse JSON
    try:
        # Strip any accidental markdown code fences
        clean = response_str.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[1]
            clean = clean.rsplit("```", 1)[0]
        data = json.loads(clean)
    except (json.JSONDecodeError, ValueError):
        _render_parse_error(parent_frame, response_str)
        return

    # Render sections
    if data.get("data_warnings"):
        _render_warnings(parent_frame, data["data_warnings"])

    if data.get("summary"):
        _render_summary_chips(parent_frame, data["summary"])

    if data.get("recommendations"):
        _render_section_header(parent_frame, "Setup Recommendations",
                               f"{len(data['recommendations'])} items")
        for rec in data["recommendations"]:
            _render_rec_card(parent_frame, rec)

    if data.get("focus_areas"):
        _render_section_header(parent_frame, "Focus Areas", "by time loss")
        _render_focus_areas(parent_frame, data["focus_areas"])

    if data.get("reliable_signals"):
        _render_section_header(parent_frame, "Data Signals", "reliability")
        _render_signals(parent_frame, data["reliable_signals"])


# ─────────────────────────────────────────────
# SECTION RENDERERS
# ─────────────────────────────────────────────

def _render_warnings(parent, warnings: list):
    frame = ctk.CTkFrame(
        parent,
        fg_color=COLORS["bg_warning"],
        border_color=COLORS["amber"],
        border_width=1,
        corner_radius=RADIUS["md"]
    )
    frame.pack(fill="x", padx=0, pady=(0, 10))

    header = ctk.CTkFrame(frame, fg_color="transparent")
    header.pack(fill="x", padx=14, pady=(10, 6))
    ctk.CTkLabel(header, text="⚠",
                 font=("Barlow Condensed", 14),
                 text_color=COLORS["amber"]).pack(side="left", padx=(0, 6))
    ctk.CTkLabel(header, text="DATA QUALITY WARNINGS",
                 font=FONTS["display_bold_sm"],
                 text_color=COLORS["amber"]).pack(side="left")

    for w in warnings:
        row = ctk.CTkFrame(frame, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=2)
        ctk.CTkLabel(row, text="—",
                     font=FONTS["display_sm"],
                     text_color=COLORS["amber"],
                     width=14).pack(side="left", anchor="n", pady=2)
        ctk.CTkLabel(row, text=w,
                     font=FONTS["body_sm"],
                     text_color=COLORS["text_secondary"],
                     wraplength=860,
                     justify="left",
                     anchor="w").pack(side="left", padx=(6, 0), fill="x")

    ctk.CTkLabel(frame, text="").pack(pady=4)


def _render_summary_chips(parent, summary: dict):
    frame = ctk.CTkFrame(parent, fg_color="transparent")
    frame.pack(fill="x", pady=(0, 10))

    label_map = {
        "entry_oversteer":     ("Entry Oversteer",    "bad"),
        "mid_corner_oversteer":("Mid-Corner OS",      "warn"),
        "braking_score":       ("Braking Score",      "good"),
        "biggest_opportunity": ("Biggest Opportunity","info"),
    }

    for i, (key, (label, color)) in enumerate(label_map.items()):
        val = summary.get(key, "—")
        if val is None:
            val = "—"
        chip = StatChip(frame, label=label, value=str(val), color=color)
        chip.grid(row=0, column=i, padx=(0, 8) if i < 3 else 0,
                  sticky="nsew")
        frame.columnconfigure(i, weight=1)


def _render_section_header(parent, title: str, subtitle: str = ""):
    row = ctk.CTkFrame(parent, fg_color="transparent", height=30)
    row.pack(fill="x", pady=(8, 4))
    row.pack_propagate(False)

    ctk.CTkLabel(row, text=title.upper(),
                 font=FONTS["display_bold_md"],
                 text_color=COLORS["text_primary"]).pack(side="left",
                                                          anchor="center")
    if subtitle:
        ctk.CTkLabel(row, text=subtitle,
                     font=FONTS["body_sm"],
                     text_color=COLORS["text_muted"]).pack(
            side="left", padx=(8, 0), anchor="center")


def _render_rec_card(parent, rec: dict):
    severity = rec.get("severity", "advisory")
    colors_map = {
        "critical": COLORS["red"],
        "medium":   COLORS["amber"],
        "advisory": COLORS["blue"],
    }
    color = colors_map.get(severity, COLORS["blue"])

    # Card frame
    card = ctk.CTkFrame(parent,
                         fg_color=COLORS["bg_base"],
                         border_color=COLORS["border"],
                         border_width=1,
                         corner_radius=RADIUS["md"])
    card.pack(fill="x", pady=(0, 8))

    # ── HEADER ──
    header = ctk.CTkFrame(card, fg_color="transparent")
    header.pack(fill="x", padx=14, pady=(12, 10))

    # Priority circle
    pframe = ctk.CTkFrame(header, fg_color=COLORS["bg_card"],
                           width=30, height=30, corner_radius=15)
    pframe.pack(side="left", padx=(0, 10))
    pframe.pack_propagate(False)
    ctk.CTkLabel(pframe, text=str(rec.get("priority", "?")),
                 font=FONTS["display_bold_md"],
                 text_color=color).pack(expand=True)

    # Title group
    tg = ctk.CTkFrame(header, fg_color="transparent")
    tg.pack(side="left", fill="x", expand=True)
    ctk.CTkLabel(tg, text=rec.get("title", ""),
                 font=FONTS["display_bold_lg"],
                 text_color=COLORS["text_primary"],
                 anchor="w").pack(anchor="w")
    ctk.CTkLabel(tg, text=rec.get("subtitle", ""),
                 font=FONTS["mono_sm"],
                 text_color=COLORS["text_secondary"],
                 anchor="w").pack(anchor="w")

    # Badges
    badges = ctk.CTkFrame(header, fg_color="transparent")
    badges.pack(side="right")
    Badge(badges, text=severity, color=severity).pack(side="left", padx=(0, 4))
    if rec.get("impact_value"):
        Badge(badges, text=rec["impact_value"], color="good").pack(side="left")

    # Divider
    Divider(card).pack(fill="x")

    # ── CHANGE BLOCK ──
    if rec.get("parameter") and rec.get("from_value") and rec.get("to_value"):
        ChangeBlock(card,
                    parameter=rec["parameter"],
                    from_val=rec["from_value"],
                    to_val=rec["to_value"]).pack(fill="x", padx=14, pady=10)

    # ── REASONS ──
    if rec.get("reasons"):
        MicroLabel(card, text="Analysis").pack(
            anchor="w", padx=14, pady=(0, 6))
        for reason in rec["reasons"]:
            row = ctk.CTkFrame(card, fg_color="transparent")
            row.pack(fill="x", padx=14, pady=2)
            ctk.CTkLabel(row, text="—",
                         font=FONTS["display_md"],
                         text_color=COLORS["accent"],
                         width=14).pack(side="left", anchor="n", pady=1)
            ctk.CTkLabel(row, text=reason,
                         font=FONTS["body_md"],
                         text_color=COLORS["text_secondary"],
                         wraplength=860,
                         justify="left",
                         anchor="w").pack(side="left", padx=(8, 0), fill="x")

    # ── DRIVER NOTE ──
    if rec.get("driver_note"):
        note_frame = ctk.CTkFrame(card,
                                   fg_color="#100D0A",
                                   corner_radius=0)
        note_frame.pack(fill="x", pady=(10, 0))

        inner = ctk.CTkFrame(note_frame, fg_color="transparent")
        inner.pack(fill="x", padx=14, pady=(10, 10))

        # Left accent bar
        accent_line = ctk.CTkFrame(inner, fg_color=COLORS["accent"],
                                    width=2, corner_radius=1)
        accent_line.pack(side="left", fill="y", padx=(0, 10))
        accent_line.pack_propagate(False)

        note_content = ctk.CTkFrame(inner, fg_color="transparent")
        note_content.pack(side="left", fill="x", expand=True)

        MicroLabel(note_content, text="Driver Note",
                   color=COLORS["accent"]).pack(anchor="w", pady=(0, 3))
        ctk.CTkLabel(note_content, text=rec["driver_note"],
                     font=FONTS["body_md"],
                     text_color=COLORS["text_secondary"],
                     wraplength=860,
                     justify="left",
                     anchor="w").pack(anchor="w")


def _render_focus_areas(parent, areas: list):
    for area in areas:
        row = ctk.CTkFrame(parent,
                            fg_color=COLORS["bg_base"],
                            border_color=COLORS["border"],
                            border_width=1,
                            corner_radius=RADIUS["sm"],
                            height=44)
        row.pack(fill="x", pady=(0, 4))
        row.pack_propagate(False)

        ctk.CTkLabel(row, text=area.get("area", ""),
                     font=FONTS["display_bold_md"],
                     text_color=COLORS["text_primary"],
                     anchor="w").pack(side="left", padx=14, anchor="center")

        ctk.CTkLabel(row, text=area.get("description", ""),
                     font=FONTS["body_sm"],
                     text_color=COLORS["text_secondary"],
                     anchor="w").pack(side="left", padx=(4, 0), anchor="center")

        loss = area.get("time_loss", "")
        if loss:
            ctk.CTkLabel(row, text=loss,
                         font=FONTS["mono_md"],
                         text_color=COLORS["red"]).pack(
                side="right", padx=14, anchor="center")


def _render_signals(parent, signals: list):
    frame = ctk.CTkFrame(parent,
                          fg_color=COLORS["bg_base"],
                          border_color=COLORS["border"],
                          border_width=1,
                          corner_radius=RADIUS["md"])
    frame.pack(fill="x", pady=(0, 8))

    rel_colors = {"high": COLORS["green"],
                  "medium": COLORS["amber"],
                  "low": COLORS["red"]}

    for i, sig in enumerate(signals):
        row = ctk.CTkFrame(frame, fg_color="transparent", height=30)
        row.pack(fill="x", padx=14, pady=2)
        row.pack_propagate(False)

        ctk.CTkLabel(row, text=sig.get("signal", ""),
                     font=FONTS["body_sm"],
                     text_color=COLORS["text_secondary"],
                     anchor="w").pack(side="left", fill="x", expand=True,
                                      anchor="center")

        ctk.CTkLabel(row, text=str(sig.get("value", "")),
                     font=FONTS["mono_sm"],
                     text_color=COLORS["text_primary"]).pack(
            side="left", padx=(0, 12), anchor="center")

        rel = sig.get("reliability", "medium")
        ctk.CTkLabel(row, text=rel.upper(),
                     font=FONTS["display_bold_sm"],
                     text_color=rel_colors.get(rel, COLORS["text_muted"])
                     ).pack(side="right", anchor="center")

        if i < len(signals) - 1:
            Divider(frame).pack(fill="x", padx=14)


def _render_parse_error(parent, raw_str: str):
    """Fallback: shows a clean error state instead of dumping raw text."""
    frame = ctk.CTkFrame(parent,
                          fg_color=COLORS["bg_danger"],
                          border_color=COLORS["red"],
                          border_width=1,
                          corner_radius=RADIUS["md"])
    frame.pack(fill="x", padx=0, pady=10)

    ctk.CTkLabel(frame, text="Response format error",
                 font=FONTS["display_bold_md"],
                 text_color=COLORS["red"]).pack(anchor="w", padx=14, pady=(12, 4))

    ctk.CTkLabel(frame,
                 text="The AI returned an unstructured response. "
                      "Check your system prompt includes the JSON format instruction.",
                 font=FONTS["body_sm"],
                 text_color=COLORS["text_secondary"],
                 wraplength=860,
                 justify="left").pack(anchor="w", padx=14, pady=(0, 4))

    # Show first 200 chars of raw for debugging
    preview = raw_str[:200] + "..." if len(raw_str) > 200 else raw_str
    ctk.CTkLabel(frame, text=preview,
                 font=FONTS["mono_sm"],
                 text_color=COLORS["text_muted"],
                 wraplength=860,
                 justify="left").pack(anchor="w", padx=14, pady=(0, 12))
