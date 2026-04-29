import streamlit as st
import pandas as pd
import plotly.express as px
from settings import initialize
from data import ensure_data_initialized
from colors import PALETTE

initialize()
ensure_data_initialized()

df = st.session_state["df_assessment_sessions"]

# -- Header -------------------------------------------------------------------
date_min = df["event_timestamp"].min()
date_max = df["event_timestamp"].max()

st.subheader(
    f"Assessment Sessions:  {date_min:%b %-d} - {date_max:%b %-d, %Y}",
    divider="violet"
)

# -- Summary tiles ------------------------------------------------------------
total_sessions = len(df)
unique_users   = df["cr_user_id"].nunique()
unique_langs   = df["lang"].nunique()
unique_types   = df["activity_type"].nunique()

c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Sessions", f"{total_sessions:,}")
c2.metric("Unique Users",   f"{unique_users:,}")
c3.metric("Languages",      f"{unique_langs:,}")
c4.metric("Activity Types", f"{unique_types:,}")

st.divider()

# Shared color map — reused across charts that split by activity type
activity_colors = {
    "letter-sounds": PALETTE["plum"],
    "sight-words":   PALETTE["lilac"],
}

# -- Chart 1: Sessions by Language --------------------------------------------
# Shows reach across languages; stacked by activity type to reveal mix
st.subheader("Sessions by Language", divider="violet")

lang_counts = (
    df.groupby(["lang", "activity_type"], as_index=False)
    .size()
    .rename(columns={"size": "sessions"})
)

fig_lang = px.bar(
    lang_counts,
    x="lang",
    y="sessions",
    color="activity_type",
    color_discrete_map=activity_colors,
    labels={"lang": "Language", "sessions": "Sessions", "activity_type": "Activity"},
    barmode="stack",
)
fig_lang.update_layout(
    plot_bgcolor="rgba(0,0,0,0)",
    paper_bgcolor="rgba(0,0,0,0)",
    legend_title_text="Activity Type",
    xaxis_title="Language",
    yaxis_title="Sessions",
)
st.plotly_chart(fig_lang, width="stretch")

# -- Chart 2: Score Distribution ----------------------------------------------
# x-axis capped at 100% — a small number of sessions have score > max_score
# (test data artifact in Firestore); those points fall outside the visible range
st.subheader("Score Distribution", divider="violet")

lang_options = sorted(df["lang"].dropna().unique().tolist())
selected_langs = st.multiselect(
    "Filter by language",
    options=lang_options,
    default=lang_options,
    key="score_dist_langs",
)

dist_df = df[df["lang"].isin(selected_langs)] if selected_langs else df.iloc[0:0]

# Clip to just below 1.0 so perfect scores land in the 95-100% bin, not an overflow bin
scored = dist_df["score_pct"].dropna().clip(upper=0.99999)

fig_hist = px.histogram(
    scored,
    labels={"value": "Score", "count": "Sessions"},
    color_discrete_sequence=[PALETTE["violet"]],
)
fig_hist.update_traces(
    xbins=dict(start=0, end=1.0001, size=0.05),
    hovertemplate="Score: %{x}<br>Sessions: %{y}<extra></extra>",
)
fig_hist.update_layout(
    plot_bgcolor="rgba(0,0,0,0)",
    paper_bgcolor="rgba(0,0,0,0)",
    xaxis_tickformat=".0%",
    xaxis_title="Score %",
    xaxis_range=[0, 1.05],
    yaxis_title="Sessions",
    showlegend=False,
)
st.plotly_chart(fig_hist, width="stretch")
st.caption(f"{len(scored):,} of {len(dist_df):,} sessions have a recorded score")

# -- Chart 3: Avg Score % by Language -----------------------------------------
st.subheader("Avg Score % by Language", divider="violet")

avg_score = (
    df.groupby(["lang", "activity_type"], as_index=False)["score_pct"]
    .mean()
    .dropna()
)

# Sort languages by overall avg score so the chart reads low-to-high
lang_order = (
    df.groupby("lang")["score_pct"].mean()
    .sort_values()
    .index.tolist()
)

fig_avg = px.bar(
    avg_score,
    x="score_pct",
    y="lang",
    color="activity_type",
    orientation="h",
    barmode="group",
    category_orders={"lang": lang_order},
    color_discrete_map=activity_colors,
    labels={"score_pct": "Avg Score", "lang": "Language", "activity_type": "Activity"},
)
fig_avg.update_layout(
    plot_bgcolor="rgba(0,0,0,0)",
    paper_bgcolor="rgba(0,0,0,0)",
    xaxis_tickformat=".0%",
    xaxis_title="Avg Score %",
    yaxis_title="Language",
    legend_title_text="Activity Type",
)
st.plotly_chart(fig_avg, width="stretch")

# -- Chart 4: Time Spent vs Score % -------------------------------------------
# y-axis capped at 100% to match Chart 2; same test-data outliers excluded visually
st.subheader("Time Spent vs Score %", divider="violet")

scatter_df = df[df["score_pct"].notna()].copy()

fig_scatter = px.scatter(
    scatter_df,
    x="time_spent_sec",
    y="score_pct",
    color="activity_type",
    color_discrete_map=activity_colors,
    hover_data={"lang": True, "cr_user_id": False},
    labels={
        "time_spent_sec": "Time Spent (sec)",
        "score_pct":      "Score",
        "activity_type":  "Activity",
        "lang":           "Language",
    },
)
fig_scatter.update_layout(
    plot_bgcolor="rgba(0,0,0,0)",
    paper_bgcolor="rgba(0,0,0,0)",
    yaxis_tickformat=".0%",
    yaxis_range=[0, 1],
    xaxis_title="Time Spent (sec)",
    yaxis_title="Score %",
    legend_title_text="Activity Type",
)
st.plotly_chart(fig_scatter, width="stretch")

st.caption(
    f"{unique_users} users · {total_sessions} total sessions"
    " · source: user_sessions_data_raw_latest"
)
