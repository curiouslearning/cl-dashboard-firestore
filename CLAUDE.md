# CLAUDE.md — CL Assessment Dashboard

# Project Overview

Streamlit analytics dashboard for the ** Curious Learning Assessment app**.
Data originates from **Firestore**, is exported to ** BigQuery**, and is queried
directly into Streamlit session state at startup. This dashboard's datasets are
small — hundreds to tens of thousands of rows, not the millions the other
Curious Learning dashboards handle — so every loader queries BigQuery live.
There is no parquet cache and no GCS dependency.

---

# Stack

- **Python ** 3.12
- **Streamlit ** 1.48
- **BigQuery ** as the data backend (queried directly, no cache layer)
- **Pandas ** for all data manipulation
- **Plotly ** for charts(when added)
- **st_pages ** for navigation(`get_nav_from_toml`)

---

# Project Structure

```
main.py                        # Entry point — set_page_config, navigation, footer
settings.py                    # GCP credentials, initialize(), get_logger()
data.py                        # Data loading, flattening, session state init
colors.py                      # Global color palette (Lavender Dusk theme) + FUNNEL_COLORS
ui.py                          # CSS injection + tile / section-header / funnel renderers
app_pages/
assessments.py               # Assessment summary — tiles + assessment charts
ftm.py                       # Feed the Monster — tiles + engagement funnels + scatter
.streamlit/
config.toml                  # Theme configuration
pages.toml                   # Navigation structure
```

---

# Color Scheme — Lavender Dusk

```toml
primaryColor = "#7C5CBF"   # violet — buttons, radio, active sidebar
backgroundColor = "#F2EFFC"   # soft lilac
secondaryBackgroundColor = "#E4DEFA"  # mid lavender — sidebar, tiles
textColor = "#2A1A5E"   # deep violet
```

Palette keys in `colors.py`: `lavender`, `lilac`, `violet`, `dusk`, `plum`, `ink`

`PALETTE` is deliberately pale — fine for tiles and chart marks that sit on the
background. Funnel stages carry their labels *inside* the bars, so they use the
darker `FUNNEL_COLORS` ramp instead (dark → focal → dark, mirroring the olive
ramp in cl-dashboard-internal's `create_engagement_figure`).

Use `divider = "violet"` in `st.subheader()` to match the theme.

---

# Data Source

# Firestore → BigQuery tables
```
ftm-b9d99.firestore_export.user_sessions_data_raw_latest   # event log
ftm-b9d99.firestore_export.summary_data_raw_latest         # per-user summaries
```

**Every collection is shared across app_ids.** `user_sessions_data` holds both
assessment `activity_completed` rows and Feed the Monster `puzzle_completed` /
`level_completed` rows; `summary_data` holds both apps' summaries. Filtering on
`app_id` is not a nicety — it is what keeps one app's rows out of another app's
DataFrame, and it belongs in SQL.

All loaders go through one helper, which applies that filter:

```python
_load_firestore_rows(table, app_id)   # SELECT ... WHERE JSON_VALUE(data,'$.app_id') = app_id
```

It renames `timestamp` → `firestore_timestamp`, freeing `timestamp` to mean the
event's own clock inside the JSON payload.

**Why no parquet cache.** The assessment loader used to read a GCS parquet
export of `user_sessions_data_raw_latest`. That export was `SELECT *` with no
app_id filter, so once FTM began writing to the same collection the file became
~97% FTM rows (28,788 of 29,710) and the assessment page counted every one of
them as an assessment — reporting 29,710 assessments across 1,616 users instead
of the real 934 across 497. Direct queries removed that whole class of problem.
Do not reintroduce a cache layer without an app_id filter in the export itself.

---

# Data Model

# Raw Firestore JSON structure (stored in `data` column)
```json
{
    "cr_user_id": "...",
    "collection": "user_sessions_data",
    "app_id":     "assessment",
    "timestamp":  "2026-04-01T11:56:44.622Z",
    "data": {
        "event_type": "activity_completed",
        "type":       "letter-sounds",
        "lang":       "ukrainian",
        "score":      0,
        "max_score":  800,
        "time_spent": 51517
    }
}
```

# Flattened columns in `df_assessments`

Each row = one completed assessment. `activity_type` tells you which one
(`letter-sounds` or `sight-words`). The dashboard uses "assessment" everywhere
in user-facing text and internal keys; "session" survives only in the upstream
resource name (`user_sessions_data_raw_latest`).

| Column | Source | Notes |
|--- | --- | ---|
| `document_id` | raw | Firestore document ID |
| `firestore_timestamp` | raw | renamed from `timestamp` |
| `event_id` | raw | |
| `operation` | raw | `CREATE` or `UPDATE` |
| `cr_user_id` | data(top-level) | |
| `app_id` | data(top-level) | always `"assessment"` currently |
| `collection` | data(top-level) | always `"user_sessions_data"` |
| `event_timestamp` | data(top-level) | parsed to UTC datetime |
| `event_type` | data.data | always `"activity_completed"` currently |
| `activity_type` | data.data | e.g. `letter-sounds`, `sight-words` |
| `lang` | data.data | e.g. `ukrainian`, `bangla`, `french` |
| `score` | data.data | Int64, nullable |
| `max_score` | data.data | Int64, nullable |
| `time_spent_ms` | data.data | Int64, milliseconds |
| `time_spent_sec` | derived | `time_spent_ms / 1000` |
| `score_pct` | derived | `score / max_score`, null if max_score = 0 |

# Key facts about the data (as of Aug 2026)
- 934 rows, 497 unique `cr_user_id` values — some users have multiple rows
- Multiple rows per user are retained(not deduplicated)
- 6 languages, 2 activity types(`letter-sounds`, `sight-words`)
- Assessment rows carry **no `metadata.environment`** — there is no way to
  separate test from production traffic on this dataset
- `event_timestamp` (from the JSON's inner `timestamp`) is populated on only
  **551 of 934** rows. Charts that `dropna` on it silently describe ~60% of the
  data — the dumbbell chart on the assessment page sees 71 repeat-take pairs
  where the full data supports 134. `firestore_timestamp` is on every row.

---

# Data Loading Pattern

**Each app's data loads independently.** A page loads only the dataset it needs,
via that dataset's own `ensure_*_data_initialized()` guard — pages are decoupled,
so navigating to one app's page never loads another's, and a load failure in one
dataset never blocks another page. Call the relevant guard at the top of the page
before accessing session state.

```python
# Assessment page
initialize()
ensure_assessment_data_initialized()
df = st.session_state["df_assessments"]

# Feed the Monster page
initialize()
ensure_ftm_data_initialized()
df = st.session_state["df_ftm"]        # per-user cumulative summaries

# Assessment × FTM comparison page
initialize()
ensure_comparison_data_initialized()
df = st.session_state["df_comparison"]  # one row per user, with a cohort label

# FTM raw event log — loader exists but no page loads it yet
ensure_ftm_events_initialized()
events = st.session_state["df_ftm_events"]
```

Every guard delegates to the shared `_guard_init(init_fn, flag_key, label)`
helper in `data.py`, which runs the loader once per session and wraps failures
in `st.error` + `st.stop()`. Every loader is `@st.cache_data(ttl="1d")` and
fetches from BigQuery through `_load_firestore_rows`, except the comparison
loader, which runs its own `COMPARISON_SQL` because it joins two tables.

# Session state keys

| Key | Content |
|--- | ---|
| `df_assessments` | Flattened assessments DataFrame (one row = one completed assessment) |
| `assessment_data_initialized` | Boolean guard for the assessment loader |
| `df_ftm` | Flattened Feed the Monster summary DataFrame (may be empty) |
| `ftm_data_initialized` | Boolean guard for the FTM loader |
| `df_ftm_events` | Flattened FTM event log (`puzzle_completed` / `level_completed`) |
| `ftm_events_initialized` | Boolean guard for the FTM event-log loader |
| `df_comparison` | One row per user across both apps, with a `cohort` label |
| `comparison_data_initialized` | Boolean guard for the comparison loader |

# Feed the Monster page scope

The FTM page filters to `firestore_timestamp >= 2026-07-29` (earlier rows
predate the full summary field set) and `environment == "production"` (drops
test and environment-less rows). Apply the identical filter to any dataset added
to this page, so every number describes the same population.

Page sections: summary tiles → world map → engagement funnels →
volume-vs-success scatter → field completeness.

The map is a `px.choropleth` (`locationmode="country names"`, `MAP_SCALE` ramp)
shaded by unique users, modeled on `stats_by_country_map` in cl-data-dashboard.
Hovering a country shows that country's own summary tiles: `summary_stats()` and
`tile_specs_for()` compute the tile row and every per-country hover card, so the
two cannot drift — a tile added to `tile_specs_for` appears on the map for free,
scoped to that country's rows. The Readers Acquired tile thresholds per-user
`highest_level_completed` ≥ 25, the same rule as the `ftm_level_25` funnel stage,
so the page-level tile always equals that stage over the `begin_play` baseline. Rows with a null or `"unknown"` country cannot be placed and
are reported in the caption. `COUNTRY_ALIASES` remaps spellings Natural Earth
does not use (Plotly drops unmatched names silently rather than erroring).

Sidebar filters (Language, Country) narrow the scoped frame **before** any
figure is computed, so every section describes the same filtered population.
Each defaults to `"All"`, and its options come from the scoped rows — values
that appear only in test or pre-cutoff data are never offered. Add new filters
to the same `active_filters` block so they apply everywhere at once.

# Engagement funnels

Rendered under the heading "Engagement Funnels"; the underlying stages are still
the ad-optimization milestones, named for the Firebase Analytics events.

The page reconstructs the Firebase Analytics conversion events **in FTM terms**,
since Firebase is not a data source and the container-level `user_profiles`
collection is not exported to BigQuery. `begin_play` and the four `play_*`
thresholds are genuinely cross-app events, so the FTM-only versions are lower
bounds.

Seven of the nine are shown, as **two side-by-side funnels** — level progress
and play time — because the milestones are independent thresholds on two tracks,
not nested stages. Interleaved they do not taper (`ftm_level_25` sits below
`play_10_min`); split by track, each is monotonic in spec order and Plotly's
"% of previous" reads as a real step-down. `begin_play` heads both as the shared
baseline and is 100% by construction — every user in the frame has an FTM
summary record.

Milestones are per install, so roll up per `cr_user_id` (`max` level, `sum`
seconds) before thresholding — some users have more than one summary doc and
must not count twice.

`play_sessions_3` and `habit_4_days_week` are deliberately omitted: the event log
carries no app-launch event (only `puzzle_completed` and `level_completed`), so
sessions can only be reconstructed from a 30-minute inactivity gap, and a rolling
7-day habit window needs more history than the page's start date allows. Both
become straightforward once `user_profiles` is exported. `data.py` keeps the
event-log loader ready for that work.

---

# Assessment × FTM comparison page

`app_pages/comparison.py` — how the two user bases relate, and whether FTM
engagement travels with assessment success.

`COMPARISON_SQL` in `data.py` does the join **in BigQuery**, unlike the other
loaders, because it spans two tables: assessment rows from
`user_sessions_data_raw_latest` and FTM summaries from `summary_data_raw_latest`,
`FULL OUTER JOIN`ed on `cr_user_id` into cohorts `Both` / `Assessment only` /
`FTM only`. Cohort membership and metrics come from different places on the FTM
side — a user counts as an FTM user if they appear in *either* FTM table, but
gameplay numbers exist only in `summary_data`, so a few users are FTM members
whose metrics are unknown rather than zero.

Two scope filters make the cohorts comparable. Both discard most of the data on
purpose, and removing either one makes the page tell a flattering lie:

- **Date — both sides start at `COMPARISON_START_DATE` (2026-08-01)**, applied
  in SQL, matching the FTM page's cutoff. FTM wrote nothing to Firestore before
  then, so an earlier assessment user would be classed "Assessment only" because
  of when tracking started, not because they didn't play. The filter is on
  `timestamp` (write time) — the only clock populated on every row of both
  tables.
- **Language — only languages present in both apps**, computed from the
  date-scoped data by `shared_languages()`, never hardcoded (the shared set
  changes as data lands). Every FTM language is playable but assessments cover
  far fewer, so an FTM user with no assessment in their language never declined
  to assess. `normalize_language()` folds case and punctuation
  (`BrazilianPortuguese` ≡ `Brazilianportuguese`); `LANGUAGE_ALIASES` handles
  word-order differences (`EnglishWestAfrican` ≡ `west-african-english`).
  **Regional variants are deliberately not folded** — FTM's `IndianEnglish` and
  `AustralianEnglish` are separate content from the assessment's `english`, and
  merging them would invent an overlap that doesn't exist.

**FTM language is backfilled from the event log, and must stay that way.**
`metadata.language` only ships from container version **2.34.5** — rows from
2.34.4 have a summary document with no language on it (nothing to do with
`created_at`, which is present on those rows). Around 15% of FTM users are
affected, and they are *not* a random slice: they average roughly double the
max level of users who carry the field, so dropping them would strip the most
engaged players out of the FTM cohort. `COMPARISON_SQL` coalesces
`metadata.language` with `data.lang` from `user_sessions_data`, which is already
lowercase and covers all but a handful. This also changes which languages
qualify as shared — Bangla and West African English only appear on both sides
once the backfill runs. `f_language_backfilled` flags the recovered rows.

Two further constraints:

- **The overlap is ~12 users** after both filters (from ~24 unfiltered).
  Nothing here reaches significance; the page is sized to test whether the
  question is worth pursuing. Keep the sample-size warning prominent.
- **No `environment` filter.** Assessment rows carry no `metadata.environment`
  at all, so the FTM page's `== "production"` filter would drop every assessment
  user. Both apps are shown unfiltered, test rows included. Do not "fix" this by
  copying the FTM filter over.
- **Causal direction is unrecoverable.** Firestore `timestamp` is write time,
  and the two exports began on different dates (assessment ~Mar 2026, FTM
  ~Jun 2026), so ordering reflects export start dates, not user behavior.
  `created_at` covers only ~40% of assessment rows and starts in June, so it
  does not rescue this. The `order_of_use` column is surfaced as "First Record"
  and must not be presented as which app the user played first.

`a_score_pct` piles up at 0% and 100% because `max_score` takes very few
distinct values — prefer medians, and Spearman over Pearson.

**`cr_user_id` encodes the account creation time**, so tenure is derivable:
26 random characters, then an unpadded local-time
`${{year}}${{month}}${{day}}${{hours}}${{minutes}}${{seconds}}` (a few ids use epoch
millis instead). Unpadded means digit widths vary and a string can have several
valid readings, so `parse_install_date()` accepts a candidate only if
re-encoding reproduces the id, and rejects any that postdates the user's first
record. **The ceiling needs a ±14h timezone slack** — the id's clock is local
while records are UTC, and without the slack every user east of UTC fails to
parse (coverage drops from 97% to 66%). Where readings remain ambiguous (~25%)
the latest is taken. `install_age_days` runs install → last record, clamped at 0.

**`highest_level_completed` is install-age confounded; the counters are not.**
The date filter scopes which *users* appear but cannot rescope FTM's metrics.
Measured over the window, `puzzles_completed` tracks in-window `puzzle_completed`
events closely (avg 22.4 summary vs 23.0 events), but `highest_level_completed`
sits well above the in-window max and the gap grows on older container versions
(2.34.5: 7.5 vs 5.2 in-window; 2.34.4: 14.7 vs 11.6; no-metadata: 19.3 vs 11.7).
It is a lifetime high-water mark predating FTM's Firestore export, which only
begins June 2026 — the earlier play backing those levels has no records at all.
With `install_age_days` this is measured rather than inferred: across FTM users
in the frame, tenure correlates with max level at ρ ≈ 0.57 but with puzzles at
only ρ ≈ 0.14, and median max level climbs 1 → 4 → 7 → 12 across tenure buckets
while median puzzles does not. Use puzzles, play time or success rate for
engagement comparisons. `METRIC_CAVEATS` on the page surfaces this whenever max
level is the selected metric.

Page prose is deliberately terse — one scope caption, one overlap warning, one
"Notes & caveats" expander. Detail belongs in the expander or in this file, not
stacked above the charts.

---

# GCP Credentials

Credentials are fetched from **Secret Manager ** at startup:
```
projects/405806232197/secrets/service_account_json/versions/latest
```

The service account needs:
- BigQuery read on `ftm-b9d99`
(GCS read on `user_data_parquet_cache` is no longer needed — the parquet cache
was removed in favor of direct queries.)

`get_gcp_credentials()` is `@st.cache_resource(ttl="1d")` — returns
`(gcp_credentials, bq_client)`.

---

# Adding a New Page

1. Create `app_pages/your_page.py`
2. Add an entry to `.streamlit/pages.toml`
3. Call `initialize()` and the relevant `ensure_*_data_initialized()` at the top
   (or add a new per-app loader + guard in `data.py` for a new dataset)
4. Access data via the matching `st.session_state["df_*"]` key

```toml
[[pages]]
path = "app_pages/your_page.py"
name = "Your Page"
icon = "📊"
```

---

# Key Conventions

- **Full function bodies ** when providing code — no partial snippets
- **`@st.cache_data(ttl="1d")`** on data loading functions
- **`@st.cache_resource(ttl="1d")`** on GCP credential functions
- Column rename guard in loader: `if "timestamp" in df.columns and "firestore_timestamp" not in df.columns`
- ` % -d` for day formatting(no leading zero) — Mac/Linux only
use `%  # d` on Windows
- Use `PALETTE` dict from `colors.py` for all chart and tile colors
  (`FUNNEL_COLORS` for funnel stages)
- Render summary tiles with `ui.tile_row(specs)` — one responsive CSS grid that
  wraps on narrow windows. Do **not** put tiles in `st.columns`: fixed columns
  squeeze until the text breaks mid-word and spills out of the tile.
- Render funnels with `ui.funnel_figure(labels, values)`. It does not sort —
  pass stages already in descending order, or the funnel will not taper.
- Avoid charts with one row (or one user) per category: the FTM page had two,
  and at ~450 users they rendered ~12,000px tall. Aggregate or bin instead.
