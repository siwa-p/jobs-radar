# sqlite storage for job search results and user feedback — single table design
import sqlite3
from jobs_radar.config import settings
from jobs_radar.models import FeedbackEntry, JobMatch

settings.data_dir.mkdir(parents=True, exist_ok=True)
DB_PATH = str(settings.data_dir / "feedback.db")


def _get_conn(db_path: str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS job_results (
            job_url          TEXT PRIMARY KEY,
            title            TEXT,
            company          TEXT,
            location         TEXT,
            description      TEXT,
            date_posted      TEXT,
            experience_required TEXT,
            relevance_score  REAL,
            llm_rating       INTEGER,
            llm_reasoning    TEXT,
            user_rating      INTEGER,
            notes            TEXT,
            search_id        TEXT,
            saved_at         DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    return conn


def save_results(matches: list[JobMatch], search_id: str, db_path: str = DB_PATH):
    with _get_conn(db_path) as conn:
        for m in matches:
            conn.execute("""
                INSERT INTO job_results
                    (job_url, title, company, location, description, date_posted,
                     experience_required, relevance_score, llm_rating, llm_reasoning, search_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_url) DO UPDATE SET
                    relevance_score = excluded.relevance_score,
                    llm_rating      = excluded.llm_rating,
                    llm_reasoning   = excluded.llm_reasoning,
                    search_id       = excluded.search_id,
                    saved_at        = CURRENT_TIMESTAMP
            """, (
                m.job_url, m.title, m.company, m.location, m.description,
                str(m.date_posted) if m.date_posted else None,
                m.experience_required, m.relevance_score, m.llm_rating, m.llm_reasoning, search_id,
            ))


def save_feedback(job_url: str, user_rating: int, notes: str, db_path: str = DB_PATH):
    with _get_conn(db_path) as conn:
        conn.execute("""
            INSERT INTO job_results (job_url, user_rating, notes)
            VALUES (?, ?, ?)
            ON CONFLICT(job_url) DO UPDATE SET
                user_rating = excluded.user_rating,
                notes       = excluded.notes
        """, (job_url, user_rating, notes))


def load_recent(db_path: str = DB_PATH) -> list[dict]:
    conn = _get_conn(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.execute("""
        SELECT * FROM job_results
        WHERE search_id = (SELECT MAX(search_id) FROM job_results)
        ORDER BY llm_rating DESC
    """)
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def load_examples(limit_liked: int = 3, limit_disliked: int = 2, db_path: str = DB_PATH):
    conn = _get_conn(db_path)
    conn.row_factory = sqlite3.Row

    cursor = conn.execute(
        "SELECT * FROM job_results WHERE user_rating >= 4 ORDER BY user_rating DESC LIMIT ?",
        (limit_liked,)
    )
    liked = [
        FeedbackEntry(
            job_url=row["job_url"], title=row["title"] or "", company=row["company"] or "",
            rating=row["user_rating"], notes=row["notes"] or "",
        )
        for row in cursor.fetchall()
    ]

    cursor = conn.execute(
        "SELECT * FROM job_results WHERE user_rating <= 2 ORDER BY user_rating ASC LIMIT ?",
        (limit_disliked,)
    )
    disliked = [
        FeedbackEntry(
            job_url=row["job_url"], title=row["title"] or "", company=row["company"] or "",
            rating=row["user_rating"], notes=row["notes"] or "",
        )
        for row in cursor.fetchall()
    ]

    conn.close()
    return liked, disliked


def load_all(db_path: str = DB_PATH) -> list[dict]:
    conn = _get_conn(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.execute("SELECT * FROM job_results ORDER BY saved_at DESC")
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows
