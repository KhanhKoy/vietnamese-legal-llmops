from __future__ import annotations

import gc
from typing import Any, Dict, Optional

from .chunking import split_text
from .dataset_reader import iter_documents
from .embeddings import EmbeddingService
from .vector_store import VectorStore


def build_index_pipeline(
    metadata_limit: Optional[int] = None,
    content_limit: Optional[int] = None,
    vector_store: Optional[VectorStore] = None,
    document_batch_size: int = 32,
    commit_interval: int = 100,
) -> VectorStore:
    """
    Build vector index with streaming to keep RAM usage bounded.

    Parameters
    ----------
    commit_interval:
        How often (in chunks) to commit the SQLite transaction and run GC
        to free WAL/journal memory.
    """
    store = vector_store or VectorStore()
    store.reset()
    embedder = EmbeddingService()

    chunk_buffer = []
    text_buffer = []
    total_chunks = 0
    since_last_commit = 0

    doc_iter = iter_documents(
        metadata_limit=metadata_limit,
        content_limit=content_limit,
        content_batch_size=document_batch_size,
    )

    for document in doc_iter:
        chunk_texts = split_text(document.text)

        for idx, chunk_text in enumerate(chunk_texts):
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
                embeddings = embedder.embed_texts(text_buffer)
                store.add(chunk_buffer, embeddings)
                total_chunks += len(chunk_buffer)
                since_last_commit += len(chunk_buffer)

                chunk_buffer.clear()
                text_buffer.clear()

                # Periodic flush to keep SQLite WAL memory down
                if since_last_commit >= commit_interval:
                    store.commit()
                    gc.collect()
                    since_last_commit = 0

    # --- Flush remaining buffer ---
    if text_buffer:
        embeddings = embedder.embed_texts(text_buffer)
        store.add(chunk_buffer, embeddings)
        total_chunks += len(chunk_buffer)

    if total_chunks == 0:
        raise ValueError("Không tạo được chunk nào từ dataset.")

    store.save()
    gc.collect()
    return store


def ask_pipeline(question: str, top_k: Optional[int] = None) -> Dict[str, Any]:
    from .qa_service import QAService

    service = QAService()
    return service.ask(question=question, top_k=top_k)
