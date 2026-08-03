import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from settings import initialize
from data import ensure_assessment_data_initialized
from colors import PALETTE
import ui

initialize()
ensure_assessment_data_initialized()
ui.inject_css()

df = st.session_state["df_assessments"]

# -- Header -------------------------------------------------------------------
date_min = df["event_timestamp"].min()
date_max = df["event_timestamp"].max()

st.subheader(
    f"Assessments:  {date_min:%b %-d} - {date_max:%b %-d, %Y}",
    divider="violet"
)

# -- Summary tiles ------------------------------------------------------------
total_assessments = len(df)
unique_users      = df["cr_user_id"].nunique()
unique_langs      = df["lang"].nunique()
unique_types      = df["activity_type"].nunique()

# Users with 2+ assessments of the same activity (drives Chart 5 too)
pair_counts = df.groupby(["cr_user_id", "activity_type"]).size()
repeat_users = (
    pair_counts[pair_counts >= 2]
    .index.get_level_values("cr_user_id")
    .nunique()
)

st.markdown(ui.section_header("Summary"), unsafe_allow_html=True)

tile_specs = [
    ("Total Assessments", f"{total_assessments:,}", f"across {unique_users:,} users"),
    ("Unique Users",      f"{unique_users:,}",      f"{repeat_users:,} repeat takers"),
    ("Languages",         f"{unique_langs:,}",      ""),
    ("Activity Types",    f"{unique_types:,}",      ""),
]
st.markdown(ui.tile_row(tile_specs), unsafe_allow_html=True)

# Shared color map — reused across charts that split by activity type
activity_colors = {
    "letter-sounds": PALETTE["plum"],
    "sight-words":   PALETTE["lilac"],
}

# -- Chart 1: Assessments by Language -----------------------------------------
# Shows reach across languages; stacked by activity type to reveal mix
st.subheader("Assessments by Language", divider="violet")

lang_counts = (
    df.groupby(["lang", "activity_type"], as_index=False)
    .size()
    .rename(columns={"size": "assessments"})
)

fig_lang = px.bar(
    lang_counts,
    x="lang",
    y="assessments",
    color="activity_type",
    color_discrete_map=activity_colors,
    labels={"lang": "Language", "assessments": "Assessments", "activity_type": "Activity"},
    barmode="stack",
)
fig_lang.update_layout(
    plot_bgcolor="rgba(0,0,0,0)",
    paper_bgcolor="rgba(0,0,0,0)",
    legend_title_text="Activity Type",
    xaxis_title="Language",
    yaxis_title="Assessments",
)
st.plotly_chart(fig_lang, width="stretch")

# -- Chart 2: Raw Score Distribution by Activity ------------------------------
# Faceted because letter-sounds and sight-words have different max_score scales —
# overlaying them on one axis would be misleading.
st.subheader("Score Distribution", divider="violet")

lang_options = sorted(df["lang"].dropna().unique().tolist())
selected_langs = st.multiselect(
    "Filter by language",
    options=lang_options,
    default=lang_options,
    key="score_dist_langs",
)

dist_df  = df[df["lang"].isin(selected_langs)] if selected_langs else df.iloc[0:0]
scored_df = dist_df.dropna(subset=["score"]).copy()

fig_hist = px.histogram(
    scored_df,
    x="score",
    facet_col="activity_type",
    color="activity_type",
    color_discrete_map=activity_colors,
    labels={"score": "Score", "activity_type": "Activity"},
)
# Different max_score per activity → independent x-axes
fig_hist.update_xaxes(matches=None, showticklabels=True)
fig_hist.update_layout(
    plot_bgcolor="rgba(0,0,0,0)",
    paper_bgcolor="rgba(0,0,0,0)",
    yaxis_title="Assessments",
    showlegend=False,
)
# Strip "activity_type=" prefix from facet titles
fig_hist.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))
st.plotly_chart(fig_hist, width="stretch")
st.caption(f"{len(scored_df):,} of {len(dist_df):,} assessments have a recorded score")

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
# y-axis capped at 100%; some assessments have score > max_score (test data artifact)
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

# -- Chart 5: Score Change — First vs Latest Take -----------------------------
# Dumbbell: per (user, activity) with 2+ scored takes, draw a horizontal line
# from first score to latest score. Color encodes direction of change.
# Replaces an earlier line-over-time chart that read as noise with sparse data.
st.subheader("Score Change: First vs Latest Take", divider="violet")

scored = df.dropna(subset=["score", "event_timestamp"])
pairs = (
    scored.sort_values("event_timestamp")
    .groupby(["cr_user_id", "activity_type"], as_index=False)
    .agg(
        first_score=("score", "first"),
        latest_score=("score", "last"),
        n_takes=("score", "size"),
    )
)
pairs = pairs[pairs["n_takes"] >= 2].copy()
pairs["delta"] = pairs["latest_score"] - pairs["first_score"]

if pairs.empty:
    st.caption("No users have 2+ scored takes of the same activity yet.")
else:
    UP_COLOR   = "#7FA582"   # sage green — improvement
    DOWN_COLOR = "#A57F8F"   # muted rose — regression
    FLAT_COLOR = PALETTE["ink"]

    def _line_color(delta):
        if delta > 0:
            return UP_COLOR
        if delta < 0:
            return DOWN_COLOR
        return FLAT_COLOR

    # Shared vertical legend above both charts (dirs computed across all data)
    direction_entries = []
    if (pairs["delta"] > 0).any():
        direction_entries.append({"shape": "line", "color": UP_COLOR,   "label": "Improved"})
    if (pairs["delta"] < 0).any():
        direction_entries.append({"shape": "line", "color": DOWN_COLOR, "label": "Regressed"})
    if (pairs["delta"] == 0).any():
        direction_entries.append({"shape": "line", "color": FLAT_COLOR, "label": "Unchanged"})
    legend_entries = direction_entries + [
        {"shape": "dot", "color": PALETTE["lilac"], "label": "First take"},
        {"shape": "dot", "color": PALETTE["plum"],  "label": "Latest take"},
    ]
    st.markdown(ui.chart_legend_html(legend_entries), unsafe_allow_html=True)

    activity_cols = st.columns(2)
    for col, activity in zip(activity_cols, ["letter-sounds", "sight-words"]):
        sub = pairs[pairs["activity_type"] == activity].copy()
        if sub.empty:
            with col:
                st.caption(f"No repeat takers for {activity}.")
            continue
        sub = sub.sort_values("delta").reset_index(drop=True)
        sub["y_pos"] = range(len(sub))

        fig = go.Figure()
        # Per-user connecting lines
        for _, row in sub.iterrows():
            fig.add_trace(go.Scatter(
                x=[row["first_score"], row["latest_score"]],
                y=[row["y_pos"], row["y_pos"]],
                mode="lines",
                line=dict(color=_line_color(row["delta"]), width=2),
                showlegend=False,
                hoverinfo="skip",
            ))
        # First-take markers (lighter)
        fig.add_trace(go.Scatter(
            x=sub["first_score"], y=sub["y_pos"],
            mode="markers",
            marker=dict(
                color=PALETTE["lilac"], size=10,
                line=dict(color=PALETTE["plum"], width=1),
            ),
            name="First take",
            customdata=sub[["latest_score", "delta", "n_takes"]].values,
            hovertemplate=(
                "First: %{x}<br>Latest: %{customdata[0]}"
                "<br>Δ: %{customdata[1]:+}<br>%{customdata[2]} takes<extra></extra>"
            ),
        ))
        # Latest-take markers (darker)
        fig.add_trace(go.Scatter(
            x=sub["latest_score"], y=sub["y_pos"],
            mode="markers",
            marker=dict(color=PALETTE["plum"], size=10),
            name="Latest take",
            customdata=sub[["first_score", "delta", "n_takes"]].values,
            hovertemplate=(
                "Latest: %{x}<br>First: %{customdata[0]}"
                "<br>Δ: %{customdata[1]:+}<br>%{customdata[2]} takes<extra></extra>"
            ),
        ))
        # Per-row delta annotations at the right end of each line
        for _, row in sub.iterrows():
            rightmost = max(row["first_score"], row["latest_score"])
            sign = "+" if row["delta"] > 0 else ""
            fig.add_annotation(
                x=rightmost, y=row["y_pos"],
                text=f"<b>{sign}{int(row['delta'])}</b>",
                showarrow=False,
                xanchor="left",
                xshift=8,
                font=dict(size=10, color=_line_color(row["delta"])),
            )
        # Reserve x-axis room on the right for the delta labels
        x_max = float(max(sub["first_score"].max(), sub["latest_score"].max()))
        fig.update_layout(
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(title="Score", range=[-x_max * 0.02, x_max * 1.18]),
            yaxis=dict(showticklabels=False, title="", showgrid=False),
            showlegend=False,
            height=max(200, 28 * len(sub) + 80),
            margin=dict(l=20, r=20, t=10, b=40),
        )
        with col:
            st.markdown(f"**{activity}**")
            st.plotly_chart(fig, width="stretch")

    n_up   = int((pairs["delta"] > 0).sum())
    n_down = int((pairs["delta"] < 0).sum())
    n_flat = int((pairs["delta"] == 0).sum())
    st.caption(
        f"{len(pairs)} (user × activity) pairs · "
        f"{n_up} improved · {n_down} regressed · {n_flat} unchanged"
    )

st.caption(
    f"{unique_users} users · {total_assessments} total assessments"
    " · source: user_sessions_data_raw_latest"
)
