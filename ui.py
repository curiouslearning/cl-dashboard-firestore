"""
ui.py — Styling and HTML tile renderers for the CL Assessment Dashboard.

Ported from the Nairobi Moms dashboard, adapted to the Lavender Dusk palette
and stripped of funnel-specific bits (no 2-letter abbreviation row).
"""

import streamlit as st
from colors import PALETTE


# Theme text color (matches .streamlit/config.toml textColor)
INK = "#2A1A5E"


def inject_css() -> None:
    st.markdown(f"""
    <style>
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
    return f"""
    <div style="background-color:{bg}; border-radius:8px; padding:12px 8px 10px;
                text-align:center; height:90px; display:flex; flex-direction:column;
                justify-content:center; gap:2px; margin-bottom:8px;">
        <p class="cl-tile-label" style="color:{INK};">{label}</p>
        <p class="cl-tile-value" style="color:{INK};">{value}</p>
        <p class="cl-tile-sub" style="color:{INK};">{sub_text}</p>
    </div>
    """


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
