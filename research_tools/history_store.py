from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "researchmind_history.db"


def _connect():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=20)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db():
    with _connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS papers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fingerprint TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            author TEXT NOT NULL DEFAULT '',
            source_type TEXT NOT NULL DEFAULT 'Research paper',
            source_url TEXT NOT NULL DEFAULT '',
            total_pages INTEGER NOT NULL DEFAULT 0,
            total_words INTEGER NOT NULL DEFAULT 0,
            full_text TEXT NOT NULL DEFAULT '',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            summary TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paper_id INTEGER,
            event_type TEXT NOT NULL,
            title TEXT NOT NULL,
            detail TEXT NOT NULL DEFAULT '',
            content TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY(paper_id) REFERENCES papers(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paper_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(paper_id) REFERENCES papers(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS study_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paper_id INTEGER NOT NULL,
            kind TEXT NOT NULL,
            content_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(paper_id) REFERENCES papers(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS quiz_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paper_id INTEGER NOT NULL,
            score INTEGER NOT NULL,
            total INTEGER NOT NULL,
            answers_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL,
            FOREIGN KEY(paper_id) REFERENCES papers(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_events_created ON events(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_events_paper ON events(paper_id);
        """)


def _now():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def save_paper(paper_data: dict, fingerprint: str) -> int:
    metadata = paper_data.get("metadata") or {}
    now = _now()
    values = (
        fingerprint,
        str(metadata.get("title") or "Untitled research paper"),
        str(metadata.get("author") or ""),
        str(paper_data.get("source_type") or "Research paper"),
        str(paper_data.get("source_url") or ""),
        int(paper_data.get("total_pages") or 0),
        int(paper_data.get("total_words") or 0),
        str(paper_data.get("full_text") or ""),
        json.dumps(metadata, ensure_ascii=False),
        now,
        now,
    )
    with _connect() as db:
        db.execute("""INSERT INTO papers
            (fingerprint,title,author,source_type,source_url,total_pages,total_words,full_text,metadata_json,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(fingerprint) DO UPDATE SET
              title=excluded.title, author=excluded.author,
              source_type=excluded.source_type, source_url=excluded.source_url,
              total_pages=excluded.total_pages, total_words=excluded.total_words,
              full_text=excluded.full_text, metadata_json=excluded.metadata_json,
              updated_at=excluded.updated_at
        """, values)
        row = db.execute("SELECT id FROM papers WHERE fingerprint=?", (fingerprint,)).fetchone()
        return int(row["id"])


def save_summary(paper_id: int, summary: str):
    now = _now()
    with _connect() as db:
        db.execute("UPDATE papers SET summary=?, updated_at=? WHERE id=?", (summary, now, paper_id))


def log_event(event_type: str, title: str, detail: str = "", content: str = "", paper_id: int | None = None):
    with _connect() as db:
        db.execute("INSERT INTO events(paper_id,event_type,title,detail,content,created_at) VALUES(?,?,?,?,?,?)",
                   (paper_id, event_type, title, detail, content, _now()))


def get_papers(include_text: bool = False):
    fields = "id,title,author,source_type,source_url,total_pages,total_words,summary,created_at,updated_at"
    if include_text:
        fields += ",full_text,metadata_json"
    with _connect() as db:
        return [dict(row) for row in db.execute(f"SELECT {fields} FROM papers ORDER BY updated_at DESC")]


def get_paper(paper_id: int):
    with _connect() as db:
        row = db.execute("SELECT * FROM papers WHERE id=?", (paper_id,)).fetchone()
        return dict(row) if row else None


def get_events(paper_id: int | None = None, limit: int = 500):
    with _connect() as db:
        if paper_id is None:
            rows = db.execute("""SELECT e.*, p.title AS paper_title FROM events e
                LEFT JOIN papers p ON p.id=e.paper_id ORDER BY e.created_at DESC LIMIT ?""", (limit,))
        else:
            rows = db.execute("""SELECT e.*, p.title AS paper_title FROM events e
                LEFT JOIN papers p ON p.id=e.paper_id WHERE e.paper_id=?
                ORDER BY e.created_at DESC LIMIT ?""", (paper_id, limit))
        return [dict(row) for row in rows]


def save_note(paper_id: int, content: str):
    now = _now()
    with _connect() as db:
        db.execute("INSERT INTO notes(paper_id,content,created_at,updated_at) VALUES(?,?,?,?)",
                   (paper_id, content, now, now))
    log_event("note", "Research note saved", "A note was added to this paper.", content, paper_id)


def get_notes(paper_id: int):
    with _connect() as db:
        return [dict(row) for row in db.execute(
            "SELECT * FROM notes WHERE paper_id=? ORDER BY created_at DESC", (paper_id,))]


def save_study_items(paper_id: int, kind: str, items):
    payload = json.dumps(items, ensure_ascii=False)
    with _connect() as db:
        db.execute("INSERT INTO study_items(paper_id,kind,content_json,created_at) VALUES(?,?,?,?)",
                   (paper_id, kind, payload, _now()))
    log_event(kind, f"{kind.replace('_', ' ').title()} created", f"{len(items)} study items saved.", payload, paper_id)


def get_study_items(paper_id: int, kind: str):
    """Return the most recently generated set for this paper and study type."""
    with _connect() as db:
        row = db.execute("SELECT content_json FROM study_items WHERE paper_id=? AND kind=? ORDER BY id DESC LIMIT 1",
                         (paper_id, kind)).fetchone()
    if not row:
        return []
    try:
        items = json.loads(row["content_json"])
        return items if isinstance(items, list) else []
    except (TypeError, json.JSONDecodeError):
        return []


def record_quiz_attempt(paper_id: int, score: int, total: int, answers):
    with _connect() as db:
        db.execute("INSERT INTO quiz_attempts(paper_id,score,total,answers_json,created_at) VALUES(?,?,?,?,?)",
                   (paper_id, score, total, json.dumps(answers, ensure_ascii=False), _now()))
    log_event("quiz", "Quiz completed", f"Score: {score}/{total}", json.dumps(answers, ensure_ascii=False), paper_id)


def get_quiz_stats(paper_id: int):
    with _connect() as db:
        row = db.execute("SELECT COUNT(*) AS attempts, COALESCE(MAX(score),0) AS best_score, COALESCE(MAX(total),0) AS total FROM quiz_attempts WHERE paper_id=?",
                         (paper_id,)).fetchone()
        return dict(row)
