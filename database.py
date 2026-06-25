"""
database.py — SQLite persistence layer for Drug Shortage Tracker.

Handles three tables:
  - snapshots: raw API records saved at each refresh
  - watchlist: drugs the user wants to monitor
  - alerts: detected changes between consecutive snapshots
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "shortages.db"


def get_connection() -> sqlite3.Connection:
    """Return a connection with row-factory set so rows behave like dicts."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create all tables on first run (idempotent)."""
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS snapshots (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                fetched_at    TEXT NOT NULL,
                generic_name  TEXT,
                brand_name    TEXT,
                manufacturer  TEXT,
                reason        TEXT,
                status        TEXT,
                initial_posting_date TEXT,
                update_date   TEXT,
                raw_json      TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_snap_generic
                ON snapshots(generic_name);
            CREATE INDEX IF NOT EXISTS idx_snap_fetched
                ON snapshots(fetched_at);

            CREATE TABLE IF NOT EXISTS watchlist (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                generic_name TEXT NOT NULL UNIQUE,
                added_at     TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS alerts (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                detected_at  TEXT NOT NULL,
                alert_type   TEXT NOT NULL,   -- 'new', 'resolved', 'status_change'
                generic_name TEXT,
                brand_name   TEXT,
                manufacturer TEXT,
                old_status   TEXT,
                new_status   TEXT,
                detail       TEXT
            );
            """
        )


# ── Snapshot helpers ─────────────────────────────────────────────────────────

def _extract_manufacturer(r: dict) -> str:
    """
    The openFDA shortages API stores the company in 'company_name' at the
    top level. 'manufacturer_name' is always None. Fall back to the nested
    openfda.manufacturer_name list when company_name is also absent.
    """
    name = r.get("company_name") or ""
    if not name:
        openfda = r.get("openfda") or {}
        mfr_list = openfda.get("manufacturer_name") or []
        name = mfr_list[0] if mfr_list else ""
    return name.strip()


def _extract_brand(r: dict) -> str:
    """Top-level brand_name is often absent; fall back to openfda.brand_name."""
    name = r.get("brand_name") or ""
    if not name:
        openfda = r.get("openfda") or {}
        brand_list = openfda.get("brand_name") or []
        name = brand_list[0] if brand_list else ""
    return name.strip()


def _build_rows(records: list[dict], timestamp: str) -> list[tuple]:
    return [
        (
            timestamp,
            (r.get("generic_name") or "").strip(),
            _extract_brand(r),
            _extract_manufacturer(r),
            (r["shortage_reason"].get("reason_text", "") if isinstance(r.get("shortage_reason"), dict) else (r.get("shortage_reason") or "")).strip(),
            (r.get("status") or "").strip(),
            r.get("initial_posting_date", ""),
            r.get("update_date", ""),
            json.dumps(r),
        )
        for r in records
    ]


def save_snapshot(records: list[dict]) -> int:
    """Persist a list of API records; return count inserted."""
    if not records:
        return 0
    rows = _build_rows(records, datetime.utcnow().isoformat())
    with get_connection() as conn:
        conn.executemany(
            """INSERT INTO snapshots
               (fetched_at, generic_name, brand_name, manufacturer,
                reason, status, initial_posting_date, update_date, raw_json)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            rows,
        )
    return len(rows)


def save_snapshot_at(records: list[dict], timestamp: str) -> int:
    """Persist records with an explicit ISO timestamp (for demo / backfill use)."""
    if not records:
        return 0
    rows = _build_rows(records, timestamp)
    with get_connection() as conn:
        conn.executemany(
            """INSERT INTO snapshots
               (fetched_at, generic_name, brand_name, manufacturer,
                reason, status, initial_posting_date, update_date, raw_json)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            rows,
        )
    return len(rows)


def get_latest_snapshot(limit: int = 2000) -> list[dict]:
    """Return all rows from the most recent fetch batch."""
    with get_connection() as conn:
        latest_ts = conn.execute(
            "SELECT MAX(fetched_at) AS ts FROM snapshots"
        ).fetchone()["ts"]
        if not latest_ts:
            return []
        rows = conn.execute(
            "SELECT * FROM snapshots WHERE fetched_at = ? LIMIT ?",
            (latest_ts, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def get_snapshot_dates() -> list[str]:
    """Return all distinct fetch timestamps (newest first)."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT DISTINCT fetched_at FROM snapshots ORDER BY fetched_at DESC"
        ).fetchall()
    return [r["fetched_at"] for r in rows]


def get_snapshot_by_date(ts: str) -> list[dict]:
    """Return all rows for a specific fetch timestamp."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM snapshots WHERE fetched_at = ?", (ts,)
        ).fetchall()
    return [dict(r) for r in rows]


def count_snapshots_per_day() -> list[dict]:
    """Return daily record counts for trend charts."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT DATE(fetched_at) AS day, COUNT(*) AS record_count
            FROM snapshots
            GROUP BY day
            ORDER BY day
            """
        ).fetchall()
    return [dict(r) for r in rows]


# ── Watchlist helpers ────────────────────────────────────────────────────────

def add_to_watchlist(generic_name: str) -> bool:
    """Add a drug; return False if it already exists."""
    try:
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO watchlist (generic_name, added_at) VALUES (?, ?)",
                (generic_name.strip(), datetime.utcnow().isoformat()),
            )
        return True
    except sqlite3.IntegrityError:
        return False


def remove_from_watchlist(generic_name: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM watchlist WHERE generic_name = ?", (generic_name,)
        )


def get_watchlist() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM watchlist ORDER BY added_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


# ── Alert helpers ────────────────────────────────────────────────────────────

def save_alerts(alerts: list[dict]) -> None:
    if not alerts:
        return
    now = datetime.utcnow().isoformat()
    rows = [
        (
            now,
            a.get("alert_type"),
            a.get("generic_name"),
            a.get("brand_name"),
            a.get("manufacturer"),
            a.get("old_status"),
            a.get("new_status"),
            a.get("detail"),
        )
        for a in alerts
    ]
    with get_connection() as conn:
        conn.executemany(
            """INSERT INTO alerts
               (detected_at, alert_type, generic_name, brand_name,
                manufacturer, old_status, new_status, detail)
               VALUES (?,?,?,?,?,?,?,?)""",
            rows,
        )


def get_recent_alerts(limit: int = 200) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM alerts ORDER BY detected_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]
