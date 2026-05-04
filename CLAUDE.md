# CLAUDE.md — CL Assessment Dashboard

# Project Overview

from data import ensure_data_initialized
from settings import initialize
Streamlit analytics dashboard for the ** Curious Learning Assessment app**.
Data originates from **Firestore**, is exported to ** BigQuery**, cached as
**GCS parquet files**, and loaded into Streamlit session state at startup.

---

# Stack

- **Python ** 3.12
- **Streamlit ** 1.48
- **BigQuery ** + **GCS parquet ** as data backend
- **gcsfs ** for GCS access
- **Pandas ** for all data manipulation
- **Plotly ** for charts(when added)
- **st_pages ** for navigation(`get_nav_from_toml`)

---

# Project Structure

```
main.py                        # Entry point — set_page_config, navigation, footer
settings.py                    # GCP credentials, initialize(), get_logger()
data.py                        # Data loading, flattening, session state init
colors.py                      # Global color palette (Lavender Dusk theme)
ui.py                          # CSS injection + HTML tile / section-header renderers
app_pages/
home.py                      # Home page — summary tiles + assessment charts
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

Use `divider = "violet"` in `st.subheader()` to match the theme.

---

# Data Source

# Firestore → BigQuery table
```
ftm-b9d99.firestore_export.user_sessions_data_raw_latest
```

# GCS parquet export (run as scheduled query)
```sql
EXPORT DATA OPTIONS(
    uri='gs://user_data_parquet_cache/assessment_sessions_*.parquet',
    format='PARQUET',
    overwrite=true
) AS
SELECT * FROM `ftm-b9d99.firestore_export.user_sessions_data_raw_latest`
```

# GCS load pattern in `data.py`
```python
load_parquet_from_gcs("user_data_parquet_cache/assessment_sessions_*.parquet")
```

The loader automatically renames `timestamp` → `firestore_timestamp` if needed,
since `SELECT * ` preserves the original Firestore column name.

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
in user-facing text and internal keys; "session" survives only in upstream
resource names (`user_sessions_data_raw_latest`, `assessment_sessions_*.parquet`).

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

# Key facts about the data (as of Apr 2026)
- 103 rows total(80 CREATE, 23 UPDATE)
- 86 unique `cr_user_id` values — some users have multiple rows
- Multiple rows per user are retained(not deduplicated)
- 5 languages, 2 activity types(`letter-sounds`, `sight-words`)

---

# Data Loading Pattern

All data loads once at startup via `ensure_data_initialized()`.
Call this at the top of every page before accessing session state.

```python

initialize()
ensure_data_initialized()

df = st.session_state["df_assessments"]
```

# Session state keys

| Key | Content |
|--- | ---|
| `df_assessments` | Fully flattened assessments DataFrame (one row = one completed assessment) |
| `data_initialized` | Boolean guard — prevents double loading |

---

# GCP Credentials

Credentials are fetched from **Secret Manager ** at startup:
```
projects/405806232197/secrets/service_account_json/versions/latest
```

The service account needs:
- BigQuery read on `ftm-b9d99`
- GCS read on `user_data_parquet_cache`

`get_gcp_credentials()` is `@st.cache_resource(ttl="1d")` — returns
`(gcp_credentials, bq_client)`.

---

# Adding a New Page

1. Create `app_pages/your_page.py`
2. Add an entry to `.streamlit/pages.toml`
3. Call `initialize()` and `ensure_data_initialized()` at the top
4. Access data via `st.session_state["df_assessments"]`

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
