"""
Assessment × Feed the Monster — cohort comparison.

A first look at how the two user bases relate: who shows up in each app, who
shows up in both, and whether FTM engagement travels with assessment success.

Scoped by date (from `COMPARISON_START_DATE`, before which FTM wrote nothing to
Firestore) and to languages both apps offer. Both filters discard a lot on
purpose — without them the cohorts compare users who *couldn't* have done the
other thing against users who chose not to.

No `environment` filter, unlike the FTM page: assessment rows carry no
`metadata.environment` at all, so it would drop every assessment user.
"""

import re

import streamlit as st
import pandas as pd
import plotly.express as px
from settings import initialize
from data import (
    ensure_comparison_data_initialized,
    shared_languages,
    COMPARISON_START_DATE,
)
from colors import PALETTE, FUNNEL_COLORS
import ui

initialize()
ensure_comparison_data_initialized()
ui.inject_css()

df_all = st.session_state["df_comparison"]

BOTH, A_ONLY, F_ONLY = "Both", "Assessment only", "FTM only"
COHORT_COLORS = {
    BOTH:   FUNNEL_COLORS[3],   # primary violet — the focal cohort
    A_ONLY: FUNNEL_COLORS[1],
    F_ONLY: FUNNEL_COLORS[5],
}

# -- Empty guard --------------------------------------------------------------
if df_all.empty:
    st.subheader("Assessment × Feed the Monster", divider="violet")
    st.info(
        f"No rows for either app on or after {COMPARISON_START_DATE}."
    )
    st.stop()

st.subheader("Assessment × Feed the Monster", divider="violet")

# -- Shared-language scope ----------------------------------------------------
# Computed from the already date-scoped frame, so a language that only appears
# in older data never enters the shared set.
shared = shared_languages(df_all)
df = df_all[df_all["match_lang"].isin(shared)]


def _prettify(label: str) -> str:
    """`west-african-english` and `IndianEnglish` both become title-cased words.

    The two apps disagree on both casing and separators, so a raw label would
    render the shared-language list as "English, french, hausa" depending on
    which app happened to supply each one.
    """
    # Split on separators, and on lowercase→uppercase boundaries for camelCase.
    # Only that boundary — splitting runs of capitals turns `SAenglish` into
    # "S Aenglish". Each word keeps its own capitals; only the first letter is
    # forced up, so `SAenglish` survives as-is rather than becoming "Saenglish".
    spaced = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", label)
    words = [w for w in re.split(r"[-_ ]+", spaced) if w]
    return " ".join(w[0].upper() + w[1:] for w in words) or label


def language_labels(frame: pd.DataFrame, keys: set[str]) -> list[str]:
    """Human-readable names for normalized language keys, using the spellings
    that actually appear in the data rather than a hand-maintained list."""
    labels = (
        frame.dropna(subset=["match_lang", "match_lang_label"])
        .groupby("match_lang")["match_lang_label"]
        .agg(lambda s: s.mode().iat[0])
    )
    return sorted(_prettify(str(labels.get(k, k))) for k in keys)


a_langs = set(df_all.loc[df_all["cohort"] != "FTM only", "a_lang_norm"].dropna())
f_langs = set(df_all.loc[df_all["cohort"] != "Assessment only", "f_lang_norm"].dropna())
dropped_assessment_langs = language_labels(df_all, a_langs - shared)
dropped_ftm_langs = language_labels(df_all, f_langs - shared)
# `metadata.language` only ships from container 2.34.5, so the loader backfills
# it from the event log. What is left after that genuinely has no language
# anywhere, and cannot be matched to an assessment that may or may not exist.
n_backfilled = int(df_all["f_language_backfilled"].fillna(False).astype(bool).sum())
unknown_lang_ftm = int(
    ((df_all["cohort"] != "Assessment only") & df_all["f_lang_norm"].isna()).sum()
)

if df.empty:
    st.info(
        "No users remain after restricting to languages present in both apps. "
        f"Assessment languages: {', '.join(language_labels(df_all, a_langs)) or '—'}. "
        f"FTM languages: {', '.join(language_labels(df_all, f_langs)) or '—'}."
    )
    st.stop()

# -- Cohorts ------------------------------------------------------------------
both = df[df["cohort"] == BOTH]
a_only = df[df["cohort"] == A_ONLY]
f_only = df[df["cohort"] == F_ONLY]

n_assessment = len(both) + len(a_only)
n_ftm = len(both) + len(f_only)
n_both = len(both)

# -- Summary tiles ------------------------------------------------------------
st.markdown(ui.section_header("Cohorts"), unsafe_allow_html=True)
st.markdown(
    ui.tile_row([
        ("Assessment Users", f"{n_assessment:,}", "took ≥ 1 assessment"),
        ("FTM Users",        f"{n_ftm:,}",        "have ≥ 1 FTM record"),
        ("Both",             f"{n_both:,}",       "appear in both apps"),
        ("Of Assessment",    f"{n_both / n_assessment:.1%}" if n_assessment else "—",
                             "of assessment users also play FTM"),
        ("Of FTM",           f"{n_both / n_ftm:.1%}" if n_ftm else "—",
                             "of FTM users also assess"),
    ]),
    unsafe_allow_html=True,
)

# One scope line and one warning. The detail lives in the notes expander at the
# bottom — repeating it here just pushed the actual charts below the fold.
shared_label = ", ".join(language_labels(df_all, shared))
st.caption(
    f"Scope: from {COMPARISON_START_DATE}, in {shared_label} "
    f"({len(shared)} of {len(f_langs)} FTM languages have an assessment)."
)

st.warning(
    f"**The overlap is {n_both} users.** Everything below rests on that cohort, "
    f"so read it as sizing the question, not answering it."
)

# -- Cohort sizes -------------------------------------------------------------
st.subheader("Who Uses What", divider="violet")

cohort_counts = (
    df["cohort"].value_counts()
    .reindex([A_ONLY, BOTH, F_ONLY])
    .rename_axis("cohort").reset_index(name="users")
)

fig_cohort = px.bar(
    cohort_counts, x="users", y="cohort", orientation="h",
    color="cohort", color_discrete_map=COHORT_COLORS, text="users",
)
fig_cohort.update_traces(
    texttemplate="%{text:,}", textposition="outside",
    hovertemplate="<b>%{y}</b><br>Users: %{x:,}<extra></extra>",
)
fig_cohort.update_layout(
    height=240, showlegend=False,
    margin=dict(l=10, r=40, t=10, b=10),
    plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
    xaxis_title="Users", yaxis_title=None,
)
st.plotly_chart(fig_cohort, width="stretch")

# Per-language split. Worth showing because the cohort mix varies a lot by
# language, and because it makes the shared-language constraint concrete.
lang_cohort = (
    df.assign(Language=df["match_lang"].map(
        lambda k: language_labels(df_all, {k})[0] if pd.notna(k) else "—"))
    .pivot_table(index="Language", columns="cohort", values="cr_user_id",
                 aggfunc="count", fill_value=0)
    .reindex(columns=[A_ONLY, BOTH, F_ONLY], fill_value=0)
)
lang_cohort["Total"] = lang_cohort.sum(axis=1)
st.dataframe(
    lang_cohort.sort_values("Total", ascending=False).reset_index(),
    width="stretch", hide_index=True,
)

# -- The overlapping users ----------------------------------------------------
# At 24 rows the whole cohort fits on screen. Showing it beats any summary of
# it: the reader can see directly how thin the evidence is, and which single
# users are driving the averages.
st.subheader(f"The {n_both} Users in Both Apps", divider="violet")

overlap_cols = {
    "user_short":           "User",
    "a_assessments":        "Assessments",
    "a_score_pct":          "Assessment Score",
    "a_lang":               "Assessment Lang",
    "f_max_level":          "FTM Max Level",
    "f_puzzles":            "FTM Puzzles",
    "f_puzzle_success_pct": "FTM Success",
    "f_time_min":           "FTM Minutes",
    "install_age_days":     "Tenure (days)",
    "order_of_use":         "First Record",
}
st.dataframe(
    both[list(overlap_cols)].rename(columns=overlap_cols)
        .sort_values("FTM Max Level", ascending=False),
    width="stretch", hide_index=True,
    column_config={
        "Assessment Score": st.column_config.NumberColumn(format="%.0f%%"),
        "FTM Success": st.column_config.NumberColumn(format="%.0f%%"),
    },
)

st.caption(
    "Assessment Score is summed score / summed max score. Tenure is days from "
    "the install date encoded in `cr_user_id` to the user's last record. Blank "
    "FTM metrics mean no summary document — unknown, not zero. **First Record** "
    "is which app Firestore wrote first, *not* which app they used first."
)

# -- FTM engagement vs assessment score ---------------------------------------
st.subheader("FTM Engagement vs Assessment Score", divider="violet")

X_METRICS = {
    "FTM Max Level":       "f_max_level",
    "FTM Puzzles Played":  "f_puzzles",
    "FTM Play Time (min)": "f_time_min",
    "FTM Success Rate":    "f_puzzle_success_pct",
    "Tenure (days)":       "install_age_days",
}

# `highest_level_completed` is a lifetime high-water mark, so it rises with how
# long a user has had the game rather than with in-window play. Tenure makes
# that measurable instead of hypothetical: across FTM users in this frame it
# correlates with max level at ~0.57, but with puzzles played at only ~0.14.
METRIC_CAVEATS = {
    "FTM Max Level": (
        "Max level is a lifetime high-water mark, not in-window progress. It "
        "tracks tenure closely (ρ ≈ 0.57 across FTM users here), so a "
        "correlation with assessment score partly measures how long the user "
        "has owned the game. Puzzles, play time and success rate are far less "
        "affected."
    ),
}
x_label = st.sidebar.selectbox(
    "FTM metric", list(X_METRICS), key="comparison_x_metric"
)
x_col = X_METRICS[x_label]

scatter_df = both.dropna(subset=[x_col, "a_score_pct"]).copy()
# Nullable Int64 reaches Plotly as an object column and silently plots nothing.
scatter_df[x_col] = scatter_df[x_col].astype(float)

if scatter_df.empty:
    st.info(f"No users in the overlap have both {x_label} and an assessment score.")
else:
    # Deliberately one color. An earlier version split these by which app
    # Firestore recorded first, which looked like a behavioral split but is an
    # artifact of the two exports starting on different dates.
    fig_sc = px.scatter(
        scatter_df, x=x_col, y="a_score_pct",
        color_discrete_sequence=[FUNNEL_COLORS[3]],
        hover_data={
            "user_short": True, "a_assessments": True,
            "a_lang": True, "f_country": True,
            x_col: ":.1f", "a_score_pct": ":.0%",
        },
        labels={
            x_col: x_label, "a_score_pct": "Assessment Score",
            "user_short": "User", "a_assessments": "Assessments",
            "a_lang": "Language", "f_country": "Country",
        },
    )
    fig_sc.update_traces(marker=dict(size=11, line=dict(width=1, color=PALETTE["dusk"])))
    fig_sc.update_layout(
        height=430, showlegend=False,
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        yaxis_tickformat=".0%", yaxis_range=[-0.03, 1.05],
        xaxis_title=x_label, yaxis_title="Assessment Score",
    )
    st.plotly_chart(fig_sc, width="stretch")

    # A correlation coefficient on ~20 points is not a finding, but its absence
    # invites someone to eyeball the cloud and infer a trend that isn't there.
    # Spearman, because assessment scores pile up hard at 0% and 100%.
    rho = scatter_df[x_col].corr(scatter_df["a_score_pct"], method="spearman")
    st.caption(
        f"{len(scatter_df)} users · Spearman ρ = {rho:.2f}, for orientation "
        f"only — at this size the interval spans nearly the whole range."
    )
    if x_label in METRIC_CAVEATS:
        st.caption(f"⚠️ {METRIC_CAVEATS[x_label]}")

# -- Do FTM players score differently? ----------------------------------------
# The larger comparison: 24 vs ~470 rather than 24 alone. Still not conclusive,
# but it is the strongest cut the Firestore data supports.
st.subheader("Assessment Scores: FTM Players vs Everyone Else", divider="violet")

scored = df[df["a_score_pct"].notna() & df["cohort"].isin([BOTH, A_ONLY])].copy()

if scored.empty:
    st.info("No assessment users have a scored assessment.")
else:
    fig_box = px.box(
        scored, x="cohort", y="a_score_pct", color="cohort",
        color_discrete_map=COHORT_COLORS, points="all",
        category_orders={"cohort": [A_ONLY, BOTH]},
        labels={"cohort": "", "a_score_pct": "Assessment Score"},
    )
    fig_box.update_traces(marker=dict(size=6, opacity=0.55),
                          hovertemplate="Score: %{y:.0%}<extra></extra>")
    fig_box.update_layout(
        height=420, showlegend=False,
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        yaxis_tickformat=".0%", yaxis_title="Assessment Score", xaxis_title=None,
        margin=dict(l=10, r=10, t=10, b=10),
    )
    st.plotly_chart(fig_box, width="stretch")

    summary = (
        scored.groupby("cohort")["a_score_pct"]
        .agg(users="size", median="median", mean="mean")
        .reindex([A_ONLY, BOTH]).dropna(how="all").reset_index()
    )
    summary["median"] = summary["median"].map("{:.0%}".format)
    summary["mean"] = summary["mean"].map("{:.0%}".format)
    st.dataframe(
        summary.rename(columns={"cohort": "Cohort", "users": "Users",
                                "median": "Median Score", "mean": "Mean Score"}),
        width="stretch", hide_index=True,
    )
    st.caption("Only users with a scored assessment appear here.")

# -- Notes --------------------------------------------------------------------
# One expander, not three. Everything a reader needs to avoid over-reading the
# charts, and nothing that merely restates what the charts already show.
with st.expander("Notes & caveats"):
    st.markdown(
        f"""
**Sample.** {n_both} of {n_assessment:,} assessment and {n_ftm:,} FTM users
appear in both apps. Nothing here reaches significance.

**Scope.** From {COMPARISON_START_DATE}, in {shared_label}. Dropping the date
cutoff multiplies the assessment cohort several times over, but that extra
population predates FTM's export and would count as non-players on missing data
alone. Dropping the language filter multiplies the FTM cohort ~20×, mostly with
languages that have no assessment at all.
Removed here: assessment languages with no FTM content
({', '.join(dropped_assessment_langs) or 'none'}); FTM languages with no
assessment ({len(dropped_ftm_langs)}); {unknown_lang_ftm:,} FTM users with no
language recorded anywhere.

**Language matching.** Case and punctuation are folded, so
`BrazilianPortuguese` = `Brazilianportuguese`. Regional variants are *not*
folded — FTM's `IndianEnglish` is separate content from the assessment's
`english`. {n_backfilled:,} FTM users had their language recovered from the
event log, since `metadata.language` only ships from container 2.34.5; those
users average roughly double the max level, so dropping them would have stripped
out the most engaged players.

**Max level is tenure-confounded.** The date filter picks which *users* appear
but cannot rescope FTM's metrics. Puzzle and play-time counters track in-window
activity closely; `highest_level_completed` is a lifetime high-water mark and
correlates with tenure at ρ ≈ 0.57. Use puzzles, play time or success rate for
engagement.

**Tenure is approximate.** Install date is decoded from the timestamp embedded
in `cr_user_id`, which is unpadded and local-time, so ~3% of ids cannot be read
and about a quarter need a tie-break between valid readings. The distribution is
sound; a single user's tenure may be off.

**Direction is unknowable.** Firestore's `timestamp` is write time, and the two
exports began on different dates, so "First Record" reflects export start dates
rather than user behavior. No causal claim can be read from this page.

**Score is coarse.** `max_score` takes few distinct values, so `a_score_pct`
piles up at 0% and 100%. Prefer medians.

**What would unlock this.** A larger shared population — more FTM history
alongside the assessment window, or the assessment launched from inside FTM so
both records are created together.
"""
    )

st.caption(
    f"{len(df):,} users in scope ({len(df_all):,} before the shared-language "
    f"filter) · {n_assessment:,} assessment · {n_ftm:,} FTM · {n_both} both · "
    f"from {COMPARISON_START_DATE}, in {shared_label} — sources: "
    "ftm-b9d99.firestore_export.user_sessions_data_raw_latest (app_id='assessment') "
    "and summary_data_raw_latest (app_id='feed-the-monster')"
)
