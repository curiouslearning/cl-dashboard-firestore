# -----------------------------
# 🎨 Global Color Configuration
# -----------------------------

# Base pastel palette — Sunset Ember
PALETTE = {
    "ember":   "#FFCBA4",   # warm coral-peach
    "coral":   "#FFB38A",   # mid coral
    "blaze":   "#FF9B71",   # deeper orange
    "sand":    "#FFF3E8",   # lightest cream (matches bg)
    "clay":    "#F5E0D0",   # muted terracotta
    "dusk":    "#E8C4A8",   # warm taupe
}

# Metric display names used in the CHART (from long_df["metric_display"])
CHART_METRIC_COLORS = {
    "Max Level Reached":        PALETTE["ember"],
    "Number of Sessions":       PALETTE["blaze"],
    "Total Play Time (min)":    PALETTE["coral"],
    "Avg Session Length (min)": PALETTE["clay"],
    "Active Span (days)":       PALETTE["dusk"],
    "Days to RA":               PALETTE["sand"],
}

# Engagement metric names used in TILES (from get_engagement_metrics)
TILE_METRIC_COLORS = {
    "Avg Level Reached":          PALETTE["ember"],
    "Avg # Sessions / User":      PALETTE["blaze"],
    "Avg Total Play Time / User": PALETTE["coral"],
    "Avg Session Length / User":  PALETTE["clay"],
    "Active Span / User":         PALETTE["dusk"],
    "Avg Days to RA":             PALETTE["sand"],
}
