"""Lightweight PostgreSQL operations for the document administration API."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any


class DocumentAdminStore:
    """Manage document metadata without loading the embedding model or vector index."""

    def __init__(self) -> None:
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:  # pragma: no cover - validated during deployment
            raise RuntimeError("Cần cài psycopg[binary] để dùng trang quản trị") from exc

        connect_options = {
            "autocommit": False,
            "connect_timeout": int(os.getenv("DB_CONNECT_TIMEOUT_SECONDS", "10")),
            "options": (
                "-c statement_timeout="
                + str(int(os.getenv("PG_QUERY_TIMEOUT_MS", "10000")))
            ),
            "row_factory": dict_row,
        }
        database_url = os.getenv("DATABASE_URL", "").strip()
        if database_url:
            self._conn = psycopg.connect(database_url, **connect_options)
        else:
            self._conn = psycopg.connect(
                host=os.getenv("PGHOST", "localhost"),
                port=os.getenv("PGPORT", "5432"),
                dbname=os.getenv("PGDATABASE", "postgres"),
                user=os.getenv("PGUSER", "postgres"),
                password=os.getenv("PGPASSWORD", ""),
                sslmode=os.getenv("PGSSLMODE", "require"),
                **connect_options,
            )

    def list_documents(self, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        sql = """
            SELECT DISTINCT ON (document_id)
                document_id,
                metadata_json,
                COUNT(*) OVER (PARTITION BY document_id) AS chunk_count
            FROM legal_chunks
            WHERE NOT (metadata_json ? 'deleted_at')
            ORDER BY document_id, id ASC
            LIMIT %s OFFSET %s
        """
        try:
            with self._conn.cursor() as cursor:
                cursor.execute(sql, (max(1, min(limit, 200)), max(0, offset)))
                rows = cursor.fetchall()
            self._conn.commit()
            return [self._normalise_row(row) for row in rows]
        except Exception:
            self._conn.rollback()
            raise

    def update_document_info(
        self,
        document_id: str,
        tinh_trang_hieu_luc: str | None = None,
        ngay_het_hieu_luc: str | None = None,
        is_procedural_law: bool | None = None,
    ) -> bool:
        changes = {
            key: value
            for key, value in {
                "tinh_trang_hieu_luc": tinh_trang_hieu_luc,
                "ngay_het_hieu_luc": ngay_het_hieu_luc,
                "is_procedural_law": is_procedural_law,
            }.items()
            if value is not None
        }
        if not changes:
            return False

        try:
            with self._conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE legal_chunks
                    SET metadata_json = COALESCE(metadata_json, '{}'::jsonb)
                        || %s::jsonb || %s::jsonb
                    WHERE document_id = %s
                      AND NOT (metadata_json ? 'deleted_at')
                    """,
                    (
                        json.dumps(changes, ensure_ascii=False),
                        json.dumps(
                            {"admin_updated_at": datetime.now(timezone.utc).isoformat()},
                            ensure_ascii=False,
                        ),
                        document_id,
                    ),
                )
                updated = cursor.rowcount > 0
            self._conn.commit()
            return updated
        except Exception:
            self._conn.rollback()
            raise

    def delete_document(self, document_id: str) -> bool:
        deleted_at = datetime.now(timezone.utc).isoformat()
        try:
            with self._conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE legal_chunks
                    SET metadata_json = COALESCE(metadata_json, '{}'::jsonb)
                        || jsonb_build_object(
                            'deleted_at', %s,
                            'tinh_trang_hieu_luc', 'Đã ẩn'
                        )
                    WHERE document_id = %s
                      AND NOT (metadata_json ? 'deleted_at')
                    """,
                    (deleted_at, document_id),
                )
                deleted = cursor.rowcount > 0
            self._conn.commit()
            return deleted
        except Exception:
            self._conn.rollback()
            raise

    @staticmethod
    def _normalise_row(row: dict[str, Any]) -> dict[str, Any]:
        metadata = row.get("metadata_json") or {}
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except json.JSONDecodeError:
                metadata = {}
        return {
            "document_id": row.get("document_id"),
            "metadata": metadata,
            "chunk_count": int(row.get("chunk_count") or 0),
        }
