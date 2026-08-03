"""
ui.py — Styling and HTML tile renderers for the CL Assessment Dashboard.

Ported from the Nairobi Moms dashboard, adapted to the Lavender Dusk palette
and stripped of funnel-specific bits (no 2-letter abbreviation row).
"""

import streamlit as st
import plotly.graph_objects as go
from colors import PALETTE, FUNNEL_COLORS


# Theme text color (matches .streamlit/config.toml textColor)
INK = "#2A1A5E"


def inject_css() -> None:
    st.markdown(f"""
    <style>
    /* Tiles wrap onto extra lines rather than squeezing when the window
       narrows; min-height (not height) lets a tile grow if text still wraps. */
    .cl-tile-row {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
        gap: 8px;
        margin-bottom: 8px;
    }}
    .cl-tile {{
        border-radius: 8px;
        padding: 12px 10px 10px;
        text-align: center;
        min-height: 90px;
        display: flex;
        flex-direction: column;
        justify-content: center;
        gap: 2px;
    }}
    /* Streamlit breaks long words by default — keep tile copy whole. */
    .cl-tile p {{
        overflow-wrap: normal;
        word-break: normal;
    }}
    .cl-tile-label {{
        margin: 0;
        font-size: 10px;
        font-weight: 600;
        letter-spacing: 0.4px;
        text-transform: uppercase;
        opacity: 0.72;
    }}
    .cl-tile-value {{
        margin: 1px 0 0;
        font-size: 22px;
        font-weight: 700;
        line-height: 1.1;
    }}
    .cl-tile-sub {{
        margin: 0;
        font-size: 10px;
        opacity: 0.6;
    }}
    .cl-section-header {{
        font-size: 13px;
        font-weight: 600;
        letter-spacing: 0.5px;
        text-transform: uppercase;
        color: {PALETTE["plum"]};
        margin: 0 0 10px;
        padding-bottom: 6px;
        border-bottom: 1.5px solid {PALETTE["lilac"]};
    }}
    </style>
    """, unsafe_allow_html=True)


def tile_html(label: str, value: str, sub: str = "", bg: str | None = None) -> str:
    """Render a single summary tile. `sub` falls back to a non-breaking space
    so cards keep equal height across a row."""
    bg = bg or PALETTE["ink"]
    sub_text = sub or "&nbsp;"
    return (
        f"<div class='cl-tile' style='background-color:{bg};'>"
        f"<p class='cl-tile-label' style='color:{INK};'>{label}</p>"
        f"<p class='cl-tile-value' style='color:{INK};'>{value}</p>"
        f"<p class='cl-tile-sub' style='color:{INK};'>{sub_text}</p>"
        "</div>"
    )


def tile_row(specs: list[tuple[str, str, str]]) -> str:
    """Render a full row of summary tiles as one responsive grid.

    `specs` is a list of (label, value, sub) tuples; backgrounds cycle through
    TILE_GRADIENT. Tiles reflow onto additional lines on narrow windows instead
    of being squeezed until their text overflows.
    """
    tiles = "".join(
        tile_html(label, value, sub, bg=TILE_GRADIENT[i % len(TILE_GRADIENT)])
        for i, (label, value, sub) in enumerate(specs)
    )
    return f"<div class='cl-tile-row'>{tiles}</div>"


def section_header(text: str) -> str:
    return f"<p class='cl-section-header'>{text}</p>"


# Background colors for a row of summary tiles, light → darker.
# Mirrors the Nairobi `FUNNEL_COLORS` gradient pattern in the Lavender Dusk palette.
TILE_GRADIENT = [
    PALETTE["lavender"],
    PALETTE["ink"],
    PALETTE["lilac"],
    PALETTE["violet"],
]


def funnel_figure(
    labels: list[str],
    values: list[int],
    value_label: str = "Users",
    height: int = 440,
) -> go.Figure:
    """Stage funnel styled to match `create_engagement_figure` in
    cl-dashboard-internal: tapering light outlines, dotted connectors, counts
    inside the bars, and rates on hover.

    `labels` / `values` are expected in funnel order (largest first) — Plotly
    draws them top to bottom as given and does not sort.
    """
    n = len(labels)
    # Outline tapers with the funnel, as in the internal version.
    taper = [4, 3, 2, 2, 2, 1, 1, 1]
    widths = [taper[i] if i < len(taper) else 1 for i in range(n)]

    hovertemplate = [
        f"<b>{label}</b><br>"
        f"{value_label}: {value:,d}"
        "<br>% of previous: %{percentPrevious:.1%}"
        "<br>% of first: %{percentInitial:.1%}<extra></extra>"
        for label, value in zip(labels, values)
    ]

    fig = go.Figure(
        go.Funnel(
            y=labels,
            x=values,
            textposition="auto",
            marker={
                "color": [FUNNEL_COLORS[i % len(FUNNEL_COLORS)] for i in range(n)],
                "line": {"width": widths, "color": [PALETTE["dusk"]] * n},
            },
            connector={"line": {"color": FUNNEL_COLORS[0],
                                "dash": "dot", "width": 3}},
            hovertemplate=hovertemplate,
        )
    )
    fig.update_traces(
        texttemplate="%{value:,d}",
        # Stages that shrink to nothing push their label outside the bar, where
        # it needs the dark ink color instead of the light inside color.
        insidetextfont=dict(color=PALETTE["dusk"]),
        outsidetextfont=dict(color=INK),
    )
    fig.update_layout(
        margin=dict(l=20, r=20, t=20, b=20),
        height=height,
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def chart_legend_html(entries: list[dict]) -> str:
    """Render a compact vertical legend.

    `entries` is a list of dicts: {"shape": "dot" | "line", "color": "#hex", "label": str}.
    Use "line" for trend/direction series and "dot" for marker series.
    """
    rows = []
    for e in entries:
        if e["shape"] == "line":
            marker = (
                f"<span style='display:inline-block; width:14px; height:3px; "
                f"background:{e['color']}; vertical-align:middle; "
                f"margin-right:8px;'></span>"
            )
        else:
            marker = (
                f"<span style='display:inline-block; width:10px; height:10px; "
                f"background:{e['color']}; border-radius:50%; "
                f"vertical-align:middle; margin-right:8px;'></span>"
            )
        rows.append(
            f"<div style='display:flex; align-items:center; "
            f"font-size:11px; color:{INK}; line-height:1.8;'>"
            f"{marker}<span>{e['label']}</span></div>"
        )
    return (
        "<div style='display:flex; flex-direction:column; margin-bottom:8px;'>"
        + "".join(rows)
        + "</div>"
    )
