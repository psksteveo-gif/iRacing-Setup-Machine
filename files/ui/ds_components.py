# components.py — Optimal Sector Reusable Widget Library
# Usage: from components import Card, StatChip, SectionLabel, DataRow, ...

import customtkinter as ctk
from ui.ds_theme import COLORS, FONTS, RADIUS, SPACING


# ─────────────────────────────────────────────
# UTILITY
# ─────────────────────────────────────────────

def configure_ctk():
    """Call once at app startup before any window creation."""
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("dark-blue")


# ─────────────────────────────────────────────
# TITLEBAR
# ─────────────────────────────────────────────

class TitleBar(ctk.CTkFrame):
    """Top titlebar with brand, session info, and action buttons."""

    def __init__(self, parent, session_text="", on_load_ibt=None, **kwargs):
        super().__init__(parent, fg_color="#060608", height=36,
                         corner_radius=0, **kwargs)
        self.pack_propagate(False)

        # Brand
        brand_frame = ctk.CTkFrame(self, fg_color="transparent")
        brand_frame.pack(side="left", padx=(14, 10))

        hex_canvas = ctk.CTkCanvas(brand_frame, width=20, height=20,
                                    bg="#060608", highlightthickness=0)
        hex_canvas.pack(side="left", pady=8)
        pts = [10,0, 20,5, 20,15, 10,20, 0,15, 0,5]
        hex_canvas.create_polygon(pts, fill=COLORS["accent"], outline="")

        name_frame = ctk.CTkFrame(brand_frame, fg_color="transparent")
        name_frame.pack(side="left", padx=(7, 0))
        ctk.CTkLabel(name_frame, text="OPTIMAL SECTOR",
                     font=FONTS["display_bold_md"],
                     text_color=COLORS["text_primary"]).pack(anchor="w")
        ctk.CTkLabel(name_frame, text="Your AI Race Engineer",
                     font=FONTS["display_sm"],
                     text_color=COLORS["text_muted"]).pack(anchor="w")

        # Separator
        sep = ctk.CTkFrame(self, fg_color=COLORS["border_strong"],
                            width=1, height=18)
        sep.pack(side="left", padx=8)
        sep.pack_propagate(False)

        # Session
        if session_text:
            ctk.CTkLabel(self, text=session_text,
                         font=FONTS["display_sm"],
                         text_color=COLORS["text_secondary"]).pack(side="left")

        # Right actions
        right = ctk.CTkFrame(self, fg_color="transparent")
        right.pack(side="right", padx=14)

        if on_load_ibt:
            AccentButton(right, text="⬆  LOAD IBT",
                         command=on_load_ibt).pack(side="left", padx=(0, 5))

        for label in ["Load Demo", "Share", "● Live", "OBS HUD", "Watch", "Settings"]:
            GhostButton(right, text=label).pack(side="left", padx=2)


# ─────────────────────────────────────────────
# TAB BAR
# ─────────────────────────────────────────────

class PrimaryTabBar(ctk.CTkFrame):
    """Horizontal primary tab bar."""

    def __init__(self, parent, tabs: list, active: str = None,
                 on_change=None, **kwargs):
        super().__init__(parent, fg_color=COLORS["bg_surface"],
                         height=38, corner_radius=0, **kwargs)
        self.pack_propagate(False)
        self._on_change = on_change
        self._buttons = {}
        self._active = active or tabs[0]

        inner = ctk.CTkFrame(self, fg_color="transparent")
        inner.pack(side="left", padx=14, fill="y")

        for tab in tabs:
            btn = ctk.CTkButton(
                inner,
                text=tab.upper(),
                font=FONTS["display_bold_sm"],
                fg_color="transparent",
                hover_color=COLORS["bg_card"],
                text_color=COLORS["accent"] if tab == self._active
                           else COLORS["text_muted"],
                corner_radius=0,
                height=38,
                command=lambda t=tab: self._select(t)
            )
            btn.pack(side="left", padx=1)
            self._buttons[tab] = btn

    def _select(self, tab):
        for t, btn in self._buttons.items():
            btn.configure(
                text_color=COLORS["accent"] if t == tab
                           else COLORS["text_muted"]
            )
        self._active = tab
        if self._on_change:
            self._on_change(tab)

    def set_active(self, tab):
        self._select(tab)


class SubTabBar(ctk.CTkFrame):
    """Secondary sub-tab bar (AI panel uses this)."""

    def __init__(self, parent, tabs: list, active: str = None,
                 on_change=None, **kwargs):
        super().__init__(parent, fg_color="transparent",
                         corner_radius=0, **kwargs)
        self._on_change = on_change
        self._buttons = {}
        self._active = active or tabs[0]

        for tab in tabs:
            is_active = tab == self._active
            btn = ctk.CTkButton(
                self,
                text=tab.upper(),
                font=FONTS["display_bold_sm"],
                fg_color=COLORS["bg_card"] if is_active else "transparent",
                hover_color=COLORS["bg_card_hover"],
                text_color=COLORS["text_primary"] if is_active
                           else COLORS["text_muted"],
                border_color=COLORS["border_strong"] if is_active else "transparent",
                border_width=1,
                corner_radius=RADIUS["sm"],
                height=28,
                command=lambda t=tab: self._select(t)
            )
            btn.pack(side="left", padx=2)
            self._buttons[tab] = btn

    def _select(self, tab):
        for t, btn in self._buttons.items():
            is_active = t == tab
            btn.configure(
                fg_color=COLORS["bg_card"] if is_active else "transparent",
                text_color=COLORS["text_primary"] if is_active
                           else COLORS["text_muted"],
            )
        self._active = tab
        if self._on_change:
            self._on_change(tab)


# ─────────────────────────────────────────────
# BUTTONS
# ─────────────────────────────────────────────

class AccentButton(ctk.CTkButton):
    def __init__(self, parent, text="", command=None, **kwargs):
        super().__init__(
            parent,
            text=text,
            font=FONTS["display_bold_sm"],
            fg_color=COLORS["accent"],
            hover_color="#C8521A",
            text_color="#FFFFFF",
            corner_radius=RADIUS["sm"],
            height=28,
            command=command,
            **kwargs
        )


class GhostButton(ctk.CTkButton):
    def __init__(self, parent, text="", command=None, **kwargs):
        super().__init__(
            parent,
            text=text,
            font=FONTS["display_sm"],
            fg_color="transparent",
            hover_color=COLORS["bg_card"],
            text_color=COLORS["text_secondary"],
            border_color=COLORS["border_strong"],
            border_width=1,
            corner_radius=RADIUS["sm"],
            height=26,
            command=command,
            **kwargs
        )


class OutlineButton(ctk.CTkButton):
    def __init__(self, parent, text="", command=None, **kwargs):
        super().__init__(
            parent,
            text=text,
            font=FONTS["display_bold_sm"],
            fg_color="transparent",
            hover_color=COLORS["bg_card_hover"],
            text_color=COLORS["text_secondary"],
            border_color=COLORS["border_strong"],
            border_width=1,
            corner_radius=RADIUS["sm"],
            height=28,
            command=command,
            **kwargs
        )


# ─────────────────────────────────────────────
# LAYOUT PRIMITIVES
# ─────────────────────────────────────────────

class Card(ctk.CTkFrame):
    """Standard bordered card. Use as a container."""

    def __init__(self, parent, **kwargs):
        super().__init__(
            parent,
            fg_color=COLORS["bg_card"],
            border_color=COLORS["border"],
            border_width=1,
            corner_radius=RADIUS["md"],
            **kwargs
        )

    def add_header(self, title: str, subtitle: str = "", right_widget=None):
        """Add a standard card header. Returns header frame."""
        header = ctk.CTkFrame(self, fg_color="transparent", height=42)
        header.pack(fill="x", padx=14, pady=(10, 0))
        header.pack_propagate(False)

        SectionLabel(header, text=title).pack(side="left", anchor="center")

        if subtitle:
            ctk.CTkLabel(header, text=subtitle,
                         font=FONTS["body_sm"],
                         text_color=COLORS["text_muted"]).pack(
                side="left", padx=(8, 0), anchor="center")

        if right_widget:
            right_widget.pack(side="right", anchor="center")

        Divider(self).pack(fill="x", pady=(8, 0))
        return header


class ScrollableCard(ctk.CTkScrollableFrame):
    """Scrollable card container."""

    def __init__(self, parent, **kwargs):
        super().__init__(
            parent,
            fg_color=COLORS["bg_card"],
            scrollbar_button_color=COLORS["border_strong"],
            scrollbar_button_hover_color=COLORS["text_muted"],
            corner_radius=RADIUS["md"],
            **kwargs
        )


# ─────────────────────────────────────────────
# TYPOGRAPHY
# ─────────────────────────────────────────────

class SectionLabel(ctk.CTkLabel):
    """All-caps section heading used in card headers and group titles."""

    def __init__(self, parent, text: str, **kwargs):
        super().__init__(
            parent,
            text=text.upper(),
            font=FONTS["display_bold_md"],
            text_color=COLORS["text_primary"],
            **kwargs
        )


class MicroLabel(ctk.CTkLabel):
    """Tiny uppercase label for column headers, chip labels."""

    def __init__(self, parent, text: str, color=None, **kwargs):
        super().__init__(
            parent,
            text=text.upper(),
            font=FONTS["display_sm"],
            text_color=color or COLORS["text_muted"],
            **kwargs
        )


class MonoValue(ctk.CTkLabel):
    """Monospaced numeric/data value."""

    def __init__(self, parent, text: str, size="md",
                 color=None, **kwargs):
        font_key = f"mono_{size}"
        super().__init__(
            parent,
            text=text,
            font=FONTS.get(font_key, FONTS["mono_md"]),
            text_color=color or COLORS["text_primary"],
            **kwargs
        )


class Divider(ctk.CTkFrame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color=COLORS["border"],
                         height=1, corner_radius=0, **kwargs)


# ─────────────────────────────────────────────
# DATA DISPLAY COMPONENTS
# ─────────────────────────────────────────────

class StatChip(ctk.CTkFrame):
    """
    Summary stat card. Shows a label + large mono value + optional delta.
    color: 'normal' | 'good' | 'bad' | 'warn' | 'info'
    """

    COLOR_MAP = {
        "normal": COLORS["text_primary"],
        "good":   COLORS["green"],
        "bad":    COLORS["red"],
        "warn":   COLORS["amber"],
        "info":   COLORS["blue"],
        "accent": COLORS["accent"],
    }

    def __init__(self, parent, label: str, value: str,
                 delta: str = "", color: str = "normal", **kwargs):
        super().__init__(
            parent,
            fg_color=COLORS["bg_base"],
            border_color=COLORS["border"],
            border_width=1,
            corner_radius=RADIUS["md"],
            **kwargs
        )

        MicroLabel(self, text=label).pack(anchor="w", padx=12, pady=(10, 2))
        MonoValue(self, text=value, size="xl",
                  color=self.COLOR_MAP.get(color, COLORS["text_primary"])
                  ).pack(anchor="w", padx=12)

        if delta:
            ctk.CTkLabel(self, text=delta,
                         font=FONTS["body_sm"],
                         text_color=COLORS["text_muted"]).pack(
                anchor="w", padx=12, pady=(2, 10))
        else:
            ctk.CTkLabel(self, text="").pack(pady=4)

    def update_value(self, value: str, color: str = "normal"):
        """Dynamically update the displayed value."""
        # Traverse children to find MonoValue and update
        for child in self.winfo_children():
            if isinstance(child, MonoValue):
                child.configure(
                    text=value,
                    text_color=self.COLOR_MAP.get(color, COLORS["text_primary"])
                )
                break


class DataRow(ctk.CTkFrame):
    """
    Horizontal key-value row. Used in setup tables, telemetry lists.
    """

    def __init__(self, parent, label: str, value: str,
                 value_color=None, badge: str = "",
                 badge_color=None, **kwargs):
        super().__init__(parent, fg_color="transparent",
                         height=30, **kwargs)
        self.pack_propagate(False)

        ctk.CTkLabel(self, text=label,
                     font=FONTS["body_sm"],
                     text_color=COLORS["text_secondary"],
                     anchor="w").pack(side="left", fill="x", expand=True)

        if badge:
            Badge(self, text=badge,
                  color=badge_color or "info").pack(side="right", padx=(4, 0))

        ctk.CTkLabel(self, text=value,
                     font=FONTS["mono_sm"],
                     text_color=value_color or COLORS["text_primary"],
                     anchor="e").pack(side="right")


class ChangeBlock(ctk.CTkFrame):
    """
    Shows a parameter change: PARAM  [old] → [new]
    Used in AI recommendation cards.
    """

    def __init__(self, parent, parameter: str,
                 from_val: str, to_val: str, **kwargs):
        super().__init__(
            parent,
            fg_color=COLORS["bg_surface"],
            border_color=COLORS["border"],
            border_width=1,
            corner_radius=RADIUS["sm"],
            **kwargs
        )

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(padx=14, pady=10)

        MicroLabel(row, text="Parameter").pack(side="left", padx=(0, 10))

        ctk.CTkLabel(row, text=parameter,
                     font=FONTS["display_md"],
                     text_color=COLORS["text_primary"]).pack(
            side="left", padx=(0, 16))

        ctk.CTkLabel(row, text=from_val,
                     font=FONTS["mono_lg"],
                     text_color=COLORS["red"]).pack(side="left")

        ctk.CTkLabel(row, text="  →  ",
                     font=FONTS["mono_md"],
                     text_color=COLORS["text_muted"]).pack(side="left")

        ctk.CTkLabel(row, text=to_val,
                     font=FONTS["mono_lg"],
                     text_color=COLORS["green"]).pack(side="left")


class IssueRow(ctk.CTkFrame):
    """
    Single row in the Issues / Top Issues list.
    severity: 'critical' | 'medium' | 'advisory' | 'good'
    """

    SEVERITY_COLORS = {
        "critical": COLORS["red"],
        "medium":   COLORS["amber"],
        "advisory": COLORS["blue"],
        "good":     COLORS["green"],
    }

    def __init__(self, parent, title: str, severity: str = "medium",
                 tag: str = "", on_click=None, **kwargs):
        color = self.SEVERITY_COLORS.get(severity, COLORS["text_secondary"])

        super().__init__(
            parent,
            fg_color=COLORS["bg_base"],
            border_color=COLORS["border"],
            border_width=1,
            corner_radius=RADIUS["sm"],
            height=40,
            **kwargs
        )
        self.pack_propagate(False)

        # Severity dot
        dot = ctk.CTkFrame(self, fg_color=color, width=6,
                            height=6, corner_radius=3)
        dot.pack(side="left", padx=(14, 10))
        dot.pack_propagate(False)

        ctk.CTkLabel(self, text=title,
                     font=FONTS["body_md"],
                     text_color=COLORS["text_primary"],
                     anchor="w").pack(side="left", fill="x", expand=True)

        if tag:
            Badge(self, text=tag,
                  color=severity).pack(side="right", padx=(0, 14))

        if on_click:
            self.bind("<Button-1>", lambda e: on_click())


class TireGrid(ctk.CTkFrame):
    """
    4-corner tire temperature or pressure display.
    values: dict with keys LF, RF, LR, RR each containing list of 3 zone values
    """

    def __init__(self, parent, values: dict, unit: str = "°F", **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)

        positions = [
            ("LF", 0, 0), ("RF", 0, 1),
            ("LR", 1, 0), ("RR", 1, 1),
        ]

        for corner, row, col in positions:
            corner_data = values.get(corner, [0, 0, 0])
            avg = sum(corner_data) / len(corner_data)
            color = self._temp_color(avg)

            frame = ctk.CTkFrame(self, fg_color="transparent")
            frame.grid(row=row, column=col, padx=8, pady=8)

            MicroLabel(frame, text=corner).pack(anchor="w", pady=(0, 4))

            zones = ctk.CTkFrame(frame, fg_color="transparent")
            zones.pack()

            for i, val in enumerate(corner_data):
                z = ctk.CTkFrame(zones, fg_color=color,
                                  corner_radius=RADIUS["sm"],
                                  width=52, height=44)
                z.grid(row=0, column=i, padx=2)
                z.pack_propagate(False)
                MonoValue(z, text=str(val), size="md",
                          color="#FFFFFF").pack(expand=True)

            avg_str = f"avg {avg:.1f}{unit}"
            ctk.CTkLabel(frame, text=avg_str,
                         font=FONTS["body_sm"],
                         text_color=COLORS["text_muted"]).pack(pady=(4, 0))

    @staticmethod
    def _temp_color(temp_f: float) -> str:
        """Returns a color based on temperature — green (cold) → amber → red (hot)."""
        if temp_f < 100:
            return "#0F3020"
        elif temp_f < 140:
            return "#1D9E52"
        elif temp_f < 170:
            return "#8A6010"
        else:
            return "#8A2020"


class ProgressBar(ctk.CTkFrame):
    """Labeled progress bar for consistency scores etc."""

    def __init__(self, parent, label: str, value: float,
                 max_val: float = 100, color=None, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x")

        ctk.CTkLabel(row, text=label,
                     font=FONTS["body_sm"],
                     text_color=COLORS["text_secondary"],
                     anchor="w").pack(side="left", fill="x", expand=True)

        pct = value / max_val if max_val > 0 else 0
        val_color = COLORS["green"] if pct > 0.7 else (
            COLORS["amber"] if pct > 0.4 else COLORS["red"])

        ctk.CTkLabel(row, text=f"{value:.0f}",
                     font=FONTS["mono_sm"],
                     text_color=color or val_color).pack(side="right")

        bar = ctk.CTkProgressBar(
            self,
            progress_color=color or val_color,
            fg_color=COLORS["border"],
            height=4,
            corner_radius=2
        )
        bar.pack(fill="x", pady=(3, 0))
        bar.set(max(0, min(1, pct)))


# ─────────────────────────────────────────────
# BADGES & TAGS
# ─────────────────────────────────────────────

class Badge(ctk.CTkLabel):
    """
    Small colored label badge.
    color: 'critical'|'medium'|'advisory'|'good'|'accent'|'info'|hex string
    """

    COLOR_MAP = {
        "critical": (COLORS["red_dim"],    COLORS["red"]),
        "medium":   (COLORS["amber_dim"],  COLORS["amber"]),
        "advisory": (COLORS["blue_dim"],   COLORS["blue"]),
        "good":     (COLORS["green_dim"],  COLORS["green"]),
        "accent":   (COLORS["accent_dim"], COLORS["accent"]),
        "info":     (COLORS["bg_surface"], COLORS["text_secondary"]),
        "purple":   (COLORS["purple_dim"], COLORS["purple"]),
    }

    def __init__(self, parent, text: str, color: str = "info", **kwargs):
        bg, fg = self.COLOR_MAP.get(color, (COLORS["bg_surface"],
                                            COLORS["text_secondary"]))
        super().__init__(
            parent,
            text=text.upper(),
            font=FONTS["display_bold_sm"],
            text_color=fg,
            fg_color=bg,
            corner_radius=RADIUS["sm"],
            padx=8,
            pady=3,
            **kwargs
        )


class LiveBadge(ctk.CTkLabel):
    """Animated-feeling 'live' indicator."""

    def __init__(self, parent, text="● ANALYSIS COMPLETE",
                 color=None, **kwargs):
        super().__init__(
            parent,
            text=text,
            font=FONTS["display_bold_sm"],
            text_color=color or COLORS["green"],
            fg_color=COLORS["green_dim"],
            corner_radius=RADIUS["sm"],
            padx=10,
            pady=4,
            **kwargs
        )


# ─────────────────────────────────────────────
# INPUT COMPONENTS
# ─────────────────────────────────────────────

class AskBar(ctk.CTkFrame):
    """
    The AI ask input bar at the bottom of the AI panel.
    on_submit: callable receiving the text string
    """

    def __init__(self, parent, on_submit=None, **kwargs):
        super().__init__(
            parent,
            fg_color=COLORS["bg_card"],
            border_color=COLORS["border"],
            border_width=1,
            corner_radius=0,
            height=58,
            **kwargs
        )
        self.pack_propagate(False)
        self._on_submit = on_submit

        inner = ctk.CTkFrame(self, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=14, pady=9)

        # Input wrapper
        input_wrap = ctk.CTkFrame(
            inner,
            fg_color=COLORS["bg_input"],
            border_color=COLORS["border_strong"],
            border_width=1,
            corner_radius=RADIUS["sm"]
        )
        input_wrap.pack(side="left", fill="both", expand=True, padx=(0, 8))

        MicroLabel(input_wrap, text="Ask",
                   color=COLORS["accent"]).pack(side="left", padx=(12, 8))

        self._entry = ctk.CTkEntry(
            input_wrap,
            placeholder_text="e.g. What if I soften the front ARB 2 clicks?",
            font=FONTS["body_md"],
            fg_color="transparent",
            border_width=0,
            text_color=COLORS["text_primary"],
            placeholder_text_color=COLORS["text_muted"]
        )
        self._entry.pack(side="left", fill="both", expand=True, pady=2)
        self._entry.bind("<Return>", self._submit)

        AccentButton(inner, text="SEND  ↗",
                     command=self._submit, width=90).pack(side="right")

    def _submit(self, event=None):
        text = self._entry.get().strip()
        if text and self._on_submit:
            self._on_submit(text)
            self._entry.delete(0, "end")

    def get(self):
        return self._entry.get()

    def clear(self):
        self._entry.delete(0, "end")


# ─────────────────────────────────────────────
# LAP TIME LIST
# ─────────────────────────────────────────────

class LapTimeRow(ctk.CTkFrame):
    """Single row in a lap time list."""

    def __init__(self, parent, lap_num: int, lap_time: str,
                 delta: str = "", fuel: str = "",
                 is_best: bool = False, is_outlier: bool = False,
                 **kwargs):
        bg = COLORS["bg_base"]
        super().__init__(parent, fg_color=bg,
                         corner_radius=0, height=26, **kwargs)
        self.pack_propagate(False)

        # Lap number
        num_color = COLORS["purple"] if is_best else COLORS["text_muted"]
        ctk.CTkLabel(self, text=f"Lap {lap_num}",
                     font=FONTS["mono_sm"],
                     text_color=num_color,
                     width=52,
                     anchor="w").pack(side="left", padx=(10, 0))

        # Lap time
        time_color = COLORS["purple"] if is_best else (
            COLORS["text_muted"] if is_outlier else COLORS["text_primary"])
        ctk.CTkLabel(self, text=lap_time,
                     font=FONTS["mono_sm"],
                     text_color=time_color).pack(side="left", padx=(4, 0))

        # Delta
        if delta:
            d_color = COLORS["green"] if delta.startswith("-") else COLORS["red"]
            if delta.startswith("+"):
                d_color = COLORS["amber"]
            ctk.CTkLabel(self, text=delta,
                         font=FONTS["mono_sm"],
                         text_color=d_color).pack(side="left", padx=(6, 0))

        # Fuel
        if fuel:
            ctk.CTkLabel(self, text=fuel,
                         font=FONTS["body_sm"],
                         text_color=COLORS["text_muted"]).pack(
                side="right", padx=(0, 10))

        if is_outlier:
            Badge(self, text="OL", color="medium").pack(
                side="right", padx=(0, 6))


# ─────────────────────────────────────────────
# SIDEBAR COMPONENTS
# ─────────────────────────────────────────────

class Sidebar(ctk.CTkFrame):
    """Left session sidebar."""

    def __init__(self, parent, **kwargs):
        super().__init__(
            parent,
            fg_color=COLORS["bg_surface"],
            corner_radius=0,
            width=148,
            border_color=COLORS["border"],
            border_width=0,
            **kwargs
        )
        self.pack_propagate(False)
        MicroLabel(self, text="Sessions").pack(
            anchor="w", padx=12, pady=(12, 6))

    def add_session(self, car: str, track: str, best_time: str,
                    progress: float = 0.5, active: bool = True):
        item = ctk.CTkFrame(
            self,
            fg_color=COLORS["bg_card"] if active else "transparent",
            corner_radius=0
        )
        item.pack(fill="x")

        # Accent bar on left
        accent_strip = ctk.CTkFrame(item, fg_color=COLORS["accent"],
                                     width=2, corner_radius=0)
        accent_strip.pack(side="left", fill="y")
        accent_strip.pack_propagate(False)

        content = ctk.CTkFrame(item, fg_color="transparent")
        content.pack(side="left", fill="x", expand=True,
                     padx=10, pady=8)

        ctk.CTkLabel(content, text=car,
                     font=FONTS["display_bold_sm"],
                     text_color=COLORS["text_primary"],
                     anchor="w",
                     wraplength=118).pack(anchor="w")

        ctk.CTkLabel(content, text=track,
                     font=FONTS["body_sm"],
                     text_color=COLORS["text_secondary"],
                     anchor="w").pack(anchor="w")

        MonoValue(content, text=best_time, size="sm",
                  color=COLORS["accent"]).pack(anchor="w", pady=(4, 0))

        bar_bg = ctk.CTkFrame(content, fg_color=COLORS["border"],
                               height=2, corner_radius=1)
        bar_bg.pack(fill="x", pady=(6, 0))
        fill_w = max(0, min(1, progress))
        bar_fill = ctk.CTkFrame(bar_bg, fg_color=COLORS["accent"],
                                 height=2, corner_radius=1)
        bar_fill.place(relwidth=fill_w, relheight=1)
