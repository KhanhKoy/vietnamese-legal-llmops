import os
from src.rag_core.pipeline import build_index_pipeline
from src.rag_core.vector_store import VectorStore
from src.rag_core.embeddings import EmbeddingService

if __name__ == "__main__":
    print("Starting test index build process...")

    embedder = EmbeddingService()
    store = VectorStore(embedder=embedder)
    # Clean up any previous database errors
    store.reset()

    # ONLY RUN TEST WITH FIRST 200 DOCUMENTS to test Parquet flow
    build_index_pipeline(
        content_limit=200,
        vector_store=store,
        embedder=embedder,
        document_batch_size=32,
        commit_interval=50
    )

    print("Test index build completed successfully! Please check the chatbot.")