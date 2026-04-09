# -----------------------------
# 🎨 Global Color Configuration
# -----------------------------

# Base palette — Lavender Dusk
PALETTE = {
    "lavender": "#E4DEFA",   # light violet (secondary bg)
    "lilac":    "#CFC6F5",   # mid lavender
    "violet":   "#B8ACEE",   # deeper violet
    "dusk":     "#F2EFFC",   # lightest (matches bg)
    "plum":     "#9B85D4",   # muted plum
    "ink":      "#D6D0F0",   # cool lavender-grey
}

# Metric display names used in the CHART (from long_df["metric_display"])
CHART_METRIC_COLORS = {
    "Max Level Reached":        PALETTE["lavender"],
    "Number of Sessions":       PALETTE["lilac"],
    "Total Play Time (min)":    PALETTE["violet"],
    "Avg Session Length (min)": PALETTE["plum"],
    "Active Span (days)":       PALETTE["ink"],
    "Days to RA":               PALETTE["dusk"],
}

# Engagement metric names used in TILES (from get_engagement_metrics)
TILE_METRIC_COLORS = {
    "Avg Level Reached":          PALETTE["lavender"],
    "Avg # Sessions / User":      PALETTE["lilac"],
    "Avg Total Play Time / User": PALETTE["violet"],
    "Avg Session Length / User":  PALETTE["plum"],
    "Active Span / User":         PALETTE["ink"],
    "Avg Days to RA":             PALETTE["dusk"],
}
