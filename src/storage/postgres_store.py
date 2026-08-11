from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import psycopg
from psycopg.rows import dict_row

from .sqlite_store import hash_password, verify_password

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS app_users (
    id TEXT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user',
    status TEXT NOT NULL DEFAULT 'Active',
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS app_chat_sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES app_users(id),
    title TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_app_chat_sessions_user
    ON app_chat_sessions (user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS app_chat_messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES app_chat_sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    sources_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    feedback TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_app_chat_messages_session
    ON app_chat_messages (session_id, created_at ASC);

CREATE TABLE IF NOT EXISTS app_feedback_events (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES app_users(id),
    session_id TEXT NOT NULL REFERENCES app_chat_sessions(id),
    message_id TEXT,
    feedback TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_app_feedback_events_user
    ON app_feedback_events (user_id, created_at DESC);
"""


def _connect() -> psycopg.Connection:
    sslmode = os.getenv("PGSSLMODE", "require")
    connect_timeout = int(os.getenv("PG_CONNECT_TIMEOUT_SECONDS", "10"))
    return psycopg.connect(
        host=os.getenv("PGHOST", "localhost"),
        port=os.getenv("PGPORT", "5432"),
        user=os.getenv("PGUSER", "postgres"),
        password=os.getenv("PGPASSWORD", "password"),
        dbname=os.getenv("PGDATABASE", "postgres"),
        sslmode=sslmode,
        connect_timeout=connect_timeout,
        row_factory=dict_row,
        autocommit=False,
    )


def _fmt_ts(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    return str(value)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _row_to_user(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "username": row["username"],
        "email": row["email"],
        "password_hash": row["password_hash"],
        "role": row["role"],
        "status": row["status"],
        "is_deleted": bool(row["is_deleted"]),
        "deleted_at": _fmt_ts(row["deleted_at"]) if row["deleted_at"] else None,
        "created_at": _fmt_ts(row["created_at"]),
        "updated_at": _fmt_ts(row["updated_at"]),
    }


def _row_to_session(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "title": row["title"],
        "created_at": _fmt_ts(row["created_at"]),
        "updated_at": _fmt_ts(row["updated_at"]),
    }


def _parse_sources(value: Any) -> List[Dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        return json.loads(value) if value else []
    return list(value)


def initialize_database() -> None:
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(_SCHEMA_SQL)
        conn.commit()
        seed_users(conn)
        seed_sessions(conn)
        seed_messages(conn)
        seed_feedback(conn)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def seed_users(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS c FROM app_users")
        if cur.fetchone()["c"] > 0:
            return

        now = _now()
        users = [
            ("user-1", "user1", "user1@phapluat.vn", hash_password("password123"), "user", "Active", False, None, now, now),
            ("admin-1", "admin", "admin@phapluat.vn", hash_password("admin123"), "admin", "Active", False, None, now, now),
            ("user-2", "minh_tran", "minh.tran@lawfirm.vn", hash_password("password123"), "user", "Active", False, None, now, now),
            ("user-3", "hoang_nam", "nam.hoang@company.com", hash_password("password123"), "user", "Active", False, None, now, now),
            ("user-4", "lan_anh", "lananh.legal@gmail.com", hash_password("password123"), "user", "Active", False, None, now, now),
        ]
        cur.executemany(
            """
            INSERT INTO app_users
                (id, username, email, password_hash, role, status, is_deleted, deleted_at, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            users,
        )


def seed_sessions(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS c FROM app_chat_sessions")
        if cur.fetchone()["c"] > 0:
            return

        now = _now()
        sessions = [
            ("sess-1", "user-1", "Thời gian thử việc Luật Lao động 2019", now, now),
            ("sess-2", "user-1", "Thủ tục thành lập công ty TNHH 1 thành viên", now, now),
        ]
        cur.executemany(
            """
            INSERT INTO app_chat_sessions (id, user_id, title, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s)
            """,
            sessions,
        )


def seed_messages(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS c FROM app_chat_messages")
        if cur.fetchone()["c"] > 0:
            return

        now = _now()
        messages = [
            (
                "msg-1",
                "sess-1",
                "assistant",
                "Xin chào! Tôi là Trợ lý Pháp luật Việt Nam. Tôi có thể hỗ trợ bạn tra cứu Bộ luật Dân sự, Luật Lao động, Bộ luật Hình sự, Luật Doanh nghiệp và nhiều văn bản pháp luật khác.",
                [
                    {
                        "title": "Điều 1, Bộ luật Dân sự 2015",
                        "snippet": "Bộ luật này quy định địa vị pháp lý, chuẩn mực pháp lý cho cách ứng xử của cá nhân, pháp nhân...",
                        "score": 0.95,
                    }
                ],
                None,
                now,
            ),
            (
                "msg-2",
                "sess-2",
                "assistant",
                "Chào bạn! Hồ sơ thành lập công ty TNHH 1 thành viên gồm Giấy đề nghị đăng ký doanh nghiệp, Điều lệ công ty và bản sao CCCD chủ sở hữu.",
                [
                    {
                        "title": "Điều 24, Luật Doanh nghiệp 2020",
                        "snippet": "Hồ sơ đăng ký doanh nghiệp công ty TNHH 1 thành viên...",
                        "score": 0.94,
                    }
                ],
                "like",
                now,
            ),
        ]
        cur.executemany(
            """
            INSERT INTO app_chat_messages
                (id, session_id, role, content, sources_json, feedback, created_at)
            VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s)
            """,
            [
                (m[0], m[1], m[2], m[3], json.dumps(m[4], ensure_ascii=False), m[5], m[6])
                for m in messages
            ],
        )


def seed_feedback(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS c FROM app_feedback_events")
        if cur.fetchone()["c"] > 0:
            return

        now = _now()
        cur.execute(
            """
            INSERT INTO app_feedback_events
                (id, user_id, session_id, message_id, feedback, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            ("fb-1", "user-1", "sess-2", "msg-2", "like", now),
        )


def authenticate_user(username: str, password: str) -> Optional[Dict[str, Any]]:
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM app_users WHERE username = %s", (username,))
            row = cur.fetchone()
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
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM app_users WHERE username = %s", (username,))
            row = cur.fetchone()
        return None if row is None else _row_to_user(row)
    finally:
        conn.close()


def list_users() -> List[Dict[str, Any]]:
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM app_users ORDER BY created_at ASC")
            rows = cur.fetchall()
        return [_row_to_user(row) for row in rows]
    finally:
        conn.close()


def create_user(username: str, email: str, password: str, role: str = "user") -> Dict[str, Any]:
    conn = _connect()
    try:
        user_id = f"user-{uuid.uuid4().hex[:8]}"
        now = _now()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO app_users
                    (id, username, email, password_hash, role, status, is_deleted, deleted_at, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (user_id, username, email, hash_password(password), role, "Active", False, None, now, now),
            )
            cur.execute("SELECT * FROM app_users WHERE id = %s", (user_id,))
            row = cur.fetchone()
        conn.commit()
        return _row_to_user(row)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def update_user_status(username: str, status: str, is_deleted: bool, deleted_at: Optional[str] = None) -> None:
    conn = _connect()
    try:
        deleted_ts = None
        if deleted_at:
            deleted_ts = deleted_at
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE app_users
                SET status = %s, is_deleted = %s, deleted_at = %s, updated_at = %s
                WHERE username = %s
                """,
                (status, is_deleted, deleted_ts, _now(), username),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def create_chat_session(user_id: str, title: str) -> Dict[str, Any]:
    conn = _connect()
    try:
        session_id = f"sess-{uuid.uuid4().hex[:8]}"
        now = _now()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO app_chat_sessions (id, user_id, title, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (session_id, user_id, title, now, now),
            )
            cur.execute("SELECT * FROM app_chat_sessions WHERE id = %s", (session_id,))
            row = cur.fetchone()
        conn.commit()
        return _row_to_session(row)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def list_chat_sessions(username: str) -> List[Dict[str, Any]]:
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT cs.id, cs.user_id, cs.title, cs.created_at, cs.updated_at
                FROM app_chat_sessions cs
                JOIN app_users u ON u.id = cs.user_id
                WHERE u.username = %s
                ORDER BY cs.created_at DESC
                """,
                (username,),
            )
            rows = cur.fetchall()
        return [_row_to_session(row) for row in rows]
    finally:
        conn.close()


def get_chat_session(session_id: str) -> Dict[str, Any]:
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM app_chat_sessions WHERE id = %s", (session_id,))
            session_row = cur.fetchone()
            if not session_row:
                raise ValueError("Session not found")
            cur.execute(
                """
                SELECT id, role, content, sources_json, feedback, created_at
                FROM app_chat_messages
                WHERE session_id = %s
                ORDER BY created_at ASC
                """,
                (session_id,),
            )
            messages = cur.fetchall()
        return {
            "session": _row_to_session(session_row),
            "messages": [
                {
                    "id": msg["id"],
                    "role": msg["role"],
                    "content": msg["content"],
                    "sources": _parse_sources(msg["sources_json"]),
                    "feedback": msg["feedback"],
                    "created_at": _fmt_ts(msg["created_at"]),
                }
                for msg in messages
            ],
        }
    finally:
        conn.close()


def delete_chat_session(session_id: str) -> None:
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM app_chat_sessions WHERE id = %s", (session_id,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def append_message(
    session_id: str,
    role: str,
    content: str,
    sources: Optional[List[Dict[str, Any]]] = None,
    feedback: Optional[str] = None,
) -> Dict[str, Any]:
    conn = _connect()
    try:
        message_id = f"msg-{uuid.uuid4().hex[:8]}"
        now = _now()
        sources_payload = json.dumps(sources or [], ensure_ascii=False)
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO app_chat_messages
                    (id, session_id, role, content, sources_json, feedback, created_at)
                VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s)
                """,
                (message_id, session_id, role, content, sources_payload, feedback, now),
            )
            cur.execute(
                "UPDATE app_chat_sessions SET updated_at = %s WHERE id = %s",
                (now, session_id),
            )
            cur.execute("SELECT * FROM app_chat_messages WHERE id = %s", (message_id,))
            row = cur.fetchone()
        conn.commit()
        return {
            "id": row["id"],
            "role": row["role"],
            "content": row["content"],
            "sources": _parse_sources(row["sources_json"]),
            "feedback": row["feedback"],
            "created_at": _fmt_ts(row["created_at"]),
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def update_chat_session_title(session_id: str, title: str) -> None:
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE app_chat_sessions SET title = %s, updated_at = %s WHERE id = %s",
                (title, _now(), session_id),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def set_feedback(user_id: str, session_id: str, message_id: Optional[str], feedback: Optional[str]) -> None:
    conn = _connect()
    try:
        with conn.cursor() as cur:
            if feedback:
                cur.execute(
                    "UPDATE app_chat_messages SET feedback = %s WHERE id = %s AND session_id = %s",
                    (feedback, message_id, session_id),
                )
                if cur.rowcount:
                    cur.execute(
                        """
                        INSERT INTO app_feedback_events
                            (id, user_id, session_id, message_id, feedback, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        (f"fb-{uuid.uuid4().hex[:8]}", user_id, session_id, message_id, feedback, _now()),
                    )
            else:
                cur.execute(
                    "UPDATE app_chat_messages SET feedback = NULL WHERE id = %s AND session_id = %s",
                    (message_id, session_id),
                )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_admin_stats() -> Dict[str, Any]:
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) AS c FROM app_users
                WHERE role = 'user' AND (is_deleted = FALSE OR is_deleted IS NULL)
                """
            )
            user_count = cur.fetchone()["c"]
            cur.execute(
                """
                SELECT COUNT(*) AS c FROM app_users
                WHERE role = 'user' AND status = 'Active' AND (is_deleted = FALSE OR is_deleted IS NULL)
                """
            )
            active_count = cur.fetchone()["c"]
            cur.execute("SELECT COUNT(*) AS c FROM app_chat_sessions")
            session_count = cur.fetchone()["c"]
            cur.execute("SELECT COUNT(*) AS c FROM app_feedback_events")
            feedback_count = cur.fetchone()["c"]
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
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT u.username, cm.content, cm.feedback, cm.created_at
                FROM app_chat_messages cm
                JOIN app_chat_sessions cs ON cs.id = cm.session_id
                JOIN app_users u ON u.id = cs.user_id
                ORDER BY cm.created_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            rows = cur.fetchall()
        return [
            {
                "username": row["username"],
                "content": row["content"],
                "feedback": row["feedback"] or "None",
                "created_at": _fmt_ts(row["created_at"]),
            }
            for row in rows
        ]
    finally:
        conn.close()


__all__ = [
    "hash_password",
    "verify_password",
    "initialize_database",
    "authenticate_user",
    "get_user_by_username",
    "list_users",
    "create_user",
    "update_user_status",
    "create_chat_session",
    "list_chat_sessions",
    "get_chat_session",
    "delete_chat_session",
    "append_message",
    "update_chat_session_title",
    "set_feedback",
    "get_admin_stats",
    "get_recent_activity",
]
