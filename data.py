import streamlit as st
import pandas as pd
import itertools
import json
import re
import traceback
from settings import get_gcp_credentials


# ══════════════════════════════════════════════════════════════════════════════
# Shared helpers
# ══════════════════════════════════════════════════════════════════════════════

def _load_firestore_rows(table: str, app_id: str) -> pd.DataFrame:
    """Fetch one app's rows from a Firestore-export table.

    Every collection in `firestore_export` is shared across app_ids, so the
    app_id filter belongs in SQL — it is what keeps one app's rows out of
    another app's DataFrame.

    `timestamp` is renamed to `firestore_timestamp` so the flatteners can use
    `timestamp` for the event's own clock inside the JSON payload.
    """
    _, bq_client = get_gcp_credentials()
    query = f"""
        SELECT document_id, timestamp, event_id, operation, data
        FROM `{table}`
        WHERE JSON_VALUE(data, '$.app_id') = '{app_id}'
    """
    df = bq_client.query(query).result().to_dataframe()
    if "timestamp" in df.columns and "firestore_timestamp" not in df.columns:
        df = df.rename(columns={"timestamp": "firestore_timestamp"})
    return df


def _parse_json(val) -> dict:
    if pd.isna(val) or val == "":
        return {}
    try:
        return json.loads(val)
    except Exception:
        return {}


def _guard_init(init_fn, flag_key: str, label: str):
    """Run `init_fn` once per session, wrapping failures in st.error/st.stop.

    Each dataset gets its own `flag_key` so pages load only what they need and
    a failure in one dataset never blocks another page.
    """
    if st.session_state.get(flag_key):
        return
    try:
        init_fn()
    except Exception as e:
        st.error(f"❌ Failed to load {label}: {e}")
        st.text(traceback.format_exc())
        st.stop()


# ══════════════════════════════════════════════════════════════════════════════
# Assessment app  (direct BigQuery → df_assessments)
# ══════════════════════════════════════════════════════════════════════════════

ASSESSMENT_TABLE = "ftm-b9d99.firestore_export.user_sessions_data_raw_latest"


@st.cache_data(ttl="1d", show_spinner=False)
def load_assessments_from_bq() -> pd.DataFrame:
    """Load assessment rows straight from BigQuery.

    Previously this read a GCS parquet export of the same table. That export was
    `SELECT *` with no app_id filter, so once Feed the Monster began writing to
    the shared `user_sessions_data` collection the file was ~97% FTM rows, and
    the assessment page counted every one of them as an assessment. Querying
    with the filter in SQL removes the whole class of problem, and at ~1k rows
    it is cheaper than fetching a 36 MB parquet to discard most of it.
    """
    return _load_firestore_rows(ASSESSMENT_TABLE, "assessment")


def flatten_assessment_df(df_raw: pd.DataFrame) -> pd.DataFrame:
    """
    Flatten the JSON 'data' field into individual columns.

    Assumes the frame is already filtered to app_id = 'assessment' — the loader
    does that in SQL. `user_sessions_data` is shared with Feed the Monster, and
    FTM rows survive this flattener silently (they carry `type`, `lang` and no
    `score`), so an unfiltered frame produces plausible-looking nonsense rather
    than an error.

    Source JSON structure:
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
                "time_spent": 51517          <- milliseconds
            }
        }

    Output columns:
        document_id, firestore_timestamp, event_id, operation,
        cr_user_id, app_id, collection, event_timestamp,
        event_type, activity_type, lang,
        score, max_score, time_spent_ms, time_spent_sec, score_pct
    """
    parsed = df_raw["data"].apply(_parse_json)
    payload = parsed.apply(lambda d: d.get("data") or {})

    df = df_raw[["document_id", "firestore_timestamp",
                 "event_id", "operation"]].copy()

    # ── Top-level fields ──────────────────────────────────────────────────────
    df["cr_user_id"] = parsed.apply(lambda d: d.get("cr_user_id"))
    df["app_id"] = parsed.apply(lambda d: d.get("app_id"))
    df["collection"] = parsed.apply(lambda d: d.get("collection"))
    df["event_timestamp"] = pd.to_datetime(
        parsed.apply(lambda d: d.get("timestamp")), utc=True, errors="coerce"
    )

    # ── Nested payload ────────────────────────────────────────────────────────
    df["event_type"] = payload.apply(lambda d: d.get("event_type"))
    df["activity_type"] = payload.apply(lambda d: d.get("type"))
    df["lang"] = payload.apply(lambda d: d.get("lang"))
    df["score"] = pd.to_numeric(
        payload.apply(lambda d: d.get("score")),      errors="coerce"
    ).astype("Int64")
    df["max_score"] = pd.to_numeric(
        payload.apply(lambda d: d.get("max_score")),  errors="coerce"
    ).astype("Int64")
    df["time_spent_ms"] = pd.to_numeric(
        payload.apply(lambda d: d.get("time_spent")), errors="coerce"
    ).astype("Int64")

    # ── Derived columns ───────────────────────────────────────────────────────
    df["time_spent_sec"] = (df["time_spent_ms"] / 1000).round(1)
    df["score_pct"] = (
        df["score"] / df["max_score"]
    ).where(df["max_score"] > 0).round(4)

    return df


def ensure_assessment_data_initialized():
    """Call at the top of the assessment page. Loads df_assessments once."""
    _guard_init(_init_assessment_data, "assessment_data_initialized",
                "assessment data")


def _init_assessment_data():
    with st.spinner("Loading assessment data...", show_time=True):
        df_raw = load_assessments_from_bq()
        if df_raw.empty:
            raise ValueError("Assessments table returned no rows.")

        st.session_state["df_assessments"] = flatten_assessment_df(df_raw)
        st.session_state["assessment_data_initialized"] = True


# ══════════════════════════════════════════════════════════════════════════════
# Feed the Monster app  (direct BigQuery → df_ftm)
# ══════════════════════════════════════════════════════════════════════════════

FTM_SUMMARY_TABLE = "ftm-b9d99.firestore_export.summary_data_raw_latest"


@st.cache_data(ttl="1d", show_spinner=False)
def load_ftm_from_bq() -> pd.DataFrame:
    """
    Load Feed the Monster summary rows straight from BigQuery.

    The `summary_data` collection is shared across app_ids (assessment,
    feed-the-monster, …), so the app_id filter is what keeps assessment
    summaries out of this frame.
    """
    return _load_firestore_rows(FTM_SUMMARY_TABLE, "feed-the-monster")


def flatten_ftm_df(df_raw: pd.DataFrame) -> pd.DataFrame:
    """
    Flatten the Feed the Monster summary_data JSON into columns.

    Per the data spec, each row is one user's cumulative summary. Fields are
    sparse in practice — many rows are missing metadata / attribution blocks,
    created_at, level counts, and time_spent_total_second — so every lookup
    tolerates absent keys and yields <NA>/NaT rather than raising.

    Source JSON (idealized; real rows are a subset):
        {
            "app_id": "feed-the-monster", "collection": "summary_data",
            "cr_user_id": "...", "schema_version": "v1",
            "created_at": "...", "updated_at": "...", "synced_at": "...",
            "data": {
                "highest_level_completed": 2, "levels_completed": 7,
                "puzzle_failure": 9, "puzzle_success": 30,
                "puzzles_completed": 39, "time_spent_total_second": 521.336,
                "container_version": "2.34.10"
            },
            "metadata": {
                "app_version": "...", "container_app_version": "...",
                "environment": "test", "language": "...", "country": "..."
            },
            "attribution": {
                "campaign_id": "...", "source": "...",
                "hostname": "...", "apk_package_name": "..."
            }
        }
    """
    parsed = df_raw["data"].apply(_parse_json)
    payload = parsed.apply(lambda d: d.get("data") or {})
    meta = parsed.apply(lambda d: d.get("metadata") or {})
    attr = parsed.apply(lambda d: d.get("attribution") or {})

    df = df_raw[["document_id", "firestore_timestamp",
                 "event_id", "operation"]].copy()

    # ── Top-level fields ──────────────────────────────────────────────────────
    df["cr_user_id"] = parsed.apply(lambda d: d.get("cr_user_id"))
    df["app_id"] = parsed.apply(lambda d: d.get("app_id"))
    df["collection"] = parsed.apply(lambda d: d.get("collection"))
    df["schema_version"] = parsed.apply(lambda d: d.get("schema_version"))

    for col in ("created_at", "updated_at", "synced_at"):
        df[col] = pd.to_datetime(
            parsed.apply(lambda d, k=col: d.get(k)), utc=True, errors="coerce"
        )
    # Single event_timestamp for time-based charts: updated_at, else inner
    # data.timestamp, else created_at.
    inner_ts = pd.to_datetime(
        parsed.apply(lambda d: d.get("timestamp")), utc=True, errors="coerce"
    )
    df["event_timestamp"] = (
        df["updated_at"].fillna(inner_ts).fillna(df["created_at"])
    )

    # ── data.* gameplay counters ──────────────────────────────────────────────
    int_fields = [
        "highest_level_completed", "levels_completed",
        "puzzle_failure", "puzzle_success", "puzzles_completed",
    ]
    for f in int_fields:
        df[f] = pd.to_numeric(
            payload.apply(lambda d, k=f: d.get(k)), errors="coerce"
        ).astype("Int64")

    df["time_spent_total_sec"] = pd.to_numeric(
        payload.apply(lambda d: d.get("time_spent_total_second")),
        errors="coerce",
    )
    df["container_version"] = payload.apply(lambda d: d.get("container_version"))

    # ── metadata.* ────────────────────────────────────────────────────────────
    df["app_version"] = meta.apply(lambda d: d.get("app_version"))
    df["container_app_version"] = meta.apply(lambda d: d.get("container_app_version"))
    df["environment"] = meta.apply(lambda d: d.get("environment"))
    df["language"] = meta.apply(lambda d: d.get("language"))
    df["country"] = meta.apply(lambda d: d.get("country"))

    # ── attribution.* ─────────────────────────────────────────────────────────
    df["campaign_id"] = attr.apply(lambda d: d.get("campaign_id"))
    df["source"] = attr.apply(lambda d: d.get("source"))
    df["hostname"] = attr.apply(lambda d: d.get("hostname"))
    df["apk_package_name"] = attr.apply(lambda d: d.get("apk_package_name"))

    # ── Derived ───────────────────────────────────────────────────────────────
    df["time_spent_total_min"] = (df["time_spent_total_sec"] / 60).round(1)
    df["puzzle_success_pct"] = (
        df["puzzle_success"] / df["puzzles_completed"]
    ).where(df["puzzles_completed"] > 0).round(4)

    return df


def ensure_ftm_data_initialized():
    """Call at the top of the Feed the Monster page. Loads df_ftm once.

    An empty result is valid here (feature is pre-launch in production), so
    this stores an empty DataFrame rather than raising.
    """
    _guard_init(_init_ftm_data, "ftm_data_initialized", "Feed the Monster data")


def _init_ftm_data():
    with st.spinner("Loading Feed the Monster data...", show_time=True):
        df_raw = load_ftm_from_bq()
        st.session_state["df_ftm"] = (
            flatten_ftm_df(df_raw) if not df_raw.empty else pd.DataFrame()
        )
        st.session_state["ftm_data_initialized"] = True


# ══════════════════════════════════════════════════════════════════════════════
# Feed the Monster event log  (direct BigQuery → df_ftm_events)
# ══════════════════════════════════════════════════════════════════════════════

FTM_EVENTS_TABLE = "ftm-b9d99.firestore_export.user_sessions_data_raw_latest"


@st.cache_data(ttl="1d", show_spinner=False)
def load_ftm_events_from_bq() -> pd.DataFrame:
    """
    Load the raw Feed the Monster event log straight from BigQuery.

    `user_sessions_data` is the append-only event log shared with the assessment
    app — the same table `load_assessments_from_bq` reads, which is exactly why
    the app_id filter matters. It carries two event types (`puzzle_completed`
    and `level_completed`) with no app-launch event, so play sessions have to be
    reconstructed from event timestamps.
    """
    return _load_firestore_rows(FTM_EVENTS_TABLE, "feed-the-monster")


def flatten_ftm_events_df(df_raw: pd.DataFrame) -> pd.DataFrame:
    """
    Flatten the Feed the Monster event log JSON into columns.

    Source JSON:
        {
            "app_id": "feed-the-monster", "collection": "user_sessions_data",
            "cr_user_id": "...", "schema_version": "v1",
            "created_at": "...", "synced_at": "...",
            "data": {
                "event_type": "puzzle_completed",   # or "level_completed"
                "level": 0, "puzzle": 2,
                "type": "LetterOnly", "lang": "arabic", "is_success": true
            },
            "metadata": {"environment": "production", "language": "Arabic",
                         "country": "Egypt", "app_version": "v1.6.1"},
            "attribution": {...}
        }

    `created_at` is populated on every row and is the event's own clock, so it
    is what sessionization and active-day counts key off of — not the Firestore
    write timestamp, which reflects sync time.
    """
    parsed = df_raw["data"].apply(_parse_json)
    payload = parsed.apply(lambda d: d.get("data") or {})
    meta = parsed.apply(lambda d: d.get("metadata") or {})

    df = df_raw[["document_id", "firestore_timestamp",
                 "event_id", "operation"]].copy()

    # ── Top-level fields ──────────────────────────────────────────────────────
    df["cr_user_id"] = parsed.apply(lambda d: d.get("cr_user_id"))
    df["app_id"] = parsed.apply(lambda d: d.get("app_id"))
    for col in ("created_at", "synced_at"):
        df[col] = pd.to_datetime(
            parsed.apply(lambda d, k=col: d.get(k)), utc=True, errors="coerce"
        )
    # Fall back to the Firestore write time on the rare row with no created_at.
    df["event_timestamp"] = df["created_at"].fillna(df["firestore_timestamp"])

    # ── data.* event payload ──────────────────────────────────────────────────
    df["event_type"] = payload.apply(lambda d: d.get("event_type"))
    df["level"] = pd.to_numeric(
        payload.apply(lambda d: d.get("level")), errors="coerce"
    ).astype("Int64")
    df["puzzle"] = pd.to_numeric(
        payload.apply(lambda d: d.get("puzzle")), errors="coerce"
    ).astype("Int64")
    df["puzzle_type"] = payload.apply(lambda d: d.get("type"))
    df["lang"] = payload.apply(lambda d: d.get("lang"))
    df["is_success"] = payload.apply(lambda d: d.get("is_success"))

    # ── metadata.* ────────────────────────────────────────────────────────────
    df["environment"] = meta.apply(lambda d: d.get("environment"))
    df["language"] = meta.apply(lambda d: d.get("language"))
    df["country"] = meta.apply(lambda d: d.get("country"))
    df["app_version"] = meta.apply(lambda d: d.get("app_version"))

    return df


def ensure_ftm_events_initialized():
    """Call before using df_ftm_events. Loads the FTM event log once."""
    _guard_init(_init_ftm_events, "ftm_events_initialized",
                "Feed the Monster event log")


def _init_ftm_events():
    with st.spinner("Loading Feed the Monster event log...", show_time=True):
        df_raw = load_ftm_events_from_bq()
        st.session_state["df_ftm_events"] = (
            flatten_ftm_events_df(df_raw) if not df_raw.empty else pd.DataFrame()
        )
        st.session_state["ftm_events_initialized"] = True


# ══════════════════════════════════════════════════════════════════════════════
# Assessment × Feed the Monster comparison  (direct BigQuery → df_comparison)
# ══════════════════════════════════════════════════════════════════════════════

# One row per user, assessment metrics beside FTM metrics, with a `cohort` label.
#
# Aggregated in SQL rather than pandas because it spans two tables and the join
# is the whole point — pulling both raw and joining locally would move ~11k rows
# to do what BigQuery does in one pass over a few hundred MB.
#
# Cohort membership and metrics come from different places on the FTM side:
# a user counts as an FTM user if they appear in *either* FTM table, but the
# gameplay numbers only exist in summary_data. A handful of users have event-log
# activity with no summary doc; they are FTM users whose metrics are unknown,
# which is not the same as zero.
#
# ── Why the date cutoff ──────────────────────────────────────────────────────
# Both sides are cut at COMPARISON_START_DATE, the same cutoff the FTM page
# uses. Before it, FTM was not writing to Firestore at all, so an assessment
# user from June would be classified "Assessment only" purely because their FTM
# play was never recorded. That is an artifact of when tracking started, not a
# fact about the user, and it would inflate the assessment-only cohort with
# people who may well have been playing FTM the whole time.
#
# The filter is on `timestamp` (the Firestore write time) rather than the JSON's
# own clock, because it is the one field populated on every row of both tables —
# assessment's inner `timestamp` is missing on ~40% of rows.
COMPARISON_START_DATE = "2026-08-01"

COMPARISON_SQL = f"""
WITH
assessment AS (
  SELECT
    JSON_VALUE(data,'$.cr_user_id')                                      AS cr_user_id,
    COUNT(*)                                                             AS a_assessments,
    SUM(SAFE_CAST(JSON_VALUE(data,'$.data.score')      AS FLOAT64))      AS a_score_sum,
    SUM(SAFE_CAST(JSON_VALUE(data,'$.data.max_score')  AS FLOAT64))      AS a_max_score_sum,
    SUM(SAFE_CAST(JSON_VALUE(data,'$.data.time_spent') AS FLOAT64))/1000 AS a_time_sec,
    COUNT(DISTINCT JSON_VALUE(data,'$.data.type'))                       AS a_activity_types,
    -- Most-taken language, not an arbitrary one: 19 users assess in more than
    -- one, and the language decides whether they survive the shared-language
    -- filter, so the pick has to be deterministic.
    APPROX_TOP_COUNT(JSON_VALUE(data,'$.data.lang'), 1)[OFFSET(0)].value AS a_lang,
    MIN(timestamp)                                                       AS a_first_seen,
    MAX(timestamp)                                                       AS a_last_seen
  FROM `ftm-b9d99.firestore_export.user_sessions_data_raw_latest`
  WHERE JSON_VALUE(data,'$.app_id') = 'assessment'
    AND JSON_VALUE(data,'$.cr_user_id') IS NOT NULL
    AND timestamp >= '{COMPARISON_START_DATE}'
  GROUP BY cr_user_id
),
ftm_summary AS (
  SELECT
    JSON_VALUE(data,'$.cr_user_id')                                            AS cr_user_id,
    MAX(SAFE_CAST(JSON_VALUE(data,'$.data.highest_level_completed') AS INT64))  AS f_max_level,
    SUM(SAFE_CAST(JSON_VALUE(data,'$.data.puzzles_completed')       AS INT64))  AS f_puzzles,
    SUM(SAFE_CAST(JSON_VALUE(data,'$.data.puzzle_success')          AS INT64))  AS f_puzzle_success,
    SUM(SAFE_CAST(JSON_VALUE(data,'$.data.time_spent_total_second') AS FLOAT64)) AS f_time_sec,
    APPROX_TOP_COUNT(JSON_VALUE(data,'$.metadata.language'), 1)[OFFSET(0)].value AS f_language,
    ANY_VALUE(JSON_VALUE(data,'$.metadata.country'))                           AS f_country,
    ANY_VALUE(JSON_VALUE(data,'$.metadata.environment'))                       AS f_environment,
    MIN(timestamp)                                                             AS f_first_seen,
    MAX(timestamp)                                                             AS f_last_seen
  FROM `ftm-b9d99.firestore_export.summary_data_raw_latest`
  WHERE JSON_VALUE(data,'$.app_id') = 'feed-the-monster'
    AND JSON_VALUE(data,'$.cr_user_id') IS NOT NULL
    AND timestamp >= '{COMPARISON_START_DATE}'
  GROUP BY cr_user_id
),
-- The event log is the fallback source of language. `metadata.language` only
-- ships from container 2.34.5 onward; users still on 2.34.4 (and rows with no
-- metadata block at all) have no language on their summary doc. Dropping them
-- is not neutral — they average roughly double the max level of users who do
-- have it, so excluding them would systematically remove the most engaged FTM
-- players from the comparison. The event log's `data.lang` covers ~95% of them
-- and is already lowercase, so it normalizes the same way.
ftm_events AS (
  SELECT
    JSON_VALUE(data,'$.cr_user_id')                                      AS cr_user_id,
    APPROX_TOP_COUNT(JSON_VALUE(data,'$.data.lang'), 1)[OFFSET(0)].value AS f_event_lang
  FROM `ftm-b9d99.firestore_export.user_sessions_data_raw_latest`
  WHERE JSON_VALUE(data,'$.app_id') = 'feed-the-monster'
    AND JSON_VALUE(data,'$.cr_user_id') IS NOT NULL
    AND timestamp >= '{COMPARISON_START_DATE}'
  GROUP BY cr_user_id
),
ftm_all AS (
  SELECT cr_user_id FROM ftm_summary
  UNION DISTINCT
  SELECT cr_user_id FROM ftm_events
),
ftm AS (
  SELECT
    ftm_all.cr_user_id,
    s.* EXCEPT (cr_user_id, f_language),
    COALESCE(s.f_language, e.f_event_lang)                  AS f_language,
    s.f_language IS NULL AND e.f_event_lang IS NOT NULL     AS f_language_backfilled
  FROM ftm_all
  LEFT JOIN ftm_summary s USING (cr_user_id)
  LEFT JOIN ftm_events  e USING (cr_user_id)
)
SELECT
  COALESCE(a.cr_user_id, f.cr_user_id) AS cr_user_id,
  CASE WHEN a.cr_user_id IS NOT NULL AND f.cr_user_id IS NOT NULL THEN 'Both'
       WHEN a.cr_user_id IS NOT NULL                              THEN 'Assessment only'
       ELSE                                                            'FTM only' END AS cohort,
  a.* EXCEPT (cr_user_id),
  f.* EXCEPT (cr_user_id)
FROM assessment a
FULL OUTER JOIN ftm f USING (cr_user_id)
"""


@st.cache_data(ttl="1d", show_spinner=False)
def load_comparison_from_bq() -> pd.DataFrame:
    """One row per user across both apps, labelled with a cohort."""
    _, bq_client = get_gcp_credentials()
    return bq_client.query(COMPARISON_SQL).result().to_dataframe()


# ── Language matching ────────────────────────────────────────────────────────
# The two apps spell languages differently and neither is normalized upstream.
# Assessment sends lowercase-hyphenated (`west-african-english`); FTM sends
# CamelCase metadata with real inconsistency inside it — `BrazilianPortuguese`
# and `Brazilianportuguese`, `Afrikaans` and `Afrikans`, `Kembata` and
# `kembata`, `IndianEnglish` and `Indian English` all appear. Stripping to
# lowercase letters collapses every one of those pairs.
#
# What it cannot collapse is a different word order, so those get an explicit
# alias. Keep this map minimal: only add an entry when two spellings genuinely
# name the same language pack. Regional variants are deliberately NOT folded
# into their base language — FTM's `IndianEnglish`, `AustralianEnglish` and
# `SAenglish` are separate content from the assessment's plain `english`, and
# merging them would invent an overlap that does not exist.
LANGUAGE_ALIASES = {
    "englishwestafrican": "westafricanenglish",
}


def normalize_language(value) -> str | None:
    """Fold a language label to a comparable key, or None if there isn't one."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    key = re.sub(r"[^a-z]", "", str(value).lower())
    if not key:
        return None
    return LANGUAGE_ALIASES.get(key, key)


# ── Install date, recovered from cr_user_id ──────────────────────────────────
# Ids look like `85kqh9tnvk5sk53cb1qm90nk78` + `2026225161519`: 26 random
# characters followed by the creation time. The timestamp is **not zero-padded**
# (`${year}${month}${day}${hours}${minutes}${seconds}`), so its digit widths
# vary and a given string can have more than one arithmetically valid reading.
# Two things make it recoverable anyway:
#
#   * a candidate is only accepted if re-encoding it reproduces the id exactly,
#     which eliminates most readings; and
#   * the install cannot postdate the user's first record.
#
# The clock is **local**, and records are stored in UTC, so the ceiling carries
# a timezone slack — without it every user east of UTC fails to parse, which
# cost about a third of the population when this was first written.
#
# Where a string still admits several readings the latest is taken: ids are
# minted on first app open, so the reading nearest the first record is the
# likeliest. Roughly a quarter of ids need that tie-break, so treat individual
# ages as approximate; the distribution is sound, a single user's age may not be.
ID_TIMESTAMP_OFFSET = 26
ID_EPOCH_FLOOR = pd.Timestamp("2019-01-01")
ID_TZ_SLACK = pd.Timedelta(hours=14)


def parse_install_date(cr_user_id, not_after=None):
    """Creation time encoded in `cr_user_id`, or NaT if it cannot be read."""
    if not isinstance(cr_user_id, str):
        return pd.NaT
    tail = cr_user_id[ID_TIMESTAMP_OFFSET:]
    if not tail.isdigit() or not 9 <= len(tail) <= 14:
        return pd.NaT

    ceiling = pd.Timestamp("2100-01-01")
    if not_after is not None and pd.notna(not_after):
        ceiling = pd.Timestamp(not_after).tz_localize(None) + ID_TZ_SLACK

    candidates = []

    # 13 digits is also a plausible epoch-millisecond stamp; a few ids use one.
    if len(tail) == 13:
        try:
            dt = pd.Timestamp(int(tail), unit="ms")
            if ID_EPOCH_FLOOR <= dt <= ceiling:
                candidates.append(dt)
        except (ValueError, OverflowError, OSError):
            pass

    year = tail[:4]
    for widths in itertools.product((1, 2), repeat=5):
        if 4 + sum(widths) != len(tail):
            continue
        parts, i = [int(year)], 4
        for w in widths:
            parts.append(int(tail[i:i + w]))
            i += w
        try:
            dt = pd.Timestamp(*parts)
        except (ValueError, OverflowError):
            continue
        if not (ID_EPOCH_FLOOR <= dt <= ceiling):
            continue
        # Only accept a reading that reproduces the id it came from.
        if (f"{dt.year}{dt.month}{dt.day}"
                f"{dt.hour}{dt.minute}{dt.second}") == tail:
            candidates.append(dt)

    return max(candidates) if candidates else pd.NaT


def shared_languages(df: pd.DataFrame) -> set[str]:
    """Normalized languages present on BOTH sides of the comparison frame.

    Only these support a fair cohort comparison. Every FTM language exists as
    FTM content, but assessments exist in a much smaller set — so an FTM user
    playing in Gujarati is not someone who "chose not to assess", they are
    someone with no assessment to take. Counting them as an FTM-only user would
    make the assessment look far less popular than it is.
    """
    a = set(df.loc[df["cohort"] != "FTM only", "a_lang_norm"].dropna())
    f = set(df.loc[df["cohort"] != "Assessment only", "f_lang_norm"].dropna())
    return a & f


def add_comparison_derived(df: pd.DataFrame) -> pd.DataFrame:
    """Rates and orderings that are easier to read in pandas than in SQL.

    Every rate is guarded against a zero denominator and yields <NA> rather than
    inf — a user with no scored assessment is *unknown*, not 0%, and the two must
    not be plotted as if they were the same thing.
    """
    df = df.copy()

    df["a_score_pct"] = (
        df["a_score_sum"] / df["a_max_score_sum"]
    ).where(df["a_max_score_sum"] > 0).round(4)

    df["f_puzzle_success_pct"] = (
        df["f_puzzle_success"] / df["f_puzzles"]
    ).where(df["f_puzzles"] > 0).round(4)

    df["a_time_min"] = (df["a_time_sec"] / 60).round(1)
    df["f_time_min"] = (df["f_time_sec"] / 60).round(1)

    # Which app did the user touch first? Only meaningful for the Both cohort;
    # it decides which direction any "FTM helps assessment scores" story could
    # even run, and lets that cohort be split when the ordering is wrong.
    both_seen = df["a_first_seen"].notna() & df["f_first_seen"].notna()
    df["order_of_use"] = pd.Series(pd.NA, index=df.index, dtype="object")
    df.loc[both_seen & (df["f_first_seen"] < df["a_first_seen"]),
           "order_of_use"] = "FTM first"
    df.loc[both_seen & (df["f_first_seen"] >= df["a_first_seen"]),
           "order_of_use"] = "Assessment first"

    # ── Language keys for the shared-language filter ─────────────────────────
    df["a_lang_norm"] = df["a_lang"].map(normalize_language)
    df["f_lang_norm"] = df["f_language"].map(normalize_language)
    # The assessment label wins where both exist: it is the language the user
    # was actually assessed in, and it is populated for every assessment user,
    # whereas FTM's metadata.language is missing on a large minority of rows.
    # The two do disagree for a few users, who play FTM in one language and
    # assess in another.
    df["match_lang"] = df["a_lang_norm"].fillna(df["f_lang_norm"])
    df["match_lang_label"] = df["a_lang"].fillna(df["f_language"])

    # ── Install date and tenure ──────────────────────────────────────────────
    # `highest_level_completed` is a lifetime high-water mark, so it grows with
    # how long a user has had the game rather than with how much they played in
    # the window. Tenure makes that confound visible instead of implicit.
    first_seen = df[["a_first_seen", "f_first_seen"]].min(axis=1)
    last_seen = df[["a_last_seen", "f_last_seen"]].max(axis=1)
    df["install_date"] = [
        parse_install_date(uid, ceiling)
        for uid, ceiling in zip(df["cr_user_id"], first_seen)
    ]
    # Tenure runs to the user's last record, not to today, so someone who
    # stopped playing in April is not credited with the months since.
    age = (
        pd.to_datetime(last_seen).dt.tz_localize(None)
        - pd.to_datetime(df["install_date"])
    ).dt.total_seconds() / 86400
    # The id's clock is local and records are UTC, so a user who installed and
    # played within the same few hours can come out slightly negative. That is
    # timezone offset, not a real negative tenure, and it is always inside the
    # slack the parser already allows — clamp rather than discard.
    df["install_age_days"] = age.clip(lower=0).round(1)

    df["user_short"] = df["cr_user_id"].str.slice(0, 10)
    return df


def ensure_comparison_data_initialized():
    """Call at the top of the comparison page. Loads df_comparison once."""
    _guard_init(_init_comparison_data, "comparison_data_initialized",
                "assessment/FTM comparison data")


def _init_comparison_data():
    with st.spinner("Loading assessment / FTM comparison...", show_time=True):
        df_raw = load_comparison_from_bq()
        st.session_state["df_comparison"] = (
            add_comparison_derived(df_raw) if not df_raw.empty else pd.DataFrame()
        )
        st.session_state["comparison_data_initialized"] = True
