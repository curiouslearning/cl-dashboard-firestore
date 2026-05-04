import streamlit as st
import pandas as pd
import json
import traceback
import re
import gcsfs
from settings import get_gcp_credentials


# ── GCS parquet loader (mirrors users.py pattern) ─────────────────────────────

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


def load_assessments_from_gcs() -> pd.DataFrame:
    # GCS export prefix is still "assessment_sessions_*" — external resource, not renamed.
    return load_parquet_from_gcs(
        "user_data_parquet_cache/assessment_sessions_*.parquet"
    )


# ── Flattening ────────────────────────────────────────────────────────────────

def _parse_json(val) -> dict:
    if pd.isna(val) or val == "":
        return {}
    try:
        return json.loads(val)
    except Exception:
        return {}


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


# ── Session state initialization ──────────────────────────────────────────────

def ensure_data_initialized():
    """Call this at the top of every page. Loads data once per session."""
    if "data_initialized" not in st.session_state:
        try:
            init_data()
        except Exception as e:
            st.error(f"❌ Failed to initialize data: {e}")
            st.text(traceback.format_exc())
            st.stop()


def init_data():
    if st.session_state.get("data_initialized"):
        return

    with st.spinner("Loading assessment data...", show_time=True):
        df_raw = load_assessments_from_gcs()

        if df_raw.empty:
            raise ValueError("Assessments table returned no rows.")

        df_assessment = flatten_assessment_df(df_raw)

        st.session_state["df_assessments"] = df_assessment
        st.session_state["data_initialized"] = True
