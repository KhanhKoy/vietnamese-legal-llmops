from __future__ import annotations

import gc
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional

if TYPE_CHECKING:
    from .vector_store import VectorStore


ProgressCallback = Callable[[int, int], None]


def build_index_pipeline(
    metadata_limit: Optional[int] = None,
    content_limit: Optional[int] = None,
    vector_store: Optional["VectorStore"] = None,
    document_batch_size: int = 32,
    commit_interval: int = 100,
    progress_callback: Optional[ProgressCallback] = None,
) -> "VectorStore":
    """
    Build vector index bằng streaming để phù hợp máy local 16GB RAM.

    Luồng xử lý:
    - `iter_documents()` yield từng document đã join metadata + content.
    - Mỗi document được chunk ngay, không giữ toàn bộ corpus trong RAM.
    - Chunk được gom theo `embedder.batch_size`, embed, rồi ghi ngay xuống SQLite.
    - Commit định kỳ để giảm WAL/journal growth.
    """
    print("[pipeline] Starting build_index_pipeline...", flush=True)

    print("[pipeline] Importing VectorStore...", flush=True)
    from .vector_store import VectorStore

    print("[pipeline] Importing EmbeddingService...", flush=True)
    from .embeddings import EmbeddingService

    print("[pipeline] Importing dataset reader...", flush=True)
    from .dataset_reader import iter_documents

    print("[pipeline] Importing chunking...", flush=True)
    from .chunking import split_text

    store = vector_store or VectorStore()
    print("[pipeline] Resetting vector store...", flush=True)
    store.reset()
    print("[pipeline] Loading embedding service...", flush=True)
    embedder = EmbeddingService()
    print(
        f"[pipeline] Embedding ready: device={embedder.device}, batch_size={embedder.batch_size}",
        flush=True,
    )

    chunk_buffer: list[Dict[str, Any]] = []
    text_buffer: list[str] = []
    total_documents = 0
    total_chunks = 0
    since_last_commit = 0

    def flush_buffers() -> None:
        nonlocal total_chunks, since_last_commit
        if not text_buffer:
            return

        embeddings = embedder.embed_texts(text_buffer)
        store.add(chunk_buffer, embeddings)
        total_chunks += len(chunk_buffer)
        since_last_commit += len(chunk_buffer)

        chunk_buffer.clear()
        text_buffer.clear()

        if since_last_commit >= commit_interval:
            store.commit()
            gc.collect()
            since_last_commit = 0

    doc_iter = iter_documents(
        metadata_limit=metadata_limit,
        content_limit=content_limit,
        content_batch_size=document_batch_size,
    )

    for document in doc_iter:
        total_documents += 1

        for idx, chunk_text in enumerate(split_text(document.text)):
            chunk_buffer.append(
                {
                    "chunk_id": f"{document.document_id}::chunk_{idx}",
                    "document_id": document.document_id,
                    "text": chunk_text,
                    "chunk_index": idx,
                    "metadata": document.metadata,
                }
            )
            text_buffer.append(chunk_text)

            if len(text_buffer) >= embedder.batch_size:
                flush_buffers()

        if progress_callback is not None:
            progress_callback(total_documents, total_chunks)

    flush_buffers()

    if total_chunks == 0:
        raise ValueError("Không tạo được chunk nào từ dataset.")

    store.save()
    gc.collect()
    return store


def ask_pipeline(question: str, top_k: Optional[int] = None) -> Dict[str, Any]:
    from .qa_service import QAService

    service = QAService()
    return service.ask(question=question, top_k=top_k)
