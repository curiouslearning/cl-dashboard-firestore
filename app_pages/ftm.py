import streamlit as st
import pandas as pd
import plotly.express as px
from settings import initialize
from data import ensure_ftm_data_initialized
from colors import PALETTE, MAP_SCALE
import ui

initialize()
ensure_ftm_data_initialized()
ui.inject_css()

df_all = st.session_state["df_ftm"]

# -- Empty guard (no FTM rows at all) -----------------------------------------
if df_all.empty:
    st.subheader("Feed the Monster", divider="violet")
    st.info("No feed-the-monster rows found in `summary_data_raw_latest`.")
    st.stop()

# -- Scope: date cutoff + production only --------------------------------------
# Rows before START_DATE predate the full summary field set. firestore_timestamp
# is used because it is populated on every row. Test and environment-less rows
# are dropped so every number on this page is real production activity.
START_DATE = pd.Timestamp("2026-08-1", tz="UTC")
df = df_all[
    (df_all["created_at"] >= START_DATE)
    & (df_all["environment"] == "production")
]

# -- Scope-empty guard --------------------------------------------------------
if df.empty:
    st.subheader("Feed the Monster", divider="violet")
    st.info(
        f"No production rows on or after {START_DATE:%b %-d, %Y}. Earlier rows "
        "predate the full summary field set, and test rows are excluded."
    )
    st.stop()

# -- Sidebar filters ----------------------------------------------------------
# Applied to the scoped frame before anything is computed, so every tile, funnel
# and chart below describes the same filtered population. Options are drawn from
# the scoped rows, so a value that only appears in test or pre-cutoff data is
# never offered. The two filters are independent — an unlikely pairing can select
# nothing, which the guard below reports.
ALL = "All"


def sidebar_filter(label: str, column: str, frame: pd.DataFrame) -> str:
    options = [ALL] + sorted(frame[column].dropna().unique().tolist())
    return st.sidebar.selectbox(label, options, key=f"ftm_filter_{column}")


st.sidebar.markdown("### Filters")
active_filters = {
    column: sidebar_filter(label, column, df)
    for label, column in (("Language", "language"), ("Country", "country"))
}
for column, selected in active_filters.items():
    if selected != ALL:
        df = df[df[column] == selected]

filter_label = " · ".join(v for v in active_filters.values() if v != ALL)

# -- Header -------------------------------------------------------------------
ts = df["created_at"]
if not ts.empty:
    st.subheader(
        f"Feed the Monster:  {ts.min():%b %-d} - {ts.max():%b %-d, %Y}",
        divider="violet",
    )
else:
    st.subheader("Feed the Monster", divider="violet")

# -- Filter-empty guard -------------------------------------------------------
if df.empty:
    st.info(f"No production rows match the selected filters ({filter_label}).")
    st.stop()

if filter_label:
    st.caption(f"Filtered to {filter_label}.")

# -- Summary metrics ----------------------------------------------------------
# Computed by function rather than inline, because the world map renders the same
# tiles per country on hover — one implementation keeps the two from drifting.
def roll_up(frame: pd.DataFrame) -> pd.DataFrame:
    """Per-user totals. Some users have more than one summary doc, so anything
    described "per user" (tiles, milestones, map) must sum theirs first."""
    return frame.groupby("cr_user_id").agg(
        max_level=("highest_level_completed", "max"),
        total_sec=("time_spent_total_sec", "sum"),
    )


def summary_stats(frame: pd.DataFrame) -> dict:
    """Every number behind the summary tiles, for the page or any slice of it."""
    users_df = roll_up(frame)
    users = len(users_df)
    puzzles = int(frame["puzzles_completed"].sum())
    solved = int(frame["puzzle_success"].sum())

    # "Recorded" play time means a positive per-user total: a null
    # time_spent_total_sec sums to 0, so users with no record and users with a
    # literal 0 land together. The average covers only users who did play; the
    # companion tile counts the rest, plus anyone under a minute, as negligible.
    played = users_df["total_sec"] > 0
    n_played = int(played.sum())
    n_negligible = int((users_df["total_sec"] < 60).sum())

    # Readers Acquired uses the same rule as the ftm_level_25 milestone below —
    # per-user highest level ≥ 25 — so the tile and the funnel stage agree.
    ra_users = int((users_df["max_level"] >= 25).sum())

    return {
        "records": len(frame),
        "users": users,
        "success_rate": solved / puzzles if puzzles else 0.0,
        "play_hours": users_df["total_sec"].sum() / 3600,
        "avg_play_min": (
            users_df.loc[played, "total_sec"].sum() / n_played / 60 if n_played else 0.0
        ),
        "n_played": n_played,
        "n_negligible": n_negligible,
        "negligible_pct": n_negligible / users if users else 0.0,
        "ra_users": ra_users,
        "ra_pct": ra_users / users if users else 0.0,
        "max_level": frame["highest_level_completed"].max(),
    }


def n_users_label(n: int) -> str:
    """"1 user" / "2 users" — sparsely populated countries hit the singular
    often enough on the map to be worth getting right."""
    return f"{n:,} user" + ("" if n == 1 else "s")


def tile_specs_for(s: dict) -> list[tuple[str, str, str]]:
    """(label, value, sub) triples for `ui.tile_row` — and, joined into lines,
    for the map's hover card."""
    max_level = "—" if pd.isna(s["max_level"]) else f"{int(s['max_level']):,}"
    return [
        ("Records",           f"{s['records']:,}",         f"across {n_users_label(s['users'])}"),
        ("Unique Users",      f"{s['users']:,}",           ""),
        ("Avg Play Time",     f"{s['avg_play_min']:,.1f} m", f"per playing user ({s['n_played']:,})"),
        ("No Play Time",      f"{s['negligible_pct']:.0%}",  f"{n_users_label(s['n_negligible'])} under 1 min"),
        ("Success Rate",      f"{s['success_rate']:.0%}",  "solved / attempted"),
        ("Play Time",         f"{s['play_hours']:,.1f} h", "where recorded"),
        ("Max Level Reached", max_level,                   ""),
        ("Readers Acquired",  f"{s['ra_pct']:.0%}",        f"{n_users_label(s['ra_users'])} at level 25+"),
    ]


per_user = roll_up(df)
n_users = len(per_user)
stats = summary_stats(df)
unique_users = stats["users"]
total_records = stats["records"]

# -- Summary tiles ------------------------------------------------------------
st.markdown(ui.section_header("Summary"), unsafe_allow_html=True)
st.markdown(ui.tile_row(tile_specs_for(stats)), unsafe_allow_html=True)

# Short label for chart hovers (raw ids are long)
df = df.copy()
df["user_short"] = df["cr_user_id"].str.slice(0, 10)

# -- World map ----------------------------------------------------------------
# Shaded by unique users; hovering a country shows that country's own summary
# tiles, built by the same `tile_specs_for` that renders the row above.
st.subheader("Users by Country", divider="violet")

# `country` is a plain English name, which is what locationmode="country names"
# matches on. Rows with no country, or the literal "unknown" the app sends when
# geolocation fails, cannot be placed — they are dropped here and counted in the
# caption so the map's user total is never mistaken for the page's.
#
# Plotly matches Natural Earth's admin-0 spellings and silently drops anything
# else, so values the app spells differently are remapped rather than lost.
COUNTRY_ALIASES = {"Palestinian Territory": "Palestine"}

geo_df = df[df["country"].notna() & (df["country"].str.lower() != "unknown")].copy()
geo_df["country"] = geo_df["country"].replace(COUNTRY_ALIASES)
unplaceable_users = n_users - geo_df["cr_user_id"].nunique()

if geo_df.empty:
    st.info("No rows in this selection carry a country.")
else:
    country_rows = []
    for country, group in geo_df.groupby("country"):
        country_stats = summary_stats(group)
        hover = f"<b>{country}</b><br>" + "<br>".join(
            f"{label}: <b>{value}</b>" + (f" <i>({sub})</i>" if sub else "")
            for label, value, sub in tile_specs_for(country_stats)
        )
        country_rows.append(
            {"country": country, "users": country_stats["users"], "hover": hover}
        )
    country_df = pd.DataFrame(country_rows).sort_values("users", ascending=False)

    fig_map = px.choropleth(
        country_df,
        locations="country",
        locationmode="country names",
        color="users",
        color_continuous_scale=MAP_SCALE,
        labels={"users": "Users"},
    )
    fig_map.update_traces(
        customdata=country_df[["hover"]],
        hovertemplate="%{customdata[0]}<extra></extra>",
        marker_line_color=PALETTE["dusk"],
        marker_line_width=0.5,
    )
    # Countries with no users still need to read as land, not as a hole in the
    # ocean, so they get a flat fill a shade lighter than the ramp's first stop.
    fig_map.update_geos(
        projection_type="natural earth",
        showframe=False,
        showcoastlines=False,
        showland=True,
        landcolor="#FFFFFF",
        showocean=False,
        bgcolor="rgba(0,0,0,0)",
    )
    fig_map.update_layout(
        height=520,
        margin=dict(l=0, r=0, t=10, b=0),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        coloraxis_colorbar=dict(title="Users"),
    )
    st.plotly_chart(fig_map, width="stretch")

    caption = (
        f"{geo_df['cr_user_id'].nunique():,} users across "
        f"{len(country_df):,} countries. Hover a country for its own summary tiles."
    )
    if unplaceable_users:
        caption += (
            f" {unplaceable_users:,} users are not shown — their rows carry no "
            "country or an `unknown` one."
        )
    st.caption(caption)

# -- Engagement funnels -------------------------------------------------------
# Mirrors the one-time conversion events sent to Firebase Analytics (see
# "Firebase Analytics — Ad-Optimization Milestones"). Firebase is not a source
# here and the container-level `user_profiles` collection is not exported to
# BigQuery yet, so every milestone is reconstructed **in Feed the Monster terms**
# from summary_data. Where the real event is cross-app (begin_play, the play_*
# thresholds), the FTM-only version is a lower bound.
#
# `play_sessions_3` and `habit_4_days_week` are deliberately omitted: both need
# the event log, and neither is trustworthy yet — there is no app-launch event
# to count, and a rolling 7-day window needs more history than this page covers.
#
# Milestones are per install, so they read from the `per_user` rollup built for
# the tiles — users with more than one summary doc must not count twice.
st.subheader("Engagement Funnels", divider="violet")

# The milestones are two independent tracks — level progress and play time —
# so they get one funnel each. Interleaved they do not taper (ftm_level_25 sits
# below play_10_min); split by track, each is naturally monotonic and its
# "% of previous" reads as a real step-down.
#
# `begin_play` heads both funnels as the shared baseline. Every user in this
# frame has an FTM summary record, so it is 100% by construction.
BEGAN_PLAY = ("begin_play", "Began play", pd.Series(True, index=per_user.index))

LEVEL_MILESTONES = [
    BEGAN_PLAY,
    ("ftm_level_1_complete", "FTM Level 1 completed", per_user["max_level"] >= 1),
    ("ftm_level_25", "FTM Level 25 reached", per_user["max_level"] >= 25),
]

PLAY_MILESTONES = [
    BEGAN_PLAY,
    ("play_10_min",   "Play time ≥ 10 min",   per_user["total_sec"] >= 600),
    ("play_1_hour",   "Play time ≥ 1 hour",   per_user["total_sec"] >= 3_600),
    ("play_3_hours",  "Play time ≥ 3 hours",  per_user["total_sec"] >= 10_800),
    ("play_10_hours", "Play time ≥ 10 hours", per_user["total_sec"] >= 36_000),
]


def milestone_frame(spec) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "event": event,
                "milestone": label,
                "users": int(reached.sum()),
                "pct": reached.sum() / n_users if n_users else 0.0,
            }
            for event, label, reached in spec
        ]
    )


level_ms = milestone_frame(LEVEL_MILESTONES)
play_ms = milestone_frame(PLAY_MILESTONES)

# Matching heights keep the two funnels aligned despite the differing stage counts.
col_level, col_play = st.columns(2)
with col_level:
    st.markdown(ui.section_header("Level Progress"), unsafe_allow_html=True)
    st.plotly_chart(
        ui.funnel_figure(level_ms["milestone"].tolist(), level_ms["users"].tolist()),
        width="stretch",
    )
with col_play:
    st.markdown(ui.section_header("Play Time"), unsafe_allow_html=True)
    st.plotly_chart(
        ui.funnel_figure(play_ms["milestone"].tolist(), play_ms["users"].tolist()),
        width="stretch",
    )

st.caption(
    f"Share of the {n_users:,} production users in this window who have crossed "
    "each threshold, reconstructed in Feed the Monster terms. Both funnels start "
    "from the same `begin_play` baseline. `begin_play` and the `play_*` "
    "thresholds fire in-app on activity across **all** apps, so the FTM-only "
    "figures here are a lower bound until `user_profiles` is exported to BigQuery."
)

with st.expander("How each milestone is derived"):
    st.markdown(
        """
| Event | FTM reconstruction |
| --- | --- |
| `begin_play` | has an FTM summary record — 100% by construction, since the page's user base *is* users with FTM activity |
| `ftm_level_1_complete` | `highest_level_completed` ≥ 1 |
| `ftm_level_25` | `highest_level_completed` ≥ 25 |
| `play_10_min` … `play_10_hours` | summed `time_spent_total_second` ≥ threshold — **FTM time only**, not cross-app |

Two spec milestones are not shown. `play_sessions_3` needs app-launch counts,
but the event log carries only `puzzle_completed` and `level_completed`, so any
figure would be reconstructed play sessions rather than true launches.
`habit_4_days_week` needs more history than this page covers — a rolling 7-day
window cannot fill up yet. Both become straightforward once `user_profiles` is
exported to BigQuery.
"""
    )

# -- Chart: Volume vs Success Rate --------------------------------------------
st.subheader("Volume vs Success Rate", divider="violet")

# Every row is production now, so there is nothing to split by color.
scatter_df = df.dropna(subset=["puzzle_success_pct"]).copy()

fig_sc = px.scatter(
    scatter_df,
    x="puzzles_completed",
    y="puzzle_success_pct",
    color_discrete_sequence=[PALETTE["plum"]],
    hover_data={"user_short": True, "language": True, "country": True},
    labels={
        "puzzles_completed": "Puzzles Completed",
        "puzzle_success_pct": "Success Rate",
        "user_short": "User",
        "language": "Language",
        "country": "Country",
    },
)
fig_sc.update_layout(
    plot_bgcolor="rgba(0,0,0,0)",
    paper_bgcolor="rgba(0,0,0,0)",
    yaxis_tickformat=".0%",
    yaxis_range=[0, 1.02],
    xaxis_title="Puzzles Completed",
    yaxis_title="Success Rate",
    showlegend=False,
)
st.plotly_chart(fig_sc, width="stretch")

# -- Field completeness --------------------------------------------------------
# How complete is each field? Surfaces the sparse metadata/attribution blocks.
tracked_cols = [
    "cr_user_id", "operation", "environment", "language", "country",
    "highest_level_completed", "levels_completed",
    "puzzle_success", "puzzle_failure", "puzzles_completed", "puzzle_success_pct",
    "time_spent_total_sec", "time_spent_total_min",
    "app_version", "container_app_version", "container_version", "schema_version",
    "campaign_id", "source", "hostname", "apk_package_name",
    "created_at", "updated_at", "synced_at", "event_timestamp",
    "document_id", "event_id",
]
tracked_cols = [c for c in tracked_cols if c in df.columns]

completeness = (
    df[tracked_cols].notna().sum()
    .rename("populated")
    .to_frame()
)
completeness["of_rows"] = len(df)
# 0–100 so the ProgressColumn's numeric label matches its bar fill.
completeness["pct"] = (completeness["populated"] / len(df) * 100).round(0)
st.markdown(ui.section_header("Field Completeness"), unsafe_allow_html=True)
st.dataframe(
    completeness.reset_index(names="field"),
    width="stretch",
    hide_index=True,
    column_config={"pct": st.column_config.ProgressColumn(
        "Populated %", format="%.0f%%", min_value=0, max_value=100,
    )},
)

st.caption(
    f"{unique_users} users · {total_records} records · "
    "source: ftm-b9d99.firestore_export.summary_data_raw_latest (app_id='feed-the-monster')"
)
