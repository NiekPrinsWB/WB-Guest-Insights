"""
Westerbergen Guest Insights - Database layer (SQLite)
"""
import sqlite3
import hashlib
import pandas as pd
from datetime import datetime
from app.config import DB_PATH


def get_connection(db_path=None):
    """Get a SQLite connection."""
    path = db_path or DB_PATH
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(conn=None):
    """Create tables if they don't exist."""
    close = False
    if conn is None:
        conn = get_connection()
        close = True

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS responses_raw (
            unique_key TEXT PRIMARY KEY,
            reserveringsnummer TEXT,
            relatie TEXT,
            aankomst TEXT,
            vertrek TEXT,
            ingevuld_op TEXT,
            objectsoort TEXT,
            objectnaam TEXT,
            verhuurmodel TEXT,
            vraag TEXT,
            antwoord TEXT,
            aanvulling TEXT,
            segment TEXT,
            categorie TEXT,
            vraag_label TEXT,
            score REAL,
            jaar INTEGER,
            week INTEGER,
            maand INTEGER,
            nps_groep TEXT,
            created_at TEXT,
            updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS ingestion_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            filename TEXT,
            segment TEXT,
            mode TEXT,
            rows_read INTEGER,
            rows_inserted INTEGER,
            rows_updated INTEGER,
            rows_skipped INTEGER,
            rows_error INTEGER,
            details TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_responses_segment ON responses_raw(segment);
        CREATE INDEX IF NOT EXISTS idx_responses_categorie ON responses_raw(categorie);
        CREATE INDEX IF NOT EXISTS idx_responses_jaar ON responses_raw(jaar);
        CREATE INDEX IF NOT EXISTS idx_responses_week ON responses_raw(jaar, week);
        CREATE INDEX IF NOT EXISTS idx_responses_objectsoort ON responses_raw(objectsoort);
        CREATE INDEX IF NOT EXISTS idx_responses_objectnaam ON responses_raw(objectnaam);
        CREATE INDEX IF NOT EXISTS idx_responses_score ON responses_raw(score);
    """)
    conn.commit()
    if close:
        conn.close()


def compute_unique_key(row):
    """Compute unique key from reserveringsnummer + vraag + ingevuld_op + segment."""
    raw = f"{row.get('reserveringsnummer', '')}" \
          f"|{row.get('vraag', '')}" \
          f"|{row.get('ingevuld_op', '')}" \
          f"|{row.get('segment', '')}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def load_responses(conn=None) -> pd.DataFrame:
    """Load all responses from the database."""
    close = False
    if conn is None:
        conn = get_connection()
        close = True

    df = pd.read_sql_query("SELECT * FROM responses_raw", conn)
    if close:
        conn.close()

    # Type conversions
    if not df.empty:
        df["score"] = pd.to_numeric(df["score"], errors="coerce")
        df["jaar"] = pd.to_numeric(df["jaar"], errors="coerce").astype("Int64")
        df["week"] = pd.to_numeric(df["week"], errors="coerce").astype("Int64")
        df["maand"] = pd.to_numeric(df["maand"], errors="coerce").astype("Int64")
        for col in ["ingevuld_op", "aankomst", "vertrek"]:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


def log_ingestion(conn, filename, segment, mode, stats):
    """Log an ingestion event."""
    now = datetime.now().isoformat()
    conn.execute(
        """INSERT INTO ingestion_log
           (timestamp, filename, segment, mode, rows_read, rows_inserted,
            rows_updated, rows_skipped, rows_error, details)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            now, filename, segment, mode,
            stats.get("read", 0),
            stats.get("inserted", 0),
            stats.get("updated", 0),
            stats.get("skipped", 0),
            stats.get("error", 0),
            stats.get("details", ""),
        ),
    )
    conn.commit()
