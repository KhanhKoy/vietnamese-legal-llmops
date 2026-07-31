from __future__ import annotations

import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


import numpy as np

from .config import get_settings
from .embeddings import EmbeddingService

VIETNAMESE_STOPWORDS = {
    "và", "hoặc", "là", "của", "cho", "với", "một", "những", "các", "theo",
    "trong", "khi", "nào", "ở", "đâu", "thì", "có", "không", "bị", "được",
    "phải", "nên", "về", "tại", "từ", "đến", "này", "đó", "kia", "ấy"
}


class VectorStore:
    def __init__(self, storage_dir: Optional[Path] = None, embedder: Optional[EmbeddingService] = None) -> None:
        self.settings = get_settings()
        self.use_pgvector = os.getenv("USE_PGVECTOR", "0").lower() in ("1", "true", "yes", "y")
        self.embedder = embedder or EmbeddingService()
        self.embed_dim = self.embedder.dimension  # dimension of embedding vectors

        if self.use_pgvector:
            import psycopg
            from pgvector.psycopg import register_vector

            sslmode = os.getenv("PGSSLMODE", "require")
            self.conn = psycopg.connect(
                host=self.settings.pg_host,
                port=self.settings.pg_port,
                user=self.settings.pg_user,
                password=self.settings.pg_password,
                dbname=self.settings.pg_database,
                sslmode=sslmode,
                autocommit=False,
            )

            # Kích hoạt extension pgvector trước
            with self.conn.cursor() as cur:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            self.conn.commit()

            # Đăng ký vector và tạo bảng
            register_vector(self.conn)
            self._init_postgres()
        else:
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
        from psycopg import sql

        with self.conn.cursor() as cur:
            create_table_query = sql.SQL(
                """
                CREATE TABLE IF NOT EXISTS legal_chunks (
                    id SERIAL PRIMARY KEY,
                    chunk_id TEXT NOT NULL,
                    document_id TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    metadata_json JSONB NOT NULL,
                    embedding vector({dim})
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_legal_chunks_chunk_id ON legal_chunks (chunk_id);
                """
            ).format(dim=sql.Literal(self.embed_dim))

            cur.execute(create_table_query)
        self.conn.commit()

    def _normalize_text(self, text: str) -> str:
        return re.sub(r"\s+", " ", (text or "").strip())

    def _extract_keywords(self, question: str) -> List[str]:
        tokens = re.findall(r"[A-Za-zÀ-ỹ0-9_]+", (question or "").lower())
        keywords = [
            token for token in tokens
            if token not in VIETNAMESE_STOPWORDS and len(token) > 1
        ]
        seen = set()
        unique_keywords: List[str] = []
        for token in keywords:
            if token not in seen:
                seen.add(token)
                unique_keywords.append(token)
        return unique_keywords

    def _safe_float(self, value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except Exception:
            return default

    def _safe_int(self, value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except Exception:
            return default

    def _doc_fingerprint(self, doc: Dict[str, Any]) -> str:
        return str(
            doc.get("document_id")
            or doc.get("source")
            or doc.get("id")
            or doc.get("chunk_id")
            or doc.get("text", "")[:250]
        )

    def _normalize_results(self, result: Any) -> List[Dict[str, Any]]:
        if isinstance(result, dict):
            items = result.get("results") or result.get("documents") or result.get("data") or []
            return items if isinstance(items, list) else []
        if isinstance(result, list):
            return result
        return []

    def _build_keyword_like_clauses(self, keywords: List[str], op: str = " AND ") -> Tuple[str, List[Any]]:
        clauses = []
        params: List[Any] = []

        for kw in keywords:
            clauses.append("(LOWER(text) LIKE ? OR LOWER(metadata_json) LIKE ?)")
            pattern = f"%{kw.lower()}%"
            params.extend([pattern, pattern])

        return op.join(clauses), params

    def _score_keyword_match(self, text: str, keywords: List[str]) -> float:
        if not keywords:
            return 0.0

        normalized = self._normalize_text(text).lower()
        hits = sum(1 for kw in keywords if kw in normalized)
        return hits / max(len(keywords), 1)

    def _merge_result_sets(self, result_sets: List[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        merged: Dict[str, Dict[str, Any]] = {}

        for results in result_sets:
            for idx, doc in enumerate(results):
                if not isinstance(doc, dict):
                    continue

                fp = self._doc_fingerprint(doc)
                current = merged.get(fp)

                score = self._safe_float(doc.get("score", 0.0))
                if score <= 0.0:
                    score = 1.0 / (idx + 1)

                if current is None or score > self._safe_float(current.get("_rank_score", current.get("score", 0.0))):
                    new_doc = dict(doc)
                    new_doc["_rank_score"] = score
                    merged[fp] = new_doc

        return sorted(
            merged.values(),
            key=lambda d: self._safe_float(d.get("_rank_score", d.get("score", 0.0))),
            reverse=True,
        )

    def _ensure_loaded(self) -> None:
        if self.use_pgvector:
            return

        if self.index is None:
            self.load()

    def reset(self) -> None:
        if self.use_pgvector:
            with self.conn.cursor() as cur:
                cur.execute("TRUNCATE TABLE legal_chunks;")
            self.conn.commit()
            return

        if hasattr(self, "sqlite_conn") and self.sqlite_conn:
            self.sqlite_conn.close()

        try:
            if self.index_path.exists():
                self.index_path.unlink()
        except PermissionError:
            pass

        try:
            if self.meta_path.exists():
                self.meta_path.unlink()
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

        # ==========================================
        # 1. TRƯỜNG HỢP DÙNG PGVECTOR (AWS RDS - PSYCOPG v3)
        # ==========================================
        if self.use_pgvector:
            records = [
                (
                    str(ch.get("chunk_id", "")),
                    str(ch.get("document_id", "")),
                    self._safe_int(ch.get("chunk_index", 0)),
                    str(ch.get("text", "")),
                    json.dumps(ch.get("metadata", {}), ensure_ascii=False),
                    emb.tolist(),
                )
                for ch, emb in zip(chunk_dicts, embeddings_f32)
            ]

            query = """
                INSERT INTO legal_chunks (chunk_id, document_id, chunk_index, text, metadata_json, embedding)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (chunk_id) DO NOTHING;
            """

            # Psycopg v3 tối ưu executemany cực tốt cho bulk insert
            batch_size = 1000
            cur = self.conn.cursor()
            try:
                for i in range(0, len(records), batch_size):
                    batch = records[i : i + batch_size]
                    cur.executemany(query, batch)
                self.conn.commit()
            finally:
                cur.close()
            return

        # ==========================================
        # 2. TRƯỜNG HỢP DÙNG FAISS + SQLITE (LOCAL)
        # ==========================================
        dim = embeddings_f32.shape[1]
        if self.index is None:
            if self.index_path.exists():
                self.index = self.faiss.read_index(str(self.index_path))
                if self.index is not None:
                    self.embedding_dim = int(self.index.d)
            else:
                self.index = self.faiss.IndexFlatIP(dim)
                self.embedding_dim = dim

        sqlite_records = [
            (
                str(ch.get("chunk_id", "")),
                str(ch.get("document_id", "")),
                self._safe_int(ch.get("chunk_index", 0)),
                str(ch.get("text", "")),
                json.dumps(ch.get("metadata", {}), ensure_ascii=False),
            )
            for ch in chunk_dicts
        ]

        # Tối ưu hóa SQLite bằng executemany thay cho vòng lặp
        cursor = self.sqlite_conn.cursor()
        cursor.executemany(
            """
            INSERT INTO metadata (chunk_id, document_id, chunk_index, text, metadata_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            sqlite_records,
        )
        self.sqlite_conn.commit()

        assert self.index is not None
        self.index.add(embeddings_f32)  # type: ignore
        self.total_vectors += len(chunks)

    def commit(self) -> None:
        if self.use_pgvector:
            self.conn.commit()
        else:
            self.sqlite_conn.commit()

    def save(self) -> None:
        if self.use_pgvector:
            self.conn.commit()
        elif self.index is not None:
            self.faiss.write_index(self.index, str(self.index_path))

    def load(self) -> None:
        if self.use_pgvector:
            return

        if self.index_path.exists():
            self.index = self.faiss.read_index(str(self.index_path))
            if self.index is not None:
                self.total_vectors = self.index.ntotal
                self.embedding_dim = int(self.index.d)

    def close(self) -> None:
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

    def search_by_vector(
        self,
        query_vector: List[float],
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Tìm kiếm k-NN vector tương đồng trong PostgreSQL pgvector bằng query_vector (dạng list float)."""
        if not self.use_pgvector or not self.conn:
            return []

        try:
            if hasattr(self.conn, "info") and self.conn.info.transaction_status == 3:
                self.conn.rollback()

            vector_str = f"[{','.join(map(str, query_vector))}]"

            where_clauses = []
            params: List[Any] = [vector_str]

            if filters:
                for key, value in filters.items():
                    if value is not None:
                        where_clauses.append("metadata_json @> %s::jsonb")
                        params.append(json.dumps({key: value}, ensure_ascii=False))

            where_sql = ""
            if where_clauses:
                where_sql = "WHERE " + " AND ".join(where_clauses)

            params.append(top_k)

            sql = f"""
                SELECT 
                    id,
                    document_id,
                    chunk_id,
                    chunk_index,
                    text,
                    metadata_json,
                    (embedding <=> %s::vector) AS distance
                FROM legal_chunks
                {where_sql}
                ORDER BY distance ASC
                LIMIT %s;
            """

            results = []
            with self.conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()

                for row in rows:
                    distance = float(row[6])
                    similarity_score = max(0.0, 1.0 - distance)

                    metadata = row[5]
                    if isinstance(metadata, str):
                        try:
                            metadata = json.loads(metadata)
                        except Exception:
                            metadata = {}

                    results.append({
                        "id": row[0],
                        "document_id": row[1],
                        "chunk_id": row[2],
                        "chunk_index": row[3],
                        "text": row[4],
                        "metadata": metadata if isinstance(metadata, dict) else {},
                        "distance": distance,
                        "score": similarity_score,
                    })

            return results

        except Exception as e:
            if self.conn:
                self.conn.rollback()
            print(f"❌ Lỗi khi search_by_vector: {e}")
            return []

    def _search_pgvector(
        self,
        query: str,
        top_k: int,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        q_emb = self.embedder.embed_query(query)
        q_emb_f32 = np.asarray(q_emb, dtype=np.float32).tolist()
        return self.search_by_vector(query_vector=q_emb_f32, top_k=top_k, filters=filters)

    def _search_faiss(self, query: str, top_k: int) -> List[Dict[str, Any]]:
        q_emb = self.embedder.embed_query(query)
        q_emb_f32 = np.asarray(q_emb, dtype=np.float32)

        if self.index is None:
            self.load()
        if self.index is None:
            raise RuntimeError("Hệ thống Vector Index trống – Hãy nạp dữ liệu trước.")

        assert self.index is not None
        q_reshaped = q_emb_f32.reshape(1, -1)
        D, I = self.index.search(q_reshaped, top_k)  # type: ignore

        row_ids = [self._safe_int(i) + 1 for i in I[0].tolist() if self._safe_int(i) >= 0]
        if not row_ids:
            return []

        placeholders = ",".join("?" for _ in row_ids)
        order_case = " ".join([f"WHEN id = ? THEN {idx}" for idx, _ in enumerate(row_ids)])

        cursor = self.sqlite_conn.cursor()
        cursor.execute(
            f"""
            SELECT id, chunk_id, document_id, chunk_index, text, metadata_json
            FROM metadata
            WHERE id IN ({placeholders})
            ORDER BY CASE {order_case} ELSE {len(row_ids)} END
            """,
            row_ids + row_ids,
        )
        rows = cursor.fetchall()

        row_map: Dict[int, Tuple[Any, ...]] = {int(row[0]): row for row in rows}

        results: List[Dict[str, Any]] = []
        for rank, row_id in enumerate(row_ids):
            row = row_map.get(row_id)
            if row is None:
                continue

            _, chunk_id, document_id, chunk_index, text, metadata_json = row
            metadata = {}
            try:
                metadata = json.loads(metadata_json)
            except Exception:
                metadata = {}

            score = float(D[0][rank]) if rank < len(D[0]) else 0.0
            results.append(
                {
                    "chunk_id": chunk_id,
                    "document_id": document_id,
                    "chunk_index": chunk_index,
                    "text": text,
                    "metadata": metadata,
                    "score": score,
                }
            )

        return results

    def search(
        self,
        query: str,
        embedder: Optional[EmbeddingService] = None,
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        if embedder is not None:
            self.embedder = embedder

        self._ensure_loaded()
        if self.use_pgvector:
            return self._search_pgvector(query, top_k, filters=filters)
        return self._search_faiss(query, top_k)

    def keyword_search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        keywords = self._extract_keywords(query)
        if not keywords:
            return []

        results: List[Dict[str, Any]] = []

        def run_sqlite(use_and: bool) -> List[Dict[str, Any]]:
            where_op = " AND " if use_and else " OR "
            where_clause, params = self._build_keyword_like_clauses(keywords, op=where_op)
            if not where_clause:
                return []

            cursor = self.sqlite_conn.cursor()
            cursor.execute(
                f"""
                SELECT id, chunk_id, document_id, chunk_index, text, metadata_json
                FROM metadata
                WHERE {where_clause}
                LIMIT ?
                """,
                params + [top_k * 3],
            )
            rows = cursor.fetchall()

            items: List[Dict[str, Any]] = []
            for row in rows:
                metadata = {}
                try:
                    metadata = json.loads(row[5])
                except Exception:
                    metadata = {}
                score = self._score_keyword_match(str(row[4]), keywords)
                items.append(
                    {
                        "chunk_id": row[1],
                        "document_id": row[2],
                        "chunk_index": row[3],
                        "text": row[4],
                        "metadata": metadata,
                        "score": score,
                    }
                )
            return items

        def run_pg(use_and: bool) -> List[Dict[str, Any]]:
            if hasattr(self.conn, "info") and self.conn.info.transaction_status == 3:
                self.conn.rollback()

            clauses = []
            params: List[Any] = []
            joiner = " AND " if use_and else " OR "
            for kw in keywords:
                clauses.append("(LOWER(text) LIKE %s OR LOWER(CAST(metadata_json AS TEXT)) LIKE %s)")
                pattern = f"%{kw.lower()}%"
                params.extend([pattern, pattern])

            sql = f"""
                SELECT chunk_id, document_id, chunk_index, text, metadata_json
                FROM legal_chunks
                WHERE {joiner.join(clauses)}
                LIMIT %s;
            """
            params.append(top_k * 3)

            try:
                with self.conn.cursor() as cur:
                    cur.execute(sql, params)
                    rows = cur.fetchall()
            except Exception as e:
                if self.conn:
                    self.conn.rollback()
                print(f"❌ Lỗi khi keyword_search: {e}")
                return []

            items: List[Dict[str, Any]] = []
            for row in rows:
                metadata = row[4]
                if isinstance(metadata, str):
                    try:
                        metadata = json.loads(metadata)
                    except Exception:
                        metadata = {}
                score = self._score_keyword_match(str(row[3]), keywords)
                items.append(
                    {
                        "chunk_id": row[0],
                        "document_id": row[1],
                        "chunk_index": row[2],
                        "text": row[3],
                        "metadata": metadata,
                        "score": score,
                    }
                )
            return items

        results = run_pg(True) if self.use_pgvector else run_sqlite(True)

        if not results and len(keywords) > 1:
            results = run_pg(False) if self.use_pgvector else run_sqlite(False)

        results.sort(key=lambda d: self._safe_float(d.get("score", 0.0)), reverse=True)
        return results[:top_k]

    def hybrid_search(
        self,
        query: str,
        embedder: Optional[EmbeddingService] = None,
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        if embedder is not None:
            self.embedder = embedder

        vector_results = self.search(query=query, top_k=max(top_k * 2, top_k))
        keyword_results = self.keyword_search(query=query, top_k=max(top_k * 2, top_k))

        merged: Dict[str, Dict[str, Any]] = {}

        for idx, doc in enumerate(vector_results):
            if not isinstance(doc, dict):
                continue
            fp = self._doc_fingerprint(doc)
            new_doc = dict(doc)
            base_score = self._safe_float(new_doc.get("score", 0.0))
            new_doc["_rank_score"] = base_score * 0.7 + (1.0 / (idx + 1)) * 0.3
            merged[fp] = new_doc

        for idx, doc in enumerate(keyword_results):
            if not isinstance(doc, dict):
                continue
            fp = self._doc_fingerprint(doc)
            kw_score = self._safe_float(doc.get("score", 0.0))
            boost = kw_score * 0.8 + (1.0 / (idx + 1)) * 0.2

            current = merged.get(fp)
            if current is None or boost > self._safe_float(current.get("_rank_score", current.get("score", 0.0))):
                new_doc = dict(doc)
                new_doc["_rank_score"] = boost
                merged[fp] = new_doc

        final_results = sorted(
            merged.values(),
            key=lambda d: self._safe_float(d.get("_rank_score", d.get("score", 0.0))),
            reverse=True,
        )

        return final_results[:top_k]

    def retrieve(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        return self.hybrid_search(query=query, top_k=top_k)

    def query(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        return self.hybrid_search(query=query, top_k=top_k)

    def _format_context(self, results: List[Dict[str, Any]]) -> str:
        blocks: List[str] = []
        for idx, result in enumerate(results, start=1):
            score = self._safe_float(result.get("score", result.get("_rank_score", 0.0)))
            doc_id = result.get("document_id", "unknown")
            chunk_id = result.get("chunk_id", "unknown")
            text = str(result.get("text", "")).strip()
            blocks.append(
                f"[Nguồn {idx} | score={score:.4f} | doc={doc_id} | chunk={chunk_id}]\n{text}"
            )
        return "\n\n---\n\n".join(blocks)

    @property
    def chunk_count(self) -> int:
        if self.use_pgvector:
            if not self.conn:
                return 0
            try:
                if hasattr(self.conn, "info") and self.conn.info.transaction_status == 3:
                    self.conn.rollback()
                with self.conn.cursor() as cur:
                    cur.execute("SELECT COUNT(*) FROM legal_chunks;")
                    row = cur.fetchone()
                    return self._safe_int(row[0], 0) if row else 0
            except Exception as e:
                if self.conn:
                    self.conn.rollback()
                print(f"Warning: Không thể lấy số lượng chunk từ Postgres ({e})")
                return 0
        return self._safe_int(self.index.ntotal, self.total_vectors) if self.index is not None else self.total_vectors

    @staticmethod
    def _chunk_to_dict(chunk: Any) -> Dict[str, Any]:
        if isinstance(chunk, dict):
            return chunk
        if hasattr(chunk, "__dict__"):
            return dict(chunk.__dict__)
        raise TypeError("Chunk phải là một dictionary hoặc đối tượng Dataclass.")

    def update_document_metadata(self, document_id: str, updates: dict) -> bool:
        """
        Cập nhật linh hoạt các trường trong metadata_json (is_procedural_law, tinh_trang_hieu_luc, ngay_het_hieu_luc...)
        cho tất cả các chunks thuộc document_id.
        """
        if not self.use_pgvector or not updates:
            return False

        if hasattr(self.conn, "info") and self.conn.info.transaction_status == 3:
            self.conn.rollback()

        sql = """
            UPDATE legal_chunks
            SET metadata_json = metadata_json || %s::jsonb
            WHERE document_id = %s;
        """
        try:
            with self.conn.cursor() as cur:
                cur.execute(sql, (
                    json.dumps(updates, ensure_ascii=False),
                    document_id
                ))
            self.conn.commit()
            return True
        except Exception as e:
            if self.conn:
                self.conn.rollback()
            print(f"❌ Lỗi khi update metadata: {e}")
            return False

    def delete_document_by_id(self, document_id: str) -> bool:
        """Xóa tất cả các chunks thuộc về document_id"""
        if not self.use_pgvector:
            return False

        if hasattr(self.conn, "info") and self.conn.info.transaction_status == 3:
            self.conn.rollback()

        sql = "DELETE FROM legal_chunks WHERE document_id = %s;"
        try:
            with self.conn.cursor() as cur:
                cur.execute(sql, (document_id,))
            self.conn.commit()
            return True
        except Exception as e:
            if self.conn:
                self.conn.rollback()
            print(f"❌ Lỗi khi xóa document: {e}")
            return False

    def get_existing_chunk_ids(self) -> set[str]:
        """Lấy toàn bộ danh sách chunk_id đã có trong Database (Postgres hoặc SQLite)."""
        if self.use_pgvector:
            if not self.conn:
                return set()
            try:
                if hasattr(self.conn, "info") and self.conn.info.transaction_status == 3:
                    self.conn.rollback()
                with self.conn.cursor() as cur:
                    cur.execute("SELECT chunk_id FROM legal_chunks;")
                    rows = cur.fetchall()
                    return {str(row[0]) for row in rows}
            except Exception as e:
                if self.conn:
                    self.conn.rollback()
                print(f"⚠️ Không thể lấy danh sách chunk_id từ Postgres ({e})")
                return set()
        else:
            if not hasattr(self, "sqlite_conn") or not self.sqlite_conn:
                return set()
            try:
                cursor = self.sqlite_conn.cursor()
                cursor.execute("SELECT chunk_id FROM metadata;")
                rows = cursor.fetchall()
                return {str(row[0]) for row in rows}
            except Exception as e:
                print(f"⚠️ Không thể lấy danh sách chunk_id từ SQLite ({e})")
                return set()

    def get_chunk_count(self) -> int:
        """Lấy tổng số lượng chunk đang lưu trong DB."""
        return self.chunk_count

    def __del__(self) -> None:
        self.close()