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

# Sequential ramp for the choropleth. PALETTE alone is too pale to separate a
# country with 3 users from one with 160, so the light end comes from PALETTE and
# the dark end from FUNNEL_COLORS — the same violets, stretched over more range.
# The lightest stop is a visible tint, not PALETTE["dusk"] — countries with no
# users are drawn white, and a one-user country has to read as different.
MAP_SCALE = [
    PALETTE["lavender"],
    PALETTE["lilac"],
    PALETTE["violet"],
    PALETTE["plum"],
    "#7C5CBF",            # primary violet
    "#5F45A6",
    "#3B2A6B",            # deepest violet
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
