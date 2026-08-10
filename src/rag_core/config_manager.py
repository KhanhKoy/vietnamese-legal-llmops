from __future__ import annotations

import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = PROJECT_ROOT / "legal_chat.db"

ALLOWED_MODELS = {"gemini-2.5-flash", "gemini-2.5-pro", "gpt-4o-mini"}
DEFAULT_CONFIG = {
    "top_k": 5,
    "temperature": 0.2,
    "max_tokens": 1024,
    "model_name": "gemini-2.5-flash",
}

_CACHE_TTL_SECONDS = 4
_cache: Optional[Dict[str, Any]] = None
_cache_expires_at = 0.0
_cache_lock = threading.Lock()


def _is_postgres_connection(conn: Any) -> bool:
    return conn.__class__.__module__.startswith("psycopg")


def _sqlite_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _postgres_connection() -> Any:
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("PostgreSQL support requires psycopg3. Install it or unset DATABASE_URL/PGHOST.") from exc

    database_url = os.getenv("DATABASE_URL", "").strip()
    if database_url:
        return psycopg.connect(database_url, autocommit=False)

    return psycopg.connect(
        dbname=os.getenv("PGDATABASE", "postgres"),
        user=os.getenv("PGUSER", "postgres"),
        password=os.getenv("PGPASSWORD", "password"),
        host=os.getenv("PGHOST", "localhost"),
        port=int(os.getenv("PGPORT", "5432")),
        autocommit=False,
    )


def _uses_postgres() -> bool:
    return bool(
        os.getenv("DATABASE_URL", "").strip()
        or os.getenv("USE_PGVECTOR", "0").lower() in ("1", "true", "yes", "y")
    )


def _log_debug(message: str) -> None:
    if os.getenv("CONFIG_MANAGER_DEBUG", "0").lower() in ("1", "true", "yes", "y"):
        print(f"[ConfigManager] {message}")


def _get_db_connection() -> Any:
    if _uses_postgres():
        _log_debug(
            f"Connecting to Postgres config DB (DATABASE_URL set={bool(os.getenv('DATABASE_URL','').strip())}, USE_PGVECTOR={os.getenv('USE_PGVECTOR','0')})"
        )
        return _postgres_connection()

    _log_debug(f"Connecting to SQLite config DB at {DB_PATH}")
    return _sqlite_connection()


def _get_placeholder(conn: Any) -> str:
    return "%s" if _is_postgres_connection(conn) else "?"


def _initialize_schema(conn: Any) -> None:
    is_postgres = _is_postgres_connection(conn)
    if is_postgres:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS system_config (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                top_k INTEGER NOT NULL DEFAULT 5,
                temperature DOUBLE PRECISION NOT NULL DEFAULT 0.2,
                max_tokens INTEGER NOT NULL DEFAULT 1024,
                model_name VARCHAR(100) NOT NULL DEFAULT 'gemini-2.5-flash',
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
    else:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS system_config (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                top_k INTEGER NOT NULL DEFAULT 5,
                temperature REAL NOT NULL DEFAULT 0.2,
                max_tokens INTEGER NOT NULL DEFAULT 1024,
                model_name TEXT NOT NULL DEFAULT 'gemini-2.5-flash',
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )


def _load_config_from_db(conn: Any) -> Dict[str, Any]:
    cursor = conn.execute("SELECT id, top_k, temperature, max_tokens, model_name, updated_at FROM system_config WHERE id = 1")
    row = cursor.fetchone()
    if row is None:
        return DEFAULT_CONFIG.copy()

    return {
        "top_k": int(row["top_k"] if "top_k" in row.keys() else row[0]),
        "temperature": float(row["temperature"] if "temperature" in row.keys() else row[1]),
        "max_tokens": int(row["max_tokens"] if "max_tokens" in row.keys() else row[2]),
        "model_name": str(row["model_name"] if "model_name" in row.keys() else row[3]),
    }


def _cache_get() -> Optional[Dict[str, Any]]:
    global _cache, _cache_expires_at
    with _cache_lock:
        if _cache is None or time.time() >= _cache_expires_at:
            return None
        return dict(_cache)


def _cache_set(config: Dict[str, Any]) -> None:
    global _cache, _cache_expires_at
    with _cache_lock:
        _cache = dict(config)
        _cache_expires_at = time.time() + _CACHE_TTL_SECONDS


def _normalize_config(raw: Dict[str, Any]) -> Dict[str, Any]:
    config = {
        "top_k": int(raw.get("top_k", DEFAULT_CONFIG["top_k"])),
        "temperature": float(raw.get("temperature", DEFAULT_CONFIG["temperature"])),
        "max_tokens": int(raw.get("max_tokens", DEFAULT_CONFIG["max_tokens"])),
        "model_name": str(raw.get("model_name", DEFAULT_CONFIG["model_name"])),
    }

    if config["top_k"] <= 0:
        raise ValueError("top_k phải lớn hơn 0")
    if not (0.0 <= config["temperature"] <= 1.0):
        raise ValueError("temperature phải nằm trong khoảng 0.0 đến 1.0")
    if config["max_tokens"] <= 0:
        raise ValueError("max_tokens phải lớn hơn 0")
    if config["model_name"] not in ALLOWED_MODELS:
        raise ValueError(f"model_name phải thuộc whitelist: {', '.join(ALLOWED_MODELS)}")

    return config


def get_config() -> Dict[str, Any]:
    cached = _cache_get()
    if cached is not None:
        return cached

    try:
        conn = _get_db_connection()
        try:
            with conn:
                _initialize_schema(conn)
                config = _load_config_from_db(conn)
        finally:
            conn.close()
    except Exception as exc:
        print(f"[ConfigManager] Không lấy được cấu hình từ DB, dùng DEFAULT_CONFIG: {exc}")
        config = DEFAULT_CONFIG.copy()

    _cache_set(config)
    return config


def initialize_config() -> bool:
    try:
        conn = _get_db_connection()
        try:
            with conn:
                _initialize_schema(conn)
                if _is_postgres_connection(conn):
                    conn.execute(
                        """
                        INSERT INTO system_config (id, top_k, temperature, max_tokens, model_name)
                        VALUES (1, %s, %s, %s, %s)
                        ON CONFLICT (id) DO NOTHING;
                        """,
                        (DEFAULT_CONFIG["top_k"], DEFAULT_CONFIG["temperature"], DEFAULT_CONFIG["max_tokens"], DEFAULT_CONFIG["model_name"]),
                    )
                else:
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO system_config (id, top_k, temperature, max_tokens, model_name)
                        VALUES (1, ?, ?, ?, ?);
                        """,
                        (DEFAULT_CONFIG["top_k"], DEFAULT_CONFIG["temperature"], DEFAULT_CONFIG["max_tokens"], DEFAULT_CONFIG["model_name"]),
                    )
                row = conn.execute(
                    "SELECT top_k, temperature, max_tokens, model_name FROM system_config WHERE id = 1"
                ).fetchone()
                if row is not None:
                    config = {
                        "top_k": int(row["top_k"]),
                        "temperature": float(row["temperature"]),
                        "max_tokens": int(row["max_tokens"]),
                        "model_name": str(row["model_name"]),
                    }
                else:
                    config = DEFAULT_CONFIG.copy()
        finally:
            conn.close()
    except Exception as exc:
        print(f"[ConfigManager] initialize_config thất bại: {exc}")
        _cache_set(DEFAULT_CONFIG.copy())
        return False

    _cache_set(config)
    return True


def update_config(new_values: Dict[str, Any]) -> bool:
    try:
        current = get_config()
        merged = {
            "top_k": new_values.get("top_k", current["top_k"]),
            "temperature": new_values.get("temperature", current["temperature"]),
            "max_tokens": new_values.get("max_tokens", current["max_tokens"]),
            "model_name": new_values.get("model_name", current["model_name"]),
        }
        validated = _normalize_config(merged)

        conn = _get_db_connection()
        try:
            with conn:
                ph = _get_placeholder(conn)
                if _is_postgres_connection(conn):
                    conn.execute(
                        f"""
                        INSERT INTO system_config (id, top_k, temperature, max_tokens, model_name)
                        VALUES (1, {ph}, {ph}, {ph}, {ph})
                        ON CONFLICT (id) DO UPDATE SET
                            top_k = EXCLUDED.top_k,
                            temperature = EXCLUDED.temperature,
                            max_tokens = EXCLUDED.max_tokens,
                            model_name = EXCLUDED.model_name,
                            updated_at = CURRENT_TIMESTAMP;
                        """,
                        (validated["top_k"], validated["temperature"], validated["max_tokens"], validated["model_name"]),
                    )
                else:
                    conn.execute(
                        f"""
                        INSERT INTO system_config (id, top_k, temperature, max_tokens, model_name)
                        VALUES (1, {ph}, {ph}, {ph}, {ph})
                        ON CONFLICT(id) DO UPDATE SET
                            top_k = excluded.top_k,
                            temperature = excluded.temperature,
                            max_tokens = excluded.max_tokens,
                            model_name = excluded.model_name,
                            updated_at = CURRENT_TIMESTAMP;
                        """,
                        (validated["top_k"], validated["temperature"], validated["max_tokens"], validated["model_name"]),
                    )
        finally:
            conn.close()

        _cache_set(validated)
        return True
    except Exception as exc:
        print(f"[ConfigManager] update_config thất bại: {exc}")
        return False
