# 💊 Drug Shortage Tracker

A production-quality healthcare analytics dashboard that pulls drug shortage data from the **openFDA Drug Shortages API** and presents it in an interactive Streamlit application backed by SQLite.

---

## Features

| Feature | Description |
|---------|-------------|
| 📊 Dashboard | KPI cards, status pie, top manufacturers, shortage reasons |
| 🔍 Search | Query live API or cached snapshot by drug/manufacturer/reason |
| 📋 Data Table | Filterable, sortable table with CSV export |
| 📈 Trends | Historical charts from SQLite snapshots |
| 🔔 Alerts | Auto-detected new / resolved / status-change events |
| ⭐ Watchlist | Persist drugs you care about across sessions |

---

## Project Structure

```
DrugShortageTracker/
├── app.py           # Streamlit entry point — all page layout lives here
├── api.py           # openFDA client with pagination
├── database.py      # SQLite helpers (snapshots, watchlist, alerts)
├── dashboard.py     # Plotly chart builders
├── requirements.txt # Python dependencies
├── README.md        # This file
└── data/
    └── shortages.db # Auto-created SQLite database
```

---

## Quick Start

### 1. Install dependencies

```bash
cd DrugShortageTracker
pip install -r requirements.txt
```

### 2. Run the app

```bash
streamlit run app.py
```

Your browser will open at **http://localhost:8501** automatically.

### 3. Load data

- Click **"Fetch Latest Data"** in the left sidebar to pull records from openFDA.
- Or click **"Load Cached Data"** if you've fetched before and want to skip the API call.

---

## How It Works

### Data flow

```
openFDA API
    │
    ▼  (api.py — paginated GET requests)
raw JSON records
    │
    ▼  (database.py — save_snapshot)
SQLite snapshots table
    │
    ▼  (app.py — records_to_df)
pandas DataFrame  ──►  Plotly charts (dashboard.py)
                  ──►  Streamlit data tables
                  ──►  Alert diffing → alerts table
```

### Alert detection

Every time you fetch new data the app compares the incoming snapshot to the previous one:
- **New**: a `generic_name` that didn't exist before
- **Resolved**: a drug no longer present in the new data
- **Status change**: same drug, different `status` field

Alerts are stored permanently in SQLite so you can review them later.

### Watchlist

Watchlisted drugs are stored in the `watchlist` SQLite table. The Watchlist page cross-references each entry against the currently loaded snapshot to show live status.

---

## API Notes

- No API key required for ≤ 1 000 requests / day.
- The app requests a maximum of **500 records by default** (configurable via the sidebar slider up to 2 000).
- Full openFDA docs: https://open.fda.gov/apis/drug/shortages/

---

## Extending the App

- **Add more fields**: modify `records_to_df()` in `app.py` and the `save_snapshot()` INSERT in `database.py`.
- **Email alerts**: call `save_alerts()` then send an SMTP email in `app.py` after detection.
- **Scheduled refresh**: run `python -c "import api, database; database.save_snapshot(api.fetch_shortages())"` in a cron job.
