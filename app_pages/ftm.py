import streamlit as st
import pandas as pd
import plotly.express as px
from settings import initialize
from data import ensure_ftm_data_initialized
from colors import PALETTE
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
START_DATE = pd.Timestamp("2026-07-29", tz="UTC")
df = df_all[
    (df_all["firestore_timestamp"] >= START_DATE)
    & (df_all["environment"] == "production")
]

# -- Header -------------------------------------------------------------------
ts = df["firestore_timestamp"]
if not ts.empty:
    st.subheader(
        f"Feed the Monster:  {ts.min():%b %-d} - {ts.max():%b %-d, %Y}",
        divider="violet",
    )
else:
    st.subheader("Feed the Monster", divider="violet")

# -- Scope-empty guard --------------------------------------------------------
if df.empty:
    st.info(
        f"No production rows on or after {START_DATE:%b %-d, %Y}. Earlier rows "
        "predate the full summary field set, and test rows are excluded."
    )
    st.stop()

# -- Summary tiles ------------------------------------------------------------
total_records   = len(df)
unique_users    = df["cr_user_id"].nunique()
puzzles_done    = int(df["puzzles_completed"].sum())
success_total   = int(df["puzzle_success"].sum())
success_rate    = success_total / puzzles_done if puzzles_done else 0.0
play_hours      = df["time_spent_total_sec"].sum(skipna=True) / 3600
max_level       = df["highest_level_completed"].max()
max_level_str   = "—" if pd.isna(max_level) else f"{int(max_level):,}"

st.markdown(ui.section_header("Summary"), unsafe_allow_html=True)

tile_specs = [
    ("Records",          f"{total_records:,}",   f"across {unique_users:,} users"),
    ("Unique Users",     f"{unique_users:,}",    ""),
    ("Puzzles Completed", f"{puzzles_done:,}",   f"{success_total:,} solved"),
    ("Success Rate",     f"{success_rate:.0%}",  "solved / attempted"),
    ("Play Time",        f"{play_hours:,.1f} h", "where recorded"),
    ("Max Level Reached", max_level_str,          ""),
]
st.markdown(ui.tile_row(tile_specs), unsafe_allow_html=True)

# Short label for chart hovers (raw ids are long)
df = df.copy()
df["user_short"] = df["cr_user_id"].str.slice(0, 10)

# -- Ad-optimization milestones -----------------------------------------------
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
# Milestones are per install, so totals are rolled up per cr_user_id first —
# users with more than one summary doc must not count twice.
st.subheader("Ad-Optimization Milestones", divider="violet")

per_user = df.groupby("cr_user_id").agg(
    max_level=("highest_level_completed", "max"),
    total_sec=("time_spent_total_sec", "sum"),
)
n_users = len(per_user)

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
