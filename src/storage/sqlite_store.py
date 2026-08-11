from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import bcrypt

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "legal_chat.db")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def initialize_database() -> None:
    conn = _connect()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                status TEXT NOT NULL DEFAULT 'Active',
                is_deleted INTEGER NOT NULL DEFAULT 0,
                deleted_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS chat_sessions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS chat_messages (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                sources_json TEXT,
                feedback TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS feedback_events (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                message_id TEXT,
                feedback TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (session_id) REFERENCES chat_sessions(id)
            );
            """
        )

        conn.commit()

        seed_users(conn)
        seed_sessions(conn)
        seed_messages(conn)
        seed_feedback(conn)
        conn.commit()
    finally:
        conn.close()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _row_to_user(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "username": row["username"],
        "email": row["email"],
        "password_hash": row["password_hash"],
        "role": row["role"],
        "status": row["status"],
        "is_deleted": bool(row["is_deleted"]),
        "deleted_at": row["deleted_at"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _row_to_session(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "title": row["title"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def seed_users(conn: sqlite3.Connection) -> None:
    count = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
    if count > 0:
        return

    now = _now()
    users = [
        ("user-1", "user1", "user1@phapluat.vn", hash_password("password123"), "user", "Active", 0, None, now, now),
        ("admin-1", "admin", "admin@phapluat.vn", hash_password("admin123"), "admin", "Active", 0, None, now, now),
        ("user-2", "minh_tran", "minh.tran@lawfirm.vn", hash_password("password123"), "user", "Active", 0, None, now, now),
        ("user-3", "hoang_nam", "nam.hoang@company.com", hash_password("password123"), "user", "Active", 0, None, now, now),
        ("user-4", "lan_anh", "lananh.legal@gmail.com", hash_password("password123"), "user", "Active", 0, None, now, now),
    ]
    conn.executemany(
        """
        INSERT INTO users (id, username, email, password_hash, role, status, is_deleted, deleted_at, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        users,
    )


def seed_sessions(conn: sqlite3.Connection) -> None:
    count = conn.execute("SELECT COUNT(*) AS c FROM chat_sessions").fetchone()["c"]
    if count > 0:
        return

    user_ids = {
        "user1": "user-1",
        "admin": "admin-1",
        "minh_tran": "user-2",
        "hoang_nam": "user-3",
        "lan_anh": "user-4",
    }
    sessions = [
        ("sess-1", user_ids["user1"], "Thời gian thử việc Luật Lao động 2019", _now(), _now()),
        ("sess-2", user_ids["user1"], "Thủ tục thành lập công ty TNHH 1 thành viên", _now(), _now()),
    ]
    conn.executemany(
        "INSERT INTO chat_sessions (id, user_id, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        sessions,
    )


def seed_messages(conn: sqlite3.Connection) -> None:
    count = conn.execute("SELECT COUNT(*) AS c FROM chat_messages").fetchone()["c"]
    if count > 0:
        return

    messages = [
        (
            "msg-1",
            "sess-1",
            "assistant",
            "Xin chào! Tôi là Trợ lý Pháp luật Việt Nam. Tôi có thể hỗ trợ bạn tra cứu Bộ luật Dân sự, Luật Lao động, Bộ luật Hình sự, Luật Doanh nghiệp và nhiều văn bản pháp luật khác.",
            json.dumps([{"title": "Điều 1, Bộ luật Dân sự 2015", "snippet": "Bộ luật này quy định địa vị pháp lý, chuẩn mực pháp lý cho cách ứng xử của cá nhân, pháp nhân...", "score": 0.95}], ensure_ascii=False),
            None,
            _now(),
        ),
        (
            "msg-2",
            "sess-2",
            "assistant",
            "Chào bạn! Hồ sơ thành lập công ty TNHH 1 thành viên gồm Giấy đề nghị đăng ký doanh nghiệp, Điều lệ công ty và bản sao CCCD chủ sở hữu.",
            json.dumps([{"title": "Điều 24, Luật Doanh nghiệp 2020", "snippet": "Hồ sơ đăng ký doanh nghiệp công ty TNHH 1 thành viên...", "score": 0.94}], ensure_ascii=False),
            "like",
            _now(),
        ),
    ]
    conn.executemany(
        """
        INSERT INTO chat_messages (id, session_id, role, content, sources_json, feedback, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        messages,
    )


def seed_feedback(conn: sqlite3.Connection) -> None:
    count = conn.execute("SELECT COUNT(*) AS c FROM feedback_events").fetchone()["c"]
    if count > 0:
        return

    events = [
        ("fb-1", "user-1", "sess-2", "msg-2", "like", _now()),
    ]
    conn.executemany(
        "INSERT INTO feedback_events (id, user_id, session_id, message_id, feedback, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        events,
    )


def authenticate_user(username: str, password: str) -> Optional[Dict[str, Any]]:
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if row is None:
            return None
        user = _row_to_user(row)
        if verify_password(password, user["password_hash"]):
            return user
        return None
    finally:
        conn.close()


def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        return None if row is None else _row_to_user(row)
    finally:
        conn.close()


def list_users() -> List[Dict[str, Any]]:
    conn = _connect()
    try:
        rows = conn.execute("SELECT * FROM users ORDER BY created_at ASC").fetchall()
        return [_row_to_user(row) for row in rows]
    finally:
        conn.close()


def create_user(username: str, email: str, password: str, role: str = "user") -> Dict[str, Any]:
    conn = _connect()
    try:
        user_id = f"user-{uuid.uuid4().hex[:8]}"
        now = _now()
        conn.execute(
            """
            INSERT INTO users (id, username, email, password_hash, role, status, is_deleted, deleted_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, username, email, hash_password(password), role, "Active", 0, None, now, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return _row_to_user(row)
    finally:
        conn.close()


def update_user_status(username: str, status: str, is_deleted: bool, deleted_at: Optional[str] = None) -> None:
    conn = _connect()
    try:
        conn.execute(
            "UPDATE users SET status = ?, is_deleted = ?, deleted_at = ?, updated_at = ? WHERE username = ?",
            (status, 1 if is_deleted else 0, deleted_at, _now(), username),
        )
        conn.commit()
    finally:
        conn.close()


def create_chat_session(user_id: str, title: str) -> Dict[str, Any]:
    conn = _connect()
    try:
        session_id = f"sess-{uuid.uuid4().hex[:8]}"
        now = _now()
        conn.execute(
            "INSERT INTO chat_sessions (id, user_id, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (session_id, user_id, title, now, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM chat_sessions WHERE id = ?", (session_id,)).fetchone()
        return _row_to_session(row)
    finally:
        conn.close()


def list_chat_sessions(username: str) -> List[Dict[str, Any]]:
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT cs.id, cs.user_id, cs.title, cs.created_at, cs.updated_at
            FROM chat_sessions cs
            JOIN users u ON u.id = cs.user_id
            WHERE u.username = ?
            ORDER BY cs.created_at DESC
            """,
            (username,),
        ).fetchall()
        return [_row_to_session(row) for row in rows]
    finally:
        conn.close()


def get_chat_session(session_id: str) -> Dict[str, Any]:
    conn = _connect()
    try:
        session_row = conn.execute("SELECT * FROM chat_sessions WHERE id = ?", (session_id,)).fetchone()
        if not session_row:
            raise ValueError("Session not found")
        messages = conn.execute(
            "SELECT id, role, content, sources_json, feedback, created_at FROM chat_messages WHERE session_id = ? ORDER BY created_at ASC",
            (session_id,),
        ).fetchall()
        return {
            "session": _row_to_session(session_row),
            "messages": [
                {
                    "id": msg["id"],
                    "role": msg["role"],
                    "content": msg["content"],
                    "sources": json.loads(msg["sources_json"]) if msg["sources_json"] else [],
                    "feedback": msg["feedback"],
                    "created_at": msg["created_at"],
                }
                for msg in messages
            ],
        }
    finally:
        conn.close()


def delete_chat_session(session_id: str) -> None:
    conn = _connect()
    try:
        conn.execute("DELETE FROM chat_sessions WHERE id = ?", (session_id,))
        conn.commit()
    finally:
        conn.close()


def append_message(session_id: str, role: str, content: str, sources: Optional[List[Dict[str, Any]]] = None, feedback: Optional[str] = None) -> Dict[str, Any]:
    conn = _connect()
    try:
        message_id = f"msg-{uuid.uuid4().hex[:8]}"
        now = _now()
        conn.execute(
            "INSERT INTO chat_messages (id, session_id, role, content, sources_json, feedback, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (message_id, session_id, role, content, json.dumps(sources or [], ensure_ascii=False), feedback, now),
        )
        conn.execute("UPDATE chat_sessions SET updated_at = ? WHERE id = ?", (now, session_id))
        conn.commit()
        row = conn.execute("SELECT * FROM chat_messages WHERE id = ?", (message_id,)).fetchone()
        return {
            "id": row["id"],
            "role": row["role"],
            "content": row["content"],
            "sources": json.loads(row["sources_json"]) if row["sources_json"] else [],
            "feedback": row["feedback"],
            "created_at": row["created_at"],
        }
    finally:
        conn.close()


def update_chat_session_title(session_id: str, title: str) -> None:
    conn = _connect()
    try:
        conn.execute("UPDATE chat_sessions SET title = ?, updated_at = ? WHERE id = ?", (title, _now(), session_id))
        conn.commit()
    finally:
        conn.close()


def set_feedback(user_id: str, session_id: str, message_id: Optional[str], feedback: Optional[str]) -> None:
    conn = _connect()
    try:
        if feedback:
            conn.execute(
                "UPDATE chat_messages SET feedback = ? WHERE id = ? AND session_id = ?",
                (feedback, message_id, session_id),
            )
            if conn.total_changes:
                conn.execute(
                    "INSERT INTO feedback_events (id, user_id, session_id, message_id, feedback, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (f"fb-{uuid.uuid4().hex[:8]}", user_id, session_id, message_id, feedback, _now()),
                )
        else:
            conn.execute("UPDATE chat_messages SET feedback = NULL WHERE id = ? AND session_id = ?", (message_id, session_id))
        conn.commit()
    finally:
        conn.close()


def get_admin_stats() -> Dict[str, Any]:
    conn = _connect()
    try:
        user_count = conn.execute("SELECT COUNT(*) AS c FROM users WHERE role = 'user' AND (is_deleted = 0 OR is_deleted IS NULL)").fetchone()["c"]
        active_count = conn.execute("SELECT COUNT(*) AS c FROM users WHERE role = 'user' AND status = 'Active' AND (is_deleted = 0 OR is_deleted IS NULL)").fetchone()["c"]
        session_count = conn.execute("SELECT COUNT(*) AS c FROM chat_sessions").fetchone()["c"]
        feedback_count = conn.execute("SELECT COUNT(*) AS c FROM feedback_events").fetchone()["c"]
        return {
            "user_count": user_count,
            "active_count": active_count,
            "session_count": session_count,
            "feedback_count": feedback_count,
        }
    finally:
        conn.close()


def get_recent_activity(limit: int = 10) -> List[Dict[str, Any]]:
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT u.username, cm.content, cm.feedback, cm.created_at
            FROM chat_messages cm
            JOIN chat_sessions cs ON cs.id = cm.session_id
            JOIN users u ON u.id = cs.user_id
            ORDER BY cm.created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [
            {
                "username": row["username"],
                "content": row["content"],
                "feedback": row["feedback"] or "None",
                "created_at": row["created_at"],
            }
            for row in rows
        ]
    finally:
        conn.close()
