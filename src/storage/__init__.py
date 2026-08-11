from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv

load_dotenv()

_EXPORTS = (
    "initialize_database",
    "hash_password",
    "verify_password",
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
)


def _resolve_backend() -> str:
    explicit = (os.getenv("APP_DB_BACKEND") or "").strip().lower()
    if explicit in {"postgres", "postgresql", "pg"}:
        return "postgres"
    if explicit in {"sqlite", "local"}:
        return "sqlite"
    # Default: follow RAG cloud flag so AWS deploy with USE_PGVECTOR=true uses RDS for app too.
    use_pg = os.getenv("USE_PGVECTOR", "0").lower() in ("1", "true", "yes", "y")
    return "postgres" if use_pg else "sqlite"


def get_app_db_backend() -> str:
    return _resolve_backend()


def _backend_module() -> Any:
    if _resolve_backend() == "postgres":
        from . import postgres_store as store
    else:
        from . import sqlite_store as store
    return store


def __getattr__(name: str) -> Any:
    if name in _EXPORTS:
        return getattr(_backend_module(), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(list(globals().keys()) + list(_EXPORTS) + ["get_app_db_backend"]))


# Eagerly bind callables so `from src.storage import X` works at import time.
_store = _backend_module()
initialize_database = _store.initialize_database
hash_password = _store.hash_password
verify_password = _store.verify_password
authenticate_user = _store.authenticate_user
get_user_by_username = _store.get_user_by_username
list_users = _store.list_users
create_user = _store.create_user
update_user_status = _store.update_user_status
create_chat_session = _store.create_chat_session
list_chat_sessions = _store.list_chat_sessions
get_chat_session = _store.get_chat_session
delete_chat_session = _store.delete_chat_session
append_message = _store.append_message
update_chat_session_title = _store.update_chat_session_title
set_feedback = _store.set_feedback
get_admin_stats = _store.get_admin_stats
get_recent_activity = _store.get_recent_activity

