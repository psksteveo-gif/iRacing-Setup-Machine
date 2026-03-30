# theme.py — Optimal Sector Design System
# Import this everywhere: from theme import COLORS, FONTS, RADIUS

COLORS = {
    # Backgrounds
    "bg_base":        "#08080A",
    "bg_surface":     "#0F0F13",
    "bg_card":        "#14141A",
    "bg_card_hover":  "#1A1A22",
    "bg_input":       "#0C0C10",
    "bg_warning":     "#100E08",
    "bg_danger":      "#100808",
    "bg_success":     "#08100D",

    # Accent / brand
    "accent":         "#E8611A",
    "accent_dim":     "#1A120A",
    "accent_border":  "#3D2010",

    # Semantic
    "green":          "#2ECC8E",
    "green_dim":      "#0A1410",
    "red":            "#E84040",
    "red_dim":        "#140808",
    "amber":          "#F0A830",
    "amber_dim":      "#14100A",
    "blue":           "#4A9EE8",
    "blue_dim":       "#080E14",
    "purple":         "#9B6EE8",
    "purple_dim":     "#0E0A14",

    # Text
    "text_primary":   "#F0EEE8",
    "text_secondary": "#8A8890",
    "text_muted":     "#4A4858",
    "text_accent":    "#E8611A",

    # Borders
    "border":         "#1C1C24",
    "border_strong":  "#252530",
}

FONTS = {
    # Load these TTFs via ctk.FontManager.load_font() before window creation
    # Download: Barlow Condensed (Google Fonts), JetBrains Mono (JetBrains)
    "display_sm":   ("Barlow Condensed", 11),
    "display_md":   ("Barlow Condensed", 13),
    "display_lg":   ("Barlow Condensed", 16),
    "display_xl":   ("Barlow Condensed", 20),
    "display_2xl":  ("Barlow Condensed", 26),
    "display_bold_sm":  ("Barlow Condensed", 11, "bold"),
    "display_bold_md":  ("Barlow Condensed", 13, "bold"),
    "display_bold_lg":  ("Barlow Condensed", 16, "bold"),
    "display_bold_xl":  ("Barlow Condensed", 20, "bold"),
    "body_sm":      ("Barlow", 11),
    "body_md":      ("Barlow", 13),
    "body_lg":      ("Barlow", 15),
    "mono_sm":      ("JetBrains Mono", 11),
    "mono_md":      ("JetBrains Mono", 13),
    "mono_lg":      ("JetBrains Mono", 16),
    "mono_xl":      ("JetBrains Mono", 20),
}

RADIUS = {
    "sm":  4,
    "md":  6,
    "lg":  8,
}

SPACING = {
    "xs":  4,
    "sm":  8,
    "md":  12,
    "lg":  16,
    "xl":  20,
    "2xl": 28,
}

# Severity → color mapping used across Issues, AI, Corners tabs
SEVERITY = {
    "critical": COLORS["red"],
    "medium":   COLORS["amber"],
    "advisory": COLORS["blue"],
    "good":     COLORS["green"],
    "info":     COLORS["text_secondary"],
}

# Tab definitions — single source of truth for tab order and labels
TABS = [
    "Dashboard", "Issues", "Driver", "Sectors",
    "Corners", "Setup", "AI", "History", "Compare"
]

AI_SUBTABS = ["Advisor", "Agent", "Debrief", "Qualifier"]
