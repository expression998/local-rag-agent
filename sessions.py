"""会话持久化：SQLite 存储对话历史，重启后可恢复。仅用标准库。"""
from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).parent / "sessions.db"
PREVIEW_LEN = 60


class SessionStore:
    def __init__(self, db_path: Path | str = DB_PATH) -> None:
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    seq INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    UNIQUE (session_id, seq),
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
                );
                """
            )
            self._conn.commit()

    def list_sessions(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT s.session_id, s.created_at, s.updated_at,
                       (SELECT content FROM messages m
                         WHERE m.session_id = s.session_id AND m.role = 'user'
                         ORDER BY m.seq LIMIT 1) AS first_question
                  FROM sessions s
                 ORDER BY s.updated_at DESC
                 LIMIT ?
                """,
                (limit,),
            ).fetchall()
        sessions = []
        for row in rows:
            question = row["first_question"] or ""
            preview = question[:PREVIEW_LEN] + ("..." if len(question) > PREVIEW_LEN else "")
            sessions.append(
                {
                    "session_id": row["session_id"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                    "preview": preview,
                }
            )
        return sessions

    def messages(self, session_id: str) -> list[dict[str, str]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT role, content FROM messages WHERE session_id = ? ORDER BY seq",
                (session_id,),
            ).fetchall()
        return [{"role": row["role"], "content": row["content"]} for row in rows]

    def append(self, session_id: str, question: str, answer: str) -> None:
        now = time.time()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO sessions (session_id, created_at, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET updated_at = excluded.updated_at
                """,
                (session_id, now, now),
            )
            start = self._conn.execute(
                "SELECT COALESCE(MAX(seq), 0) FROM messages WHERE session_id = ?",
                (session_id,),
            ).fetchone()[0]
            self._conn.execute(
                "INSERT INTO messages (session_id, seq, role, content) VALUES (?, ?, ?, ?)",
                (session_id, start + 1, "user", question),
            )
            self._conn.execute(
                "INSERT INTO messages (session_id, seq, role, content) VALUES (?, ?, ?, ?)",
                (session_id, start + 2, "assistant", answer),
            )
            self._conn.commit()

    def delete(self, session_id: str) -> None:
        with self._lock:
            self._conn.execute(
                "DELETE FROM messages WHERE session_id = ?", (session_id,)
            )
            self._conn.execute(
                "DELETE FROM sessions WHERE session_id = ?", (session_id,)
            )
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()
