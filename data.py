import streamlit as st
import pandas as pd
import json
import traceback
import re
import gcsfs
from settings import get_gcp_credentials


# ══════════════════════════════════════════════════════════════════════════════
# Shared helpers
# ══════════════════════════════════════════════════════════════════════════════

RUN_DATE_RE = re.compile(r"/run_date=\d{4}-\d{2}-\d{2}/")


@st.cache_data(ttl="1d", show_spinner=False)
def load_parquet_from_gcs(file_pattern: str) -> pd.DataFrame:
    credentials, _ = get_gcp_credentials()
    fs = gcsfs.GCSFileSystem(project="ftm-b9d99", token=credentials)

    files = fs.glob(file_pattern)
    if not files:
        raise FileNotFoundError(f"No files matching pattern: {file_pattern}")

    if "run_date=*" in file_pattern:
        run_dirs = [m.group(0) for f in files if (m := RUN_DATE_RE.search(f))]
        if not run_dirs:
            raise FileNotFoundError(
                f"No run_date folders found: {file_pattern}")
        latest_run_dir = max(set(run_dirs))
        files = [f for f in files if latest_run_dir in f]

    df = pd.read_parquet(files, filesystem=fs).copy()
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
# Assessment app  (GCS parquet → df_assessments)
# ══════════════════════════════════════════════════════════════════════════════

def load_assessments_from_gcs() -> pd.DataFrame:
    # GCS export prefix is still "assessment_sessions_*" — external resource, not renamed.
    return load_parquet_from_gcs(
        "user_data_parquet_cache/assessment_sessions_*.parquet"
    )


def flatten_assessment_df(df_raw: pd.DataFrame) -> pd.DataFrame:
    """
    Flatten the JSON 'data' field into individual columns.

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
        df_raw = load_assessments_from_gcs()
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
    feed-the-monster, …), so we filter to app_id = 'feed-the-monster' in SQL.
    There is no GCS parquet export for this table yet; the row count is small
    (tens of rows), so a direct query is cheap.

    Returns the raw table columns with `timestamp` renamed to
    `firestore_timestamp` to match the assessment loader convention.
    """
    _, bq_client = get_gcp_credentials()
    query = f"""
        SELECT document_id, timestamp, event_id, operation, data
        FROM `{FTM_SUMMARY_TABLE}`
        WHERE JSON_VALUE(data, '$.app_id') = 'feed-the-monster'
    """
    df = bq_client.query(query).result().to_dataframe()
    if "timestamp" in df.columns and "firestore_timestamp" not in df.columns:
        df = df.rename(columns={"timestamp": "firestore_timestamp"})
    return df


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
