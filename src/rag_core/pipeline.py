from __future__ import annotations

import os
from typing import Any, Dict, Optional

from .chunking import chunk_document
from .dataset_reader import iter_documents
from .embeddings import EmbeddingService
from .vector_store import VectorStore


def build_index_pipeline(
    metadata_limit: Optional[int] = None,
    content_limit: Optional[int] = None,
    vector_store: Optional[VectorStore] = None,
    embedder: Optional[EmbeddingService] = None,
    document_batch_size: int = 32,
    commit_interval: int = 0,
) -> VectorStore:
    """
    Build vector index with streaming to keep RAM usage bounded,
    và tự động bỏ qua các chunks đã có sẵn trên AWS RDS để hỗ trợ chạy tiếp nối.
    """
    # Determine embedder to use
    if commit_interval <= 0:
        commit_interval = max(1, int(os.getenv("INDEX_COMMIT_INTERVAL", "1000")))

    if embedder is None:
        if vector_store is not None and hasattr(vector_store, "embedder") and vector_store.embedder is not None:
            embedder = vector_store.embedder
        else:
            embedder = EmbeddingService()

    # Create vector store if not provided
    if vector_store is None:
        store = VectorStore(embedder=embedder)
    else:
        store = vector_store
        store.embedder = embedder
        store.embed_dim = embedder.dimension

    # ⚠️ ĐÃ BỎ LỆNH RESET: Tránh việc xóa sạch toàn bộ DB cũ khi bắt đầu Session mới!
    # store.reset()

    # =======================================================
    # 🚀 1. LẤY DANH SÁCH CHUNK_ID ĐÃ CÓ TRÊN AWS RDS
    # =======================================================
    print("🔍 Đang đối chiếu danh sách chunks với AWS RDS...")
    existing_ids = store.get_existing_chunk_ids()
    print(f"✅ Đã tìm thấy {len(existing_ids)} chunks đã tồn tại trên DB. Hệ thống sẽ tự động bỏ qua.")

    chunk_buffer = []
    text_buffer = []
    total_chunks = 0
    skipped_chunks = 0
    since_last_commit = 0

    doc_iter = iter_documents(
        metadata_limit=metadata_limit,
        content_limit=content_limit,
        content_batch_size=document_batch_size,
    )

    for document in doc_iter:
        doc_chunks = chunk_document(document)

        for chunk in doc_chunks:
            # Trích xuất chunk_id an toàn (kể cả khi chunk là Dataclass hoặc Dict)
            c_id = str(getattr(chunk, "chunk_id", chunk.get("chunk_id", "") if isinstance(chunk, dict) else ""))

            # =======================================================
            # 🚀 2. BỎ QUA CHUNK ĐÃ EMBEDDING RỒI (TIẾT KIỆM GPU)
            # =======================================================
            if c_id and c_id in existing_ids:
                skipped_chunks += 1
                continue

            chunk_buffer.append(chunk)
            text_buffer.append(chunk.text)

            if len(text_buffer) >= embedder.batch_size:
                embeddings = embedder.embed_texts(text_buffer)
                store.add(chunk_buffer, embeddings)
                total_chunks += len(chunk_buffer)
                since_last_commit += len(chunk_buffer)

                chunk_buffer.clear()
                text_buffer.clear()

                # Periodic flush to keep SQLite/Memory down
                if since_last_commit >= commit_interval:
                    store.commit()
                    since_last_commit = 0

    # --- Flush remaining buffer ---
    if text_buffer:
        embeddings = embedder.embed_texts(text_buffer)
        store.add(chunk_buffer, embeddings)
        total_chunks += len(chunk_buffer)

    print(f"📊 Kết quả lượt chạy: Đã bỏ qua {skipped_chunks} chunks cũ | Nạp mới thành công {total_chunks} chunks.")

    if total_chunks == 0 and skipped_chunks == 0:
        raise ValueError("Không tạo được chunk nào từ dataset.")

    store.save()
    return store


async def ask_pipeline(question: str, top_k: Optional[int] = None) -> Dict[str, Any]:
    from .qa_service import QAService

    service = QAService()
    return await service.ask(question=question, top_k=top_k)
