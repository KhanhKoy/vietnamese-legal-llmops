from __future__ import annotations

from typing import Any, Dict, List, Optional

from .config import get_settings
from .embeddings import EmbeddingService
from .vector_store import VectorStore


class Retriever:
    def __init__(
        self,
        vector_store: Optional[VectorStore] = None,
        embedder: Optional[EmbeddingService] = None,
    ) -> None:
        self.settings = get_settings()
        self.embedder = embedder or EmbeddingService()
        self.vector_store = vector_store or VectorStore()

    def _ensure_loaded(self) -> None:
        if self.vector_store.chunk_count == 0:
            self.vector_store.load()

    def retrieve(self, question: str, top_k: Optional[int] = None) -> List[Dict[str, Any]]:
        self._ensure_loaded()
        k = top_k or self.settings.top_k
        return self.vector_store.search(
            query=question,
            embedder=self.embedder,
            top_k=k,
        )

    @staticmethod
    def format_context(results: List[Dict[str, Any]]) -> str:
        blocks: List[str] = []

        for idx, result in enumerate(results, start=1):
            chunk = result.get("chunk", {})
            score = result.get("score", 0.0)

            document_id = chunk.get("document_id", "unknown")
            chunk_id = chunk.get("chunk_id", "unknown")
            text = chunk.get("text", "")

            blocks.append(
                f"[Nguồn {idx} | score={score:.4f} | doc={document_id} | chunk={chunk_id}]\n{text}"
            )

        return "\n\n---\n\n".join(blocks)

    def retrieve_with_context(
        self,
        question: str,
        top_k: Optional[int] = None,
    ) -> Dict[str, Any]:
        results = self.retrieve(question=question, top_k=top_k)
        context = self.format_context(results)

        return {
            "question": question,
            "top_k": top_k or self.settings.top_k,
            "results": results,
            "context": context,
        }
