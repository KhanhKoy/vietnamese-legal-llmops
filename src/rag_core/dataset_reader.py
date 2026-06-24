from __future__ import annotations

import gc
import sqlite3
import tempfile
from dataclasses import dataclass
from typing import Any, Dict, Iterator, List, Optional

import fsspec
import pyarrow.parquet as pq
from datasets import load_dataset

from .config import get_settings


@dataclass
class LegalDocument:
    document_id: str
    text: str
    metadata: Dict[str, Any]


def _normalize_id(value: Any) -> str:
    return "" if value is None else str(value)


def iter_metadata_rows(limit: Optional[int] = None) -> Iterator[Dict[str, Any]]:
    """
    Đọc metadata theo kiểu streaming để tránh load toàn bộ vào RAM.
    """
    settings = get_settings()
    dataset = load_dataset(
        settings.hf_dataset_name,
        settings.hf_metadata_config,
        streaming=True,
    )
    split_name = "data" if "data" in dataset else next(iter(dataset.keys()))

    count = 0
    for row in dataset[split_name]:
        yield dict(row)
        count += 1
        if limit is not None and count >= limit:
            break


def _build_metadata_db(
    metadata_limit: Optional[int] = None,
) -> str:
    """
    Stream tất cả metadata vào một SQLite tạm thời trên ổ cứng.
    Trả về đường dẫn file .db để dùng cho tra cứu.

    Giải pháp này chỉ dùng O(1) RAM vì từng row được insert ngay lập tức
    xuống SQLite, không giữ gì trong Python heap.
    """
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()

    conn = sqlite3.connect(tmp.name)
    conn.execute("PRAGMA synchronous=OFF;")
    conn.execute("PRAGMA journal_mode=MEMORY;")
    conn.execute(
        """
        CREATE TABLE meta (
            id TEXT PRIMARY KEY,
            payload TEXT NOT NULL
        )
        """
    )

    import json

    batch: list[tuple[str, str]] = []
    for row in iter_metadata_rows(limit=metadata_limit):
        doc_id = _normalize_id(row.get("id"))
        if not doc_id:
            continue
        # Strip id from payload to avoid duplicating key
        payload = {k: v for k, v in row.items() if k != "id"}
        batch.append((doc_id, json.dumps(payload, ensure_ascii=False)))

        if len(batch) >= 5000:
            conn.executemany(
                "INSERT OR REPLACE INTO meta (id, payload) VALUES (?, ?)", batch
            )
            batch.clear()

    if batch:
        conn.executemany(
            "INSERT OR REPLACE INTO meta (id, payload) VALUES (?, ?)", batch
        )

    conn.commit()
    conn.close()
    return tmp.name


def iter_content_rows(
    limit: Optional[int] = None,
    batch_size: int = 64,
) -> Iterator[Dict[str, Any]]:
    """
    Đọc content.parquet theo batch nhỏ, không dùng pandas để giảm RAM.
    """
    settings = get_settings()

    with fsspec.open(settings.hf_content_parquet_url, mode="rb") as f:
        parquet_file = pq.ParquetFile(f)

        yielded = 0
        for batch in parquet_file.iter_batches(
            batch_size=batch_size,
            columns=["id", "content"],
        ):
            data = batch.to_pydict()
            ids = data.get("id", [])
            contents = data.get("content", [])

            for doc_id, content in zip(ids, contents):
                yield {"id": doc_id, "content": content}
                yielded += 1
                if limit is not None and yielded >= limit:
                    return


def iter_documents(
    metadata_limit: Optional[int] = None,
    content_limit: Optional[int] = None,
    content_batch_size: int = 64,
) -> Iterator[LegalDocument]:
    """
    Đọc documents bằng cách join metadata + content trên ổ cứng.

    Metadata được stream vào một SQLite tạm trước, sau đó content được
    duyệt và tra metadata tương ứng qua lookup trên SQLite. Phương pháp này
    tránh hoàn toàn OOM vì không có dict nào giữ toàn bộ dữ liệu trong RAM.
    """
    import json


    # --- Giai đoạn 1: load metadata vào file SQLite tạm (streaming) ---
    meta_db_path = _build_metadata_db(metadata_limit=metadata_limit)

    try:
        meta_conn = sqlite3.connect(meta_db_path)
        meta_conn.execute("PRAGMA synchronous=OFF;")
        meta_conn.execute("PRAGMA journal_mode=MEMORY;")

        # --- Giai đoạn 2: duyệt content, lookup metadata từ SQLite ---
        for content_row in iter_content_rows(
            limit=content_limit, batch_size=content_batch_size
        ):
            doc_id = _normalize_id(content_row.get("id"))
            content = content_row.get("content", "")

            if not doc_id or not content:
                continue

            # Lookup metadata
            row = meta_conn.execute(
                "SELECT payload FROM meta WHERE id = ?", (doc_id,)
            ).fetchone()
            metadata: Dict[str, Any] = json.loads(row[0]) if row else {}

            # Merge any extra fields from content row (excluding id/content)
            extra = {
                k: v
                for k, v in content_row.items()
                if k not in {"id", "content"}
            }
            metadata.update(extra)

            yield LegalDocument(
                document_id=doc_id,
                text=str(content),
                metadata=metadata,
            )

        meta_conn.close()
    finally:
        # --- Giai đoạn 3: dọn dẹp file tạm ---
        import os

        try:
            os.unlink(meta_db_path)
        except OSError:
            pass
        gc.collect()


def load_documents(
    metadata_limit: Optional[int] = None,
    content_limit: Optional[int] = None,
    content_batch_size: int = 64,
) -> List[LegalDocument]:
    return list(
        iter_documents(
            metadata_limit=metadata_limit,
            content_limit=content_limit,
            content_batch_size=content_batch_size,
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
