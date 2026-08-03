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

# Funnel stage fills — dark → focal → dark, mirroring the olive ramp used by
# `create_engagement_figure` in cl-dashboard-internal so funnels read the same
# across dashboards. Deliberately darker than PALETTE: stage labels sit inside
# the bars, so the fills have to carry light text.
FUNNEL_COLORS = [
    "#3B2A6B",   # deepest violet
    "#4C3688",
    "#5F45A6",
    "#7C5CBF",   # primary violet — focal stage
    "#6B4EB0",
    "#8E6FD0",
    "#443173",
    "#57408F",
]

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
