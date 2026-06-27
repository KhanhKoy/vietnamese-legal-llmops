from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence

import numpy as np

from .config import get_settings

if TYPE_CHECKING:
    from .embeddings import EmbeddingService


class VectorStore:
    def __init__(self, storage_dir: Optional[Path] = None) -> None:
        settings = get_settings()
        self.storage_dir = Path(storage_dir or settings.vector_store_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        self.db_path = self.storage_dir / "vector_store.sqlite3"
        self.meta_path = self.storage_dir / "store_meta.json"

        self.conn: Optional[sqlite3.Connection] = None
        self.embedding_dim: Optional[int] = None
        self.chunk_count: int = 0

    def _connect(self) -> sqlite3.Connection:
        if self.conn is None:
            self.conn = sqlite3.connect(self.db_path)
            self.conn.execute("PRAGMA journal_mode=WAL;")
            self.conn.execute("PRAGMA synchronous=NORMAL;")
            self.conn.execute("PRAGMA temp_store=FILE;")
            self.conn.execute("PRAGMA cache_size=-20000;")  # ~20 MB cache
            self.conn.execute("PRAGMA mmap_size=268435456;")  # 256 MB memory-map
            self.conn.row_factory = sqlite3.Row
        return self.conn

    def _ensure_schema(self) -> None:
        conn = self._connect()
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chunk_id TEXT NOT NULL,
                document_id TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                text TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                embedding BLOB NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        conn.commit()

    @staticmethod
    def _chunk_to_dict(chunk: Any) -> Dict[str, Any]:
        if isinstance(chunk, dict):
            return chunk
        if hasattr(chunk, "__dict__"):
            return dict(chunk.__dict__)
        raise TypeError("Chunk phải là dict hoặc dataclass có __dict__.")

    def reset(self) -> None:
        conn = self._connect()
        conn.execute("DROP TABLE IF EXISTS chunks")
        conn.execute("DROP TABLE IF EXISTS meta")
        conn.commit()
        self._ensure_schema()
        self.chunk_count = 0
        self.embedding_dim = None

    def build(self, chunks: Sequence[Any], embeddings: np.ndarray) -> None:
        self.reset()
        self.add(chunks, embeddings)

    def add(self, chunks: Sequence[Any], embeddings: np.ndarray) -> None:
        chunk_dicts = [self._chunk_to_dict(chunk) for chunk in chunks]
        embeddings = np.asarray(embeddings, dtype=np.float32)

        if len(chunk_dicts) != len(embeddings):
            raise ValueError("Số chunks và số embeddings phải bằng nhau.")

        if embeddings.ndim != 2:
            raise ValueError("Embeddings phải có dạng 2 chiều.")

        if self.embedding_dim is None:
            self.embedding_dim = int(embeddings.shape[1])
        elif int(embeddings.shape[1]) != self.embedding_dim:
            raise ValueError("Kích thước embedding không khớp với vector store.")

        self._ensure_schema()
        conn = self._connect()

        # Store as float16 to halve storage size
        embeddings_f16 = embeddings.astype(np.float16)

        rows = []
        for chunk, emb_f16 in zip(chunk_dicts, embeddings_f16):
            rows.append(
                (
                    str(chunk.get("chunk_id", "")),
                    str(chunk.get("document_id", "")),
                    int(chunk.get("chunk_index", 0)),
                    str(chunk.get("text", "")),
                    json.dumps(chunk.get("metadata", {}), ensure_ascii=False),
                    emb_f16.tobytes(),
                )
            )

        conn.executemany(
            """
            INSERT INTO chunks (
                chunk_id, document_id, chunk_index, text, metadata_json, embedding
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        self.chunk_count += len(rows)

    def commit(self) -> None:
        """
        Lightweight SQLite COMMIT without writing meta.json to disk.
        Call periodically during large builds to free WAL memory.
        """
        if self.conn is not None:
            self.conn.commit()

    def save(self) -> None:
        conn = self._connect()
        conn.commit()

        if self.embedding_dim is None:
            self.embedding_dim = self._read_embedding_dim()

        meta = {
            "num_chunks": self.chunk_count,
            "embedding_dim": self.embedding_dim,
        }
        with self.meta_path.open("w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

    def _read_embedding_dim(self) -> int:
        conn = self._connect()
        row = conn.execute("SELECT embedding FROM chunks LIMIT 1").fetchone()
        if row is None:
            raise ValueError("Vector store rỗng.")
        emb = np.frombuffer(row["embedding"], dtype=np.float16)
        return int(emb.shape[0])

    def load(self) -> None:
        if not self.db_path.exists():
            raise FileNotFoundError("Không tìm thấy vector store. Hãy build index trước.")

        self._ensure_schema()

        conn = self._connect()
        row = conn.execute("SELECT COUNT(*) AS cnt FROM chunks").fetchone()
        self.chunk_count = int(row["cnt"]) if row else 0

        if self.chunk_count == 0:
            raise ValueError("Vector store rỗng.")

        self.embedding_dim = self._read_embedding_dim()

    def _iter_chunks_in_batches(self, batch_size: int = 512):
        conn = self._connect()
        last_id = 0

        while True:
            rows = conn.execute(
                """
                SELECT id, chunk_id, document_id, chunk_index, text, metadata_json, embedding
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
            yield rows

    def search_by_embedding(
        self,
        query_embedding: np.ndarray,
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        if self.db_path is None:
            raise ValueError("Vector store chưa được khởi tạo.")

        query_embedding = np.asarray(query_embedding, dtype=np.float32).reshape(-1)

        best: List[Dict[str, Any]] = []

        for rows in self._iter_chunks_in_batches(batch_size=256):
            embeddings = []
            chunks = []

            for row in rows:
                emb = np.frombuffer(row["embedding"], dtype=np.float16).astype(np.float32)
                embeddings.append(emb)
                chunks.append(
                    {
                        "chunk_id": row["chunk_id"],
                        "document_id": row["document_id"],
                        "chunk_index": row["chunk_index"],
                        "text": row["text"],
                        "metadata": json.loads(row["metadata_json"]),
                    }
                )

            emb_matrix = np.vstack(embeddings).astype(np.float32)
            scores = emb_matrix @ query_embedding

            for score, chunk in zip(scores, chunks):
                item = {"score": float(score), "chunk": chunk}
                best.append(item)

            if len(best) > top_k * 10:
                best.sort(key=lambda x: x["score"], reverse=True)
                best = best[:top_k]

        best.sort(key=lambda x: x["score"], reverse=True)
        return best[:top_k]

    def search(
        self,
        query: str,
        embedder: Optional["EmbeddingService"] = None,
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        if embedder is None:
            from .embeddings import EmbeddingService

            embedder = EmbeddingService()

        query_embedding = embedder.embed_query(query)
        return self.search_by_embedding(query_embedding, top_k=top_k)
