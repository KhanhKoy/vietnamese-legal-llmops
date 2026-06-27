from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

from tqdm import tqdm

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from rag_core.chunking import html_to_text, split_text  # noqa: E402


DEFAULT_OUTPUT = PROJECT_ROOT / "models" / "indexing" / "chunks.sqlite3"
DATASET_NAME = "th1nhng0/vietnamese-legal-documents"
METADATA_CONFIG = "metadata"
CONTENT_CONFIG = "content"
METADATA_PARQUET_PATH = "data/metadata.parquet"
CONTENT_PARQUET_PATH = "data/content.parquet"
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Phase A: dataset parquet -> metadata join -> HTML cleaning -> chunks checkpoint."
    )
    parser.add_argument("--dataset-name", default=DATASET_NAME)
    parser.add_argument("--metadata-limit", type=int, default=None)
    parser.add_argument("--content-limit", type=int, default=None)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--metadata-batch-size", type=int, default=2048)
    parser.add_argument("--content-batch-size", type=int, default=16)
    parser.add_argument("--chunk-batch-size", type=int, default=1000)
    parser.add_argument(
        "--keep-expired",
        action="store_true",
        help="Keep documents where tinh_trang_hieu_luc is 'Hết hiệu lực toàn bộ'.",
    )
    return parser.parse_args()


def normalize_id(value: Any) -> str:
    return "" if value is None else str(value).strip()


def normalize_text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def is_expired_full(row: Dict[str, Any]) -> bool:
    status = normalize_text(row.get("tinh_trang_hieu_luc")).casefold()
    return status == EXPIRED_FULL_STATUS.casefold()


def parquet_path_for_config(config_name: str) -> str:
    if config_name == METADATA_CONFIG:
        return METADATA_PARQUET_PATH
    if config_name == CONTENT_CONFIG:
        return CONTENT_PARQUET_PATH
    raise ValueError(f"Unsupported config: {config_name}")


def iter_hf_parquet_config(
    dataset_name: str,
    config_name: str,
    columns: list[str],
    batch_size: int,
) -> Iterator[Dict[str, Any]]:
    parquet_path = parquet_path_for_config(config_name)
    print(
        f"[phase_a] Loading parquet dataset={dataset_name}, config={config_name}, path={parquet_path}",
        flush=True,
    )
    from huggingface_hub import hf_hub_download
    import pyarrow.parquet as pq

    local_path = hf_hub_download(
        repo_id=dataset_name,
        repo_type="dataset",
        filename=parquet_path,
    )
    print(f"[phase_a] Local parquet: {local_path}", flush=True)

    parquet_file = pq.ParquetFile(local_path, memory_map=False)
    available_columns = set(parquet_file.schema.names)
    selected_columns = [column for column in columns if column in available_columns]
    missing_columns = sorted(set(columns) - available_columns)
    if missing_columns:
        print(
            f"[phase_a] Warning: missing columns in {config_name}: {missing_columns}",
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


def create_metadata_db() -> tuple[str, sqlite3.Connection]:
    tmp = tempfile.NamedTemporaryFile(suffix=".metadata.sqlite3", delete=False)
    tmp.close()
    conn = sqlite3.connect(tmp.name)
    conn.execute("PRAGMA synchronous=OFF;")
    conn.execute("PRAGMA journal_mode=MEMORY;")
    conn.execute("PRAGMA temp_store=MEMORY;")
    conn.execute(
        """
        CREATE TABLE metadata (
            id TEXT PRIMARY KEY,
            payload TEXT NOT NULL
        )
        """
    )
    return tmp.name, conn


def build_metadata_lookup(
    dataset_name: str,
    metadata_limit: Optional[int],
    keep_expired: bool,
    batch_size: int,
) -> str:
    db_path, conn = create_metadata_db()
    rows: list[tuple[str, str]] = []
    inserted = 0

    iterator = iter_hf_parquet_config(
        dataset_name=dataset_name,
        config_name=METADATA_CONFIG,
        columns=sorted(METADATA_COLUMNS),
        batch_size=batch_size,
    )
    progress = tqdm(
        iterator,
        total=metadata_limit,
        desc="Phase A metadata",
        unit="row",
        dynamic_ncols=True,
    )

    try:
        for row in progress:
            doc_id = normalize_id(row.get("id"))
            if not doc_id:
                continue
            if not keep_expired and is_expired_full(row):
                continue

            metadata = {
                column: row.get(column)
                for column in METADATA_COLUMNS
                if column in row
            }
            metadata["id"] = doc_id
            rows.append((doc_id, json.dumps(metadata, ensure_ascii=False)))

            if len(rows) >= 5000:
                conn.executemany(
                    "INSERT OR REPLACE INTO metadata (id, payload) VALUES (?, ?)",
                    rows,
                )
                inserted += len(rows)
                progress.set_postfix(inserted=inserted)
                rows.clear()

            if metadata_limit is not None and inserted + len(rows) >= metadata_limit:
                break

        if rows:
            conn.executemany(
                "INSERT OR REPLACE INTO metadata (id, payload) VALUES (?, ?)",
                rows,
            )
            inserted += len(rows)
        conn.commit()
    finally:
        conn.close()
        progress.close()

    print(f"[phase_a] Metadata lookup ready: {inserted} rows", flush=True)
    return db_path


def init_chunks_db(output_path: Path) -> sqlite3.Connection:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()

    conn = sqlite3.connect(output_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA temp_store=FILE;")
    conn.execute(
        """
        CREATE TABLE chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chunk_id TEXT NOT NULL UNIQUE,
            document_id TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            text TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX idx_chunks_document_id ON chunks(document_id)")
    conn.commit()
    return conn


def flush_chunk_rows(
    conn: sqlite3.Connection,
    rows: list[tuple[str, str, int, str, str]],
) -> int:
    if not rows:
        return 0
    conn.executemany(
        """
        INSERT OR REPLACE INTO chunks (
            chunk_id, document_id, chunk_index, text, metadata_json
        ) VALUES (?, ?, ?, ?, ?)
        """,
        rows,
    )
    inserted = len(rows)
    rows.clear()
    return inserted


def build_chunks_checkpoint(
    dataset_name: str,
    metadata_db_path: str,
    content_limit: Optional[int],
    output_path: Path,
    content_batch_size: int,
    chunk_batch_size: int,
) -> int:
    meta_conn = sqlite3.connect(metadata_db_path)
    chunks_conn = init_chunks_db(output_path)
    chunk_rows: list[tuple[str, str, int, str, str]] = []
    total_chunks = 0
    total_documents = 0

    iterator = iter_hf_parquet_config(
        dataset_name=dataset_name,
        config_name=CONTENT_CONFIG,
        columns=["id", "content_html"],
        batch_size=content_batch_size,
    )
    progress = tqdm(
        iterator,
        total=content_limit,
        desc="Phase A content",
        unit="doc",
        dynamic_ncols=True,
    )

    try:
        for row in progress:
            doc_id = normalize_id(row.get("id"))
            content_html = row.get("content_html")
            if not doc_id or not content_html:
                continue

            meta_row = meta_conn.execute(
                "SELECT payload FROM metadata WHERE id = ?",
                (doc_id,),
            ).fetchone()
            if meta_row is None:
                continue

            metadata = json.loads(meta_row[0])
            text = html_to_text(normalize_text(content_html))
            if not text:
                continue

            for chunk_index, chunk_text in enumerate(split_text(text)):
                chunk_rows.append(
                    (
                        f"{doc_id}::chunk_{chunk_index}",
                        doc_id,
                        chunk_index,
                        chunk_text,
                        json.dumps(metadata, ensure_ascii=False),
                    )
                )

            if len(chunk_rows) >= chunk_batch_size:
                total_chunks += flush_chunk_rows(chunks_conn, chunk_rows)
                chunks_conn.commit()

            total_documents += 1
            progress.set_postfix(docs=total_documents, chunks=total_chunks + len(chunk_rows))

            if content_limit is not None and total_documents >= content_limit:
                break

        total_chunks += flush_chunk_rows(chunks_conn, chunk_rows)
        chunks_conn.commit()
    finally:
        progress.close()
        meta_conn.close()
        chunks_conn.close()

    print(
        f"[phase_a] Done. documents={total_documents}, chunks={total_chunks}, output={output_path}",
        flush=True,
    )
    return total_chunks


def main() -> None:
    args = parse_args()
    metadata_db_path = build_metadata_lookup(
        dataset_name=args.dataset_name,
        metadata_limit=args.metadata_limit,
        keep_expired=args.keep_expired,
        batch_size=args.metadata_batch_size,
    )
    try:
        build_chunks_checkpoint(
            dataset_name=args.dataset_name,
            metadata_db_path=metadata_db_path,
            content_limit=args.content_limit,
            output_path=args.output,
            content_batch_size=args.content_batch_size,
            chunk_batch_size=args.chunk_batch_size,
        )
    finally:
        Path(metadata_db_path).unlink(missing_ok=True)


if __name__ == "__main__":
    main()
