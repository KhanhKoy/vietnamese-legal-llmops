from __future__ import annotations

import gc
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
    commit_interval: int = 100,
) -> VectorStore:
    """
    Build vector index with streaming to keep RAM usage bounded.

    Parameters
    ----------
    embedder:
        EmbeddingService instance to use for creating embeddings. If not provided,
        one will be created (either from the vector_store if it has one, or a new one).
    commit_interval:
        How often (in chunks) to commit the SQLite transaction and run GC
        to free WAL/journal memory.
    """
    # Determine embedder to use
    if embedder is None:
        # If vector_store provided and has an embedder attribute, use it
        if vector_store is not None and hasattr(vector_store, "embedder") and vector_store.embedder is not None:
            embedder = vector_store.embedder
        else:
            embedder = EmbeddingService()
    else:
        # embedder provided
        pass

    # Create vector store if not provided
    if vector_store is None:
        store = VectorStore(embedder=embedder)
    else:
        store = vector_store
        # Ensure the store uses the embedder we decided upon
        store.embedder = embedder
        store.embed_dim = embedder.dimension

    store.reset()

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
        doc_chunks = chunk_document(document)

        for chunk in doc_chunks:
            chunk_buffer.append(chunk)
            text_buffer.append(chunk.text)

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
                    # gc.collect()  # Removed as per original code comment
                    since_last_commit = 0

    # --- Flush remaining buffer ---
    if text_buffer:
        embeddings = embedder.embed_texts(text_buffer)
        store.add(chunk_buffer, embeddings)
        total_chunks += len(chunk_buffer)

    if total_chunks == 0:
        raise ValueError("Không tạo được chunk nào từ dataset.")

    store.save()
    # gc.collect()  # Removed as per original code comment
    return store


async def ask_pipeline(question: str, top_k: Optional[int] = None) -> Dict[str, Any]:
    from .qa_service import QAService

    service = QAService()
    return await service.ask(question=question, top_k=top_k)
