from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, Iterator, List

from tqdm import tqdm

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


DEFAULT_CHUNKS_DB = PROJECT_ROOT / "models" / "indexing" / "chunks.sqlite3"
DEFAULT_VECTOR_DIR = PROJECT_ROOT / "models" / "vector_store"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Phase B: chunks checkpoint -> CUDA embeddings -> vector store."
    )
    parser.add_argument("--chunks-db", type=Path, default=DEFAULT_CHUNKS_DB)
    parser.add_argument("--vector-store-dir", type=Path, default=DEFAULT_VECTOR_DIR)
    parser.add_argument(
        "--batch-size",
        type=int,
        default=16,
        help="Embedding batch size. Use 16 or 32 for GTX 1650 4GB VRAM.",
    )
    parser.add_argument("--commit-interval", type=int, default=512)
    return parser.parse_args()


def count_chunks(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()
    return int(row[0]) if row else 0


def iter_chunk_batches(
    conn: sqlite3.Connection,
    batch_size: int,
) -> Iterator[List[Dict[str, Any]]]:
    last_id = 0
    conn.row_factory = sqlite3.Row

    while True:
        rows = conn.execute(
            """
            SELECT id, chunk_id, document_id, chunk_index, text, metadata_json
            FROM chunks
            WHERE id > ?
            ORDER BY id
            LIMIT ?
            """,
            (last_id, batch_size),
        ).fetchall()

        if not rows:
            break

        last_id = int(rows[-1]["id"])
        yield [
            {
                "chunk_id": row["chunk_id"],
                "document_id": row["document_id"],
                "chunk_index": int(row["chunk_index"]),
                "text": row["text"],
                "metadata": json.loads(row["metadata_json"]),
            }
            for row in rows
        ]


def main() -> None:
    args = parse_args()

    if not args.chunks_db.exists():
        raise FileNotFoundError(f"Chunks checkpoint not found: {args.chunks_db}")

    safe_batch_size = max(1, min(int(args.batch_size), 32))
    os.environ["EMBEDDING_BATCH_SIZE"] = str(safe_batch_size)

    print(f"[phase_b] chunks_db={args.chunks_db}", flush=True)
    print(f"[phase_b] vector_store_dir={args.vector_store_dir}", flush=True)
    print(f"[phase_b] embedding batch_size={safe_batch_size}", flush=True)

    from rag_core.embeddings import EmbeddingService
    from rag_core.vector_store import VectorStore

    chunks_conn = sqlite3.connect(args.chunks_db)
    total_chunks = count_chunks(chunks_conn)
    if total_chunks == 0:
        raise ValueError(f"No chunks found in checkpoint: {args.chunks_db}")

    store = VectorStore(storage_dir=args.vector_store_dir)
    store.reset()
    embedder = EmbeddingService()

    indexed = 0
    since_commit = 0

    progress = tqdm(
        total=total_chunks,
        desc="Phase B embeddings",
        unit="chunk",
        dynamic_ncols=True,
    )

    try:
        for chunk_batch in iter_chunk_batches(chunks_conn, batch_size=safe_batch_size):
            texts = [chunk["text"] for chunk in chunk_batch]
            embeddings = embedder.embed_texts(texts)
            store.add(chunk_batch, embeddings)

            indexed += len(chunk_batch)
            since_commit += len(chunk_batch)
            progress.update(len(chunk_batch))

            if since_commit >= args.commit_interval:
                store.commit()
                since_commit = 0

        store.save()
    finally:
        progress.close()
        chunks_conn.close()

    print(
        f"[phase_b] Done. indexed_chunks={indexed}, vector_store={args.vector_store_dir}",
        flush=True,
    )


if __name__ == "__main__":
    main()
