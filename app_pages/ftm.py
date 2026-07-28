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

# -- Environment filter: production only --------------------------------------
# The FTM summary feed flips on in production soon; this page reports on
# production data. Until it's live, `production` is empty, so expose a toggle
# (shown only while there are no production rows) to preview test data. Once
# real production rows land, the toggle disappears and the page is prod-only.
prod_mask = df_all["environment"] == "production"
n_prod = int(prod_mask.sum())

preview_test = False
if n_prod == 0:
    preview_test = st.toggle(
        "Preview non-production data (production feed not live yet)",
        value=False,
        help="No production rows yet. Enable to inspect test-environment rows "
             "while the feature is pre-launch.",
    )

df = df_all if preview_test else df_all[prod_mask]

# -- Header -------------------------------------------------------------------
ts = df["event_timestamp"].dropna() if not df.empty else df["event_timestamp"]
if not ts.empty:
    st.subheader(
        f"Feed the Monster:  {ts.min():%b %-d} - {ts.max():%b %-d, %Y}",
        divider="violet",
    )
else:
    st.subheader("Feed the Monster", divider="violet")

scope = "all environments (preview)" if preview_test else "production"
st.caption(
    f"Reporting on **{scope}** rows of `summary_data` where "
    "`app_id = 'feed-the-monster'`. Charts below are provisional."
)

# -- Production-empty guard ---------------------------------------------------
if df.empty:
    st.info(
        "No **production** rows yet — the Feed the Monster summary feed isn't "
        "live in production. Enable the preview toggle above to inspect test data."
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
cols = st.columns(len(tile_specs))
for i, (col, (label, value, sub)) in enumerate(zip(cols, tile_specs)):
    bg = ui.TILE_GRADIENT[i % len(ui.TILE_GRADIENT)]
    with col:
        st.markdown(ui.tile_html(label, value, sub, bg=bg), unsafe_allow_html=True)

# Short label for per-record charts (users repeat and ids are long)
df = df.copy()
df["user_short"] = df["cr_user_id"].str.slice(0, 10)
df["record"] = df["user_short"] + " · #" + (df.groupby("cr_user_id").cumcount() + 1).astype(str)

# -- Chart 1: Puzzle outcomes by record ---------------------------------------
# success / failure are populated on every row, so this is the most reliable view.
st.subheader("Puzzle Outcomes by Record", divider="violet")

outcomes = (
    df[["record", "puzzle_success", "puzzle_failure"]]
    .melt(id_vars="record", var_name="outcome", value_name="count")
)
outcomes["outcome"] = outcomes["outcome"].map(
    {"puzzle_success": "Solved", "puzzle_failure": "Failed"}
)
order = df.sort_values("puzzles_completed", ascending=True)["record"].tolist()

fig_out = px.bar(
    outcomes,
    x="count",
    y="record",
    color="outcome",
    orientation="h",
    barmode="stack",
    category_orders={"record": order, "outcome": ["Solved", "Failed"]},
    color_discrete_map={"Solved": PALETTE["plum"], "Failed": PALETTE["ink"]},
    labels={"count": "Puzzles", "record": "User · record", "outcome": "Outcome"},
)
fig_out.update_layout(
    plot_bgcolor="rgba(0,0,0,0)",
    paper_bgcolor="rgba(0,0,0,0)",
    legend_title_text="Outcome",
    height=max(280, 26 * df["record"].nunique() + 80),
    margin=dict(l=10, r=10, t=10, b=40),
)
st.plotly_chart(fig_out, width="stretch")

# -- Chart 2: Volume vs Success Rate ------------------------------------------
st.subheader("Volume vs Success Rate", divider="violet")

env_colors = {"test": PALETTE["violet"], "production": PALETTE["plum"]}
scatter_df = df.dropna(subset=["puzzle_success_pct"]).copy()
scatter_df["environment"] = scatter_df["environment"].fillna("unknown")

fig_sc = px.scatter(
    scatter_df,
    x="puzzles_completed",
    y="puzzle_success_pct",
    color="environment",
    color_discrete_map={**env_colors, "unknown": PALETTE["lilac"]},
    hover_data={"user_short": True, "language": True, "country": True},
    labels={
        "puzzles_completed": "Puzzles Completed",
        "puzzle_success_pct": "Success Rate",
        "environment": "Environment",
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
    legend_title_text="Environment",
)
st.plotly_chart(fig_sc, width="stretch")

# -- Chart 3: Level progression -----------------------------------------------
# levels_completed / highest_level_completed present on ~2/3 of rows.
st.subheader("Level Progression by Record", divider="violet")

lvl = df.dropna(subset=["levels_completed", "highest_level_completed"]).copy()
if lvl.empty:
    st.caption("No rows carry level-progression fields yet.")
else:
    lvl_long = (
        lvl[["record", "levels_completed", "highest_level_completed"]]
        .melt(id_vars="record", var_name="metric", value_name="level")
    )
    lvl_long["metric"] = lvl_long["metric"].map({
        "levels_completed": "Levels Completed",
        "highest_level_completed": "Highest Level Reached",
    })
    lvl_order = lvl.sort_values("levels_completed")["record"].tolist()
    fig_lvl = px.bar(
        lvl_long,
        x="level",
        y="record",
        color="metric",
        orientation="h",
        barmode="group",
        category_orders={"record": lvl_order},
        color_discrete_map={
            "Levels Completed": PALETTE["plum"],
            "Highest Level Reached": PALETTE["violet"],
        },
        labels={"level": "Level", "record": "User · record", "metric": "Metric"},
    )
    fig_lvl.update_layout(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        legend_title_text="",
        height=max(280, 26 * lvl["record"].nunique() + 80),
        margin=dict(l=10, r=10, t=10, b=40),
    )
    st.plotly_chart(fig_lvl, width="stretch")

# -- Raw data + field completeness --------------------------------------------
st.subheader("Flattened Records", divider="violet")

display_cols = [
    "cr_user_id", "operation", "environment", "language", "country",
    "highest_level_completed", "levels_completed",
    "puzzle_success", "puzzle_failure", "puzzles_completed", "puzzle_success_pct",
    "time_spent_total_sec", "time_spent_total_min",
    "app_version", "container_app_version", "container_version", "schema_version",
    "campaign_id", "source", "hostname", "apk_package_name",
    "created_at", "updated_at", "synced_at", "event_timestamp",
    "document_id", "event_id",
]
display_cols = [c for c in display_cols if c in df.columns]
st.dataframe(
    df[display_cols].sort_values("event_timestamp", ascending=False, na_position="last"),
    width="stretch",
    hide_index=True,
)

# How complete is each field? Surfaces the sparse metadata/attribution blocks.
completeness = (
    df[display_cols].notna().sum()
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
