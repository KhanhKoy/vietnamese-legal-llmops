from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import psycopg

DATABASE_URL = os.environ.get("DATABASE_URL")


def _connect():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL not set for Postgres store")
    return psycopg.connect(DATABASE_URL)


def delete_chat_session(session_id: str) -> None:
    # Delete feedback and messages first, then the session, within a transaction
    conn = _connect()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM feedback_events WHERE session_id = %s", (session_id,))
                cur.execute("DELETE FROM chat_messages WHERE session_id = %s", (session_id,))
                cur.execute("DELETE FROM chat_sessions WHERE id = %s", (session_id,))
    finally:
        conn.close()

# Note: other storage functions (create_chat_session, append_message, etc.) can be
# implemented similarly if you plan to run the app against Postgres. This file only
# provides the minimal change required to safely delete chat sessions without FK errors.
