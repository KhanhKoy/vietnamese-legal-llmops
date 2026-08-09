"""Initialize app DB (Postgres on RDS or local SQLite) and print basic stats."""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.storage import get_admin_stats, get_app_db_backend, initialize_database, list_users


if __name__ == "__main__":
    backend = get_app_db_backend()
    print(f"APP_DB_BACKEND resolved to: {backend}")
    initialize_database()
    print("Database initialized successfully.")
    print("Users:", len(list_users()))
    print("Stats:", get_admin_stats())
