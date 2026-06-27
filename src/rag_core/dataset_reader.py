from __future__ import annotations

import gc
import json
import os
import sqlite3
import tempfile
from dataclasses import dataclass
from typing import Any, Dict, Iterator, List, Optional

from .chunking import html_to_text
from .config import get_settings


METADATA_CONFIG = "metadata"
CONTENT_CONFIG = "content"
METADATA_PARQUET_PATH = os.getenv("HF_METADATA_PARQUET_PATH", "data/metadata.parquet")
CONTENT_PARQUET_PATH = os.getenv("HF_CONTENT_PARQUET_PATH", "data/content.parquet")
EXPIRED_FULL_STATUS = "Hết hiệu lực toàn bộ"

METADATA_COLUMNS = {
    "id",
    "title",
    "so_ky_hieu",
    "ngay_ban_hanh",
    "loai_van_ban",
    "co_quan_ban_hanh",
    "tinh_trang_hieu_luc",
}


@dataclass
class LegalDocument:
    document_id: str
    text: str
    metadata: Dict[str, Any]


def _normalize_id(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _normalize_text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _is_expired_full(row: Dict[str, Any]) -> bool:
    status = _normalize_text(row.get("tinh_trang_hieu_luc")).casefold()
    return status == EXPIRED_FULL_STATUS.casefold()


def _parquet_path_for_config(config_name: str) -> str:
    if config_name == METADATA_CONFIG:
        return METADATA_PARQUET_PATH
    if config_name == CONTENT_CONFIG:
        return CONTENT_PARQUET_PATH
    raise ValueError(f"Unsupported dataset config: {config_name}")


def _iter_parquet_config(
    config_name: str,
    columns: Optional[List[str]] = None,
    batch_size: int = 1024,
) -> Iterator[Dict[str, Any]]:
    """
    Read HuggingFace dataset parquet files directly.

    This avoids `datasets.load_dataset()`, which is currently causing a native
    Windows access violation in this environment when iterating the metadata
    split. We still process rows in small Arrow batches and never convert the
    full dataset to Pandas.
    """
    settings = get_settings()
    parquet_path = _parquet_path_for_config(config_name)

    print(
        f"[dataset_reader] Downloading parquet config={config_name}, path={parquet_path}...",
        flush=True,
    )
    from huggingface_hub import hf_hub_download
    import pyarrow.parquet as pq

    local_path = hf_hub_download(
        repo_id=settings.hf_dataset_name,
        repo_type="dataset",
        filename=parquet_path,
    )
    print(
        f"[dataset_reader] Parquet ready for config={config_name}: {local_path}",
        flush=True,
    )

    parquet_file = pq.ParquetFile(local_path, memory_map=False)
    available_columns = set(parquet_file.schema.names)
    selected_columns = (
        [column for column in columns if column in available_columns]
        if columns
        else None
    )

    if columns:
        missing = sorted(set(columns) - available_columns)
        if missing:
            print(
                f"[dataset_reader] Warning: missing columns in {config_name}: {missing}",
                flush=True,
            )

    print(
        f"[dataset_reader] Iterating parquet config={config_name}, columns={selected_columns or 'ALL'}...",
        flush=True,
    )
    for batch in parquet_file.iter_batches(
        batch_size=batch_size,
        columns=selected_columns,
    ):
        data = batch.to_pydict()
        row_count = len(next(iter(data.values()))) if data else 0
        for index in range(row_count):
            yield {key: values[index] for key, values in data.items()}


def iter_metadata_rows(
    limit: Optional[int] = None,
    filter_expired: bool = True,
) -> Iterator[Dict[str, Any]]:
    yielded = 0

    for row in _iter_parquet_config(
        METADATA_CONFIG,
        columns=sorted(METADATA_COLUMNS),
        batch_size=2048,
    ):
        doc_id = _normalize_id(row.get("id"))
        if not doc_id:
            continue

        if filter_expired and _is_expired_full(row):
            continue

        metadata = {
            key: row.get(key)
            for key in METADATA_COLUMNS
            if key in row
        }
        metadata["id"] = doc_id

        yield metadata
        yielded += 1

        if limit is not None and yielded >= limit:
            break


def _build_metadata_db(
    metadata_limit: Optional[int] = None,
    filter_expired: bool = True,
) -> str:
    print("[dataset_reader] Loading metadata into temporary SQLite...", flush=True)
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    print(f"[dataset_reader] Metadata temp DB: {tmp.name}", flush=True)

    print("[dataset_reader] Opening SQLite connection...", flush=True)
    conn = sqlite3.connect(tmp.name)
    print("[dataset_reader] SQLite connection opened.", flush=True)
    conn.execute("PRAGMA synchronous=OFF;")
    conn.execute("PRAGMA journal_mode=MEMORY;")
    conn.execute("PRAGMA temp_store=MEMORY;")
    conn.execute(
        """
        CREATE TABLE meta (
            id TEXT PRIMARY KEY,
            payload TEXT NOT NULL
        )
        """
    )
    print("[dataset_reader] Metadata table ready. Start iterating metadata rows...", flush=True)

    batch: list[tuple[str, str]] = []
    inserted = 0
    for row in iter_metadata_rows(
        limit=metadata_limit,
        filter_expired=filter_expired,
    ):
        doc_id = _normalize_id(row.get("id"))
        payload = {k: v for k, v in row.items() if k != "id"}
        batch.append((doc_id, json.dumps(payload, ensure_ascii=False)))

        if len(batch) >= 5000:
            conn.executemany(
                "INSERT OR REPLACE INTO meta (id, payload) VALUES (?, ?)",
                batch,
            )
            inserted += len(batch)
            print(f"[dataset_reader] Metadata rows loaded: {inserted}", flush=True)
            batch.clear()

    if batch:
        conn.executemany(
            "INSERT OR REPLACE INTO meta (id, payload) VALUES (?, ?)",
            batch,
        )
        inserted += len(batch)

    conn.commit()
    conn.close()
    print(f"[dataset_reader] Metadata SQLite completed: {inserted} rows.", flush=True)
    return tmp.name


def iter_content_rows(limit: Optional[int] = None) -> Iterator[Dict[str, Any]]:
    yielded = 0

    for row in _iter_parquet_config(
        CONTENT_CONFIG,
        columns=["id", "content_html"],
        batch_size=64,
    ):
        doc_id = _normalize_id(row.get("id"))
        content_html = row.get("content_html")

        if not doc_id or not content_html:
            continue

        yield {
            "id": doc_id,
            "content_html": content_html,
        }
        yielded += 1

        if limit is not None and yielded >= limit:
            break


def iter_documents(
    metadata_limit: Optional[int] = None,
    content_limit: Optional[int] = None,
    content_batch_size: int = 64,
    filter_expired: bool = True,
) -> Iterator[LegalDocument]:
    _ = content_batch_size
    meta_db_path = _build_metadata_db(
        metadata_limit=metadata_limit,
        filter_expired=filter_expired,
    )

    meta_conn: Optional[sqlite3.Connection] = None
    try:
        meta_conn = sqlite3.connect(meta_db_path)
        meta_conn.execute("PRAGMA synchronous=OFF;")
        meta_conn.execute("PRAGMA journal_mode=MEMORY;")

        print("[dataset_reader] Iterating content and joining by id...", flush=True)
        for content_row in iter_content_rows(limit=content_limit):
            doc_id = _normalize_id(content_row.get("id"))
            if not doc_id:
                continue

            row = meta_conn.execute(
                "SELECT payload FROM meta WHERE id = ?",
                (doc_id,),
            ).fetchone()
            if row is None:
                continue

            metadata: Dict[str, Any] = json.loads(row[0])
            metadata["id"] = doc_id

            text = html_to_text(_normalize_text(content_row.get("content_html")))
            if not text:
                continue

            yield LegalDocument(
                document_id=doc_id,
                text=text,
                metadata=metadata,
            )
    finally:
        if meta_conn is not None:
            meta_conn.close()
        try:
            os.unlink(meta_db_path)
        except OSError:
            pass
        gc.collect()


def load_documents(
    metadata_limit: Optional[int] = None,
    content_limit: Optional[int] = None,
    content_batch_size: int = 64,
    filter_expired: bool = True,
) -> List[LegalDocument]:
    return list(
        iter_documents(
            metadata_limit=metadata_limit,
            content_limit=content_limit,
            content_batch_size=content_batch_size,
            filter_expired=filter_expired,
        )
    )


def documents_to_dicts(documents: List[LegalDocument]) -> List[Dict[str, Any]]:
    return [
        {
            "document_id": doc.document_id,
            "text": doc.text,
            "metadata": doc.metadata,
        }
        for doc in documents
    ]
