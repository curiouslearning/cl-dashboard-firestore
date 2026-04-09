import streamlit as st
import pandas as pd
from settings import initialize
from data import ensure_data_initialized

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
unique_users = df["cr_user_id"].nunique()
unique_langs = df["lang"].nunique()
unique_types = df["activity_type"].nunique()

c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Sessions",    f"{total_sessions:,}")
c2.metric("Unique Users",      f"{unique_users:,}")
c3.metric("Languages",         f"{unique_langs:,}")
c4.metric("Activity Types",    f"{unique_types:,}")

st.divider()

# -- Per-user summary table ---------------------------------------------------
st.subheader("Sessions by User")

user_summary = (
    df.groupby("cr_user_id", as_index=False)
    .agg(
        sessions=("cr_user_id",      "count"),
        avg_score_pct=("score_pct",       "mean"),
        avg_time_sec=("time_spent_sec",  "mean"),
        activity_types=("activity_type", lambda x: ", ".join(
            sorted(x.dropna().unique()))),
        languages=("lang", lambda x: ", ".join(sorted(x.dropna().unique()))),
        last_seen=("event_timestamp", "max"),
    )
    .sort_values("sessions", ascending=False)
    .reset_index(drop=True)
)

user_summary["avg_score_pct"] = user_summary["avg_score_pct"].map(
    lambda v: f"{v:.0%}" if pd.notna(v) else "-"
)
user_summary["avg_time_sec"] = user_summary["avg_time_sec"].map(
    lambda v: f"{v:.1f}s" if pd.notna(v) else "-"
)
user_summary["last_seen"] = user_summary["last_seen"].dt.strftime(
    "%Y-%m-%d %H:%M")

user_summary.columns = [
    "User ID", "Sessions", "Avg Score", "Avg Time",
    "Activity Types", "Languages", "Last Seen",
]

st.dataframe(user_summary, use_container_width=True, hide_index=True)

st.caption(
    f"{unique_users} users · {total_sessions} total sessions"
    " · source: user_sessions_data_raw_latest"
)
