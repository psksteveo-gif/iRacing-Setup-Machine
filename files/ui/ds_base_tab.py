# base_tab.py — Base class every tab inherits from
# Ensures consistent layout, padding, colors, and scrolling across all tabs

import customtkinter as ctk
from ui.ds_theme import COLORS, FONTS, RADIUS, SPACING


class BaseTab(ctk.CTkFrame):
    """
    Base class for all Optimal Sector tabs.

    Provides:
    - Consistent background color
    - Optional scrollable content area
    - Standard section/card factory methods
    - Uniform padding

    Usage:
        class DashboardTab(BaseTab):
            def __init__(self, parent):
                super().__init__(parent)
                self.build()

            def build(self):
                row = self.add_stat_row()
                StatChip(row, label="Best Lap", value="1:24.683").pack(side="left")
    """

    def __init__(self, parent, scrollable: bool = False, **kwargs):
        super().__init__(
            parent,
            fg_color=COLORS["bg_base"],
            corner_radius=0,
            **kwargs
        )

        if scrollable:
            self._scroll = ctk.CTkScrollableFrame(
                self,
                fg_color=COLORS["bg_base"],
                scrollbar_button_color=COLORS["border_strong"],
                scrollbar_button_hover_color=COLORS["text_muted"],
                corner_radius=0
            )
            self._scroll.pack(fill="both", expand=True)
            self.content = self._scroll
        else:
            self.content = self

    # ── FACTORY METHODS ──

    def add_padding(self, h=SPACING["md"]):
        ctk.CTkFrame(self.content, fg_color="transparent",
                      height=h).pack(fill="x")

    def add_divider(self):
        ctk.CTkFrame(self.content, fg_color=COLORS["border"],
                      height=1, corner_radius=0).pack(fill="x")

    def add_section_header(self, title: str, subtitle: str = "",
                            right_widget=None) -> ctk.CTkFrame:
        """Returns a section header row frame."""
        row = ctk.CTkFrame(self.content, fg_color="transparent", height=36)
        row.pack(fill="x", padx=SPACING["lg"], pady=(SPACING["md"], 4))
        row.pack_propagate(False)

        ctk.CTkLabel(row, text=title.upper(),
                     font=FONTS["display_bold_md"],
                     text_color=COLORS["text_primary"]).pack(
            side="left", anchor="center")

        if subtitle:
            ctk.CTkLabel(row, text=subtitle,
                         font=FONTS["body_sm"],
                         text_color=COLORS["text_muted"]).pack(
                side="left", padx=(8, 0), anchor="center")

        if right_widget:
            right_widget.pack(side="right", anchor="center")

        return row

    def add_card(self, title: str = "", subtitle: str = "") -> ctk.CTkFrame:
        """Creates and returns a card frame, optionally with a header."""
        from ui.ds_components import Card
        card = Card(self.content)
        card.pack(fill="x", padx=SPACING["sm"], pady=(0, SPACING["sm"]))

        if title:
            card.add_header(title, subtitle)

        return card

    def add_grid_row(self, columns: int = 4,
                     padx=SPACING["sm"]) -> ctk.CTkFrame:
        """Creates a horizontal grid row, returns it for packing children."""
        row = ctk.CTkFrame(self.content, fg_color="transparent")
        row.pack(fill="x", padx=padx, pady=(0, SPACING["sm"]))
        for i in range(columns):
            row.columnconfigure(i, weight=1)
        return row

    def add_two_col_layout(self) -> tuple:
        """Creates a two-column layout, returns (left_frame, right_frame)."""
        container = ctk.CTkFrame(self.content, fg_color="transparent")
        container.pack(fill="both", expand=True,
                       padx=SPACING["sm"], pady=(0, SPACING["sm"]))

        left = ctk.CTkFrame(container, fg_color="transparent")
        left.pack(side="left", fill="both", expand=True, padx=(0, 4))

        right = ctk.CTkFrame(container, fg_color="transparent")
        right.pack(side="left", fill="both", expand=True, padx=(4, 0))

        return left, right

    def clear(self):
        """Remove all children from content area (for refresh)."""
        for w in self.content.winfo_children():
            w.destroy()
