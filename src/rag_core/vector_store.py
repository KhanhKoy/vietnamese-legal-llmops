from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
from .config import get_settings
from .embeddings import EmbeddingService

class VectorStore:
    def __init__(self, storage_dir: Optional[Path] = None) -> None:
        self.settings = get_settings()
        
        # Kiểm tra biến môi trường xem có kích hoạt chế độ chạy PostgreSQL trên Cloud không
        self.use_pgvector = os.getenv("USE_PGVECTOR", "0").lower() in ("1", "true", "yes", "y")
        self.embedder = EmbeddingService()
        
        if self.use_pgvector:
            # --- CHẾ ĐỘ PRODUCTION: AMAZON RDS (POSTGRESQL + PGVECTOR) ---
            import psycopg
            from pgvector.psycopg import register_vector
            
            # Kết nối tới database Amazon RDS dựa trên config
            self.conn = psycopg.connect(
                host=self.settings.pg_host,
                port=self.settings.pg_port,
                user=self.settings.pg_user,
                password=self.settings.pg_password,
                dbname=self.settings.pg_database,
                autocommit=False
            )
            register_vector(self.conn)
            self._init_postgres()
        else:
            # --- CHẾ ĐỘ LOCAL DEV: FAISS + SQLITE3 ---
            import faiss
            self.faiss = faiss
            self.storage_dir = Path(storage_dir or self.settings.vector_store_dir)
            self.storage_dir.mkdir(parents=True, exist_ok=True)

            self.index_path = self.storage_dir / "faiss_index.bin"
            self.meta_path = self.storage_dir / "faiss_meta.sqlite3"

            self.index: Optional[faiss.Index] = None
            self.embedding_dim: Optional[int] = None
            self.total_vectors: int = 0
            
            self.sqlite_conn = sqlite3.connect(self.meta_path)
            self._init_sqlite()

    # -----------------------------------------------------------------
    # Khởi tạo bảng dữ liệu
    # -----------------------------------------------------------------
    def _init_sqlite(self) -> None:
        self.sqlite_conn.execute(
            """
            CREATE TABLE IF NOT EXISTS metadata (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chunk_id TEXT NOT NULL,
                document_id TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                text TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )
        self.sqlite_conn.commit()

    def _init_postgres(self) -> None:
        # Kích hoạt extension pgvector trong database nếu chưa có
        with self.conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            # Tạo bảng lưu trữ vector luật pháp tích hợp cột vector nhúng (1536 chiều cho Titan Embedding)
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS legal_chunks (
                    id SERIAL PRIMARY KEY,
                    chunk_id TEXT NOT NULL,
                    document_id TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    metadata_json JSONB NOT NULL,
                    embedding vector(1536)
                );
                """
            )
        self.conn.commit()

    # -----------------------------------------------------------------
    # Các hàm tương tác API chung (Public API)
    # -----------------------------------------------------------------
    def reset(self) -> None:
        if self.use_pgvector:
            with self.conn.cursor() as cur:
                cur.execute("TRUNCATE TABLE legal_chunks;")
            self.conn.commit()
        else:
            if hasattr(self, "sqlite_conn") and self.sqlite_conn:
                self.sqlite_conn.close()
            try:
                if self.index_path.exists():
                    self.index_path.unlink()
            except PermissionError:
                pass
            self.index = None
            self.embedding_dim = None
            self.total_vectors = 0
            self.sqlite_conn = sqlite3.connect(self.meta_path)
            self._init_sqlite()

    def add(self, chunks: Sequence[Any], embeddings: np.ndarray) -> None:
        if len(chunks) != embeddings.shape[0]:
            raise ValueError("Số lượng chunks và embeddings không khớp nhau.")
        
        chunk_dicts = [self._chunk_to_dict(c) for c in chunks]
        embeddings_f32 = np.asarray(embeddings, dtype=np.float32)

        if self.use_pgvector:
            with self.conn.cursor() as cur:
                for ch, emb in zip(chunk_dicts, embeddings_f32):
                    cur.execute(
                        """
                        INSERT INTO legal_chunks (chunk_id, document_id, chunk_index, text, metadata_json, embedding)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        (
                            str(ch.get("chunk_id", "")),
                            str(ch.get("document_id", "")),
                            int(ch.get("chunk_index", 0)),
                            str(ch.get("text", "")),
                            json.dumps(ch.get("metadata", {}), ensure_ascii=False),
                            emb.tolist()
                        )
                    )
        else:
            dim = embeddings_f32.shape[1]
            if self.index is None:
                if self.index_path.exists():
                    self.index = self.faiss.read_index(str(self.index_path))
                    self.embedding_dim = int(self.index.d)
                else:
                    self.index = self.faiss.IndexFlatIP(dim)
                    self.embedding_dim = dim
            
            # Ghi metadata vào SQLite
            cursor = self.sqlite_conn.cursor()
            for ch in chunk_dicts:
                cursor.execute(
                    "INSERT INTO metadata (chunk_id, document_id, chunk_index, text, metadata_json) VALUES (?, ?, ?, ?, ?)",
                    (
                        str(ch.get("chunk_id", "")),
                        str(ch.get("document_id", "")),
                        int(ch.get("chunk_index", 0)),
                        str(ch.get("text", "")),
                        json.dumps(ch.get("metadata", {}), ensure_ascii=False),
                    )
                )
            self.sqlite_conn.commit()
            self.index.add(embeddings_f32)
            self.total_vectors += len(chunks)

    def commit(self) -> None:
        if self.use_pgvector:
            self.conn.commit()
        else:
            self.sqlite_conn.commit()

    def save(self) -> None:
        if self.use_pgvector:
            self.conn.commit()
        else:
            if self.index is not None:
                self.faiss.write_index(self.index, str(self.index_path))

    def load(self) -> None:
        if not self.use_pgvector:
            if self.index_path.exists():
                self.index = self.faiss.read_index(str(self.index_path))
                self.total_vectors = self.index.ntotal
                self.embedding_dim = int(self.index.d)

    # -----------------------------------------------------------------
    # Hàm giải quyết bài toán crash code trên Lambda
    # -----------------------------------------------------------------
    def close(self) -> None:
        """Đóng an toàn mọi kết nối cơ sở dữ liệu để giải phóng tài nguyên mạng."""
        if self.use_pgvector and hasattr(self, "conn") and self.conn:
            try:
                self.conn.commit()
                self.conn.close()
            except Exception:
                pass
        elif not self.use_pgvector and hasattr(self, "sqlite_conn") and self.sqlite_conn:
            try:
                self.sqlite_conn.close()
            except Exception:
                pass

    # -----------------------------------------------------------------
    # Tìm kiếm dữ liệu tương đồng (Search)
    # -----------------------------------------------------------------
    def search(self, query: str, embedder: Optional[EmbeddingService] = None, top_k: int = 5) -> List[Dict[str, Any]]:
        emb_service = embedder or self.embedder
        q_emb = emb_service.embed_query(query)
        q_emb_f32 = np.asarray(q_emb, dtype=np.float32)

        results: List[Dict[str, Any]] = []

        if self.use_pgvector:
            # Thực hiện truy vấn khoảng cách Vector Cosine (<=>) trên PostgreSQL RDS
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT chunk_id, document_id, chunk_index, text, metadata_json, (embedding <=> %s) as distance
                    FROM legal_chunks
                    ORDER BY distance ASC
                    LIMIT %s;
                    """,
                    (q_emb_f32.tolist(), top_k)
                )
                rows = cur.fetchall()
                for row in rows:
                    results.append({
                        "chunk_id": row[0],
                        "document_id": row[1],
                        "chunk_index": row[2],
                        "text": row[3],
                        "metadata": json.loads(row[4]) if isinstance(row[4], str) else row[4],
                        "score": float(1 - row[5])  # Chuyển đổi khoảng cách thành điểm số tương đồng
                    })
        else:
            if self.index is None:
                self.load()
            if self.index is None:
                raise RuntimeError("Hệ thống Vector Index trống – Hãy nạp dữ liệu trước.")
            
            q_reshaped = q_emb_f32.reshape(1, -1)
            D, I = self.index.search(q_reshaped, top_k)
            ids = (I[0] + 1).tolist()
            placeholders = ",".join("?" for _ in ids)

            cursor = self.sqlite_conn.cursor()
            cursor.execute(
                f"SELECT chunk_id, document_id, chunk_index, text, metadata_json FROM metadata WHERE id IN ({placeholders})",
                ids
            )
            rows = cursor.fetchall()
            for (chunk_id, document_id, chunk_index, text, metadata_json), score in zip(rows, D[0]):
                results.append({
                    "chunk_id": chunk_id,
                    "document_id": document_id,
                    "chunk_index": chunk_index,
                    "text": text,
                    "metadata": json.loads(metadata_json),
                    "score": float(score)
                })
        return results

    @property
    def chunk_count(self) -> int:
        if self.use_pgvector:
            try:
                with self.conn.cursor() as cur:
                    cur.execute("SELECT COUNT(*) FROM legal_chunks;")
                    row = cur.fetchone()
                    # Kiểm tra xem cursor có thực sự trả về hàng dữ liệu nào không
                    if row is not None:
                        return int(row[0])
                    return 0
            except Exception as e:
                # Trả về 0 nếu có bất kỳ lỗi kết nối hoặc truy vấn nào phát sinh
                print(f"Warning: Không thể lấy số lượng chunk từ Postgres ({e})")
                return 0
        else:
            return self.index.ntotal if self.index is not None else self.total_vectors
    @staticmethod
    def _chunk_to_dict(chunk: Any) -> Dict[str, Any]:
        if isinstance(chunk, dict):
            return chunk
        if hasattr(chunk, "__dict__"):
            return dict(chunk.__dict__)
        raise TypeError("Chunk phải là một dictionary hoặc đối tượng Dataclass.")

    def __del__(self) -> None:
        self.close()