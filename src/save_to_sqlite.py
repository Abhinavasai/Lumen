"""
save_to_sqlite.py
UPSERTs deduped jobs into jobs.db and logs run stats in job_runs.
"""
import json
import os
import sqlite3
from datetime import datetime

# ── Path resolution ─────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
DB_DIR = os.path.join(BASE_DIR, "db")
os.makedirs(DB_DIR, exist_ok=True)

DEDUPED_INPUT = os.path.join(OUTPUT_DIR, "deduped_jobs.json")
DB_PATH = os.path.join(DB_DIR, "jobs.db")


def init_db(conn: sqlite3.Connection):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            source          TEXT,
            source_job_id   TEXT,
            company         TEXT,
            title           TEXT,
            location        TEXT,
            url             TEXT UNIQUE,
            description     TEXT,
            posted_at       TEXT,
            normalized_key  TEXT,
            status          TEXT DEFAULT 'new',
            run_date        TEXT,
            ai_score        REAL,
            ai_reason       TEXT,
            is_top_pick     INTEGER DEFAULT 0,
            dismissed       INTEGER DEFAULT 0
        )
    """)
    # Migrate existing databases that lack the new columns
    existing = {row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
    for col, default in [("is_top_pick", "0"), ("dismissed", "0")]:
        if col not in existing:
            conn.execute(f"ALTER TABLE jobs ADD COLUMN {col} INTEGER DEFAULT {default}")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS job_runs (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            run_date        TEXT,
            source          TEXT,
            new_jobs        INTEGER,
            duplicate_jobs  INTEGER
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS applied_jobs (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            source_job_id   TEXT UNIQUE,
            title           TEXT,
            company         TEXT,
            url             TEXT,
            applied_at      TEXT
        )
    """)
    conn.commit()


def save_jobs(jobs: list | None = None, run_date: str | None = None) -> int:
    if jobs is None:
        with open(DEDUPED_INPUT, encoding="utf-8") as f:
            jobs = json.load(f)

    if run_date is None:
        run_date = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    conn = sqlite3.connect(DB_PATH)
    init_db(conn)

    new_count = 0
    dup_count = 0
    source_stats: dict[str, int] = {}

    for job in jobs:
        source = job.get("source", "unknown")
        url = job.get("url", "")
        if not url:
            # Skip jobs with no URL â€” can't dedup them reliably
            continue
        try:
            conn.execute(
                """
                INSERT INTO jobs
                    (source, source_job_id, company, title, location, url,
                     description, posted_at, normalized_key, run_date, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new')
                ON CONFLICT(url) DO UPDATE SET
                    title          = excluded.title,
                    description    = excluded.description,
                    run_date       = excluded.run_date,
                    status         = 'new',
                    ai_score       = NULL,
                    ai_reason      = NULL
                """,
                (
                    source,
                    job.get("source_job_id", ""),
                    job.get("company", ""),
                    job.get("title", ""),
                    job.get("location", ""),
                    url,
                    job.get("description", ""),
                    job.get("posted_at", ""),
                    job.get("normalized_key", ""),
                    run_date,
                ),
            )
            new_count += 1
            source_stats[source] = source_stats.get(source, 0) + 1
        except sqlite3.IntegrityError:
            dup_count += 1

    for source, count in source_stats.items():
        conn.execute(
            "INSERT INTO job_runs (run_date, source, new_jobs, duplicate_jobs) VALUES (?, ?, ?, ?)",
            (run_date, source, count, dup_count),
        )

    conn.commit()
    conn.close()

    print(f"[sqlite] Saved {new_count} jobs ({dup_count} integrity conflicts) â†’ jobs.db")
    return new_count


if __name__ == "__main__":
    save_jobs()

