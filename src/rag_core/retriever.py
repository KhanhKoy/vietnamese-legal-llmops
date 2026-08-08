from __future__ import annotations

import asyncio
import inspect
import re
from typing import Any, Dict, List, Optional

from .config import get_settings
from .embeddings import EmbeddingService
from .vector_store import VectorSearchError, VectorStore

VIETNAMESE_STOPWORDS = {
    "và", "hoặc", "là", "của", "cho", "với", "một", "những", "các", "theo",
    "trong", "khi", "nào", "ở", "đâu", "thì", "có", "không", "bị", "được",
    "phải", "nên", "về", "tại", "từ", "đến", "này", "đó", "kia", "ấy"
}


class Retriever:
    def __init__(
        self,
        vector_store: Optional[VectorStore] = None,
        embedder: Optional[EmbeddingService] = None,
    ) -> None:
        self.settings = get_settings()
        self.embedder = embedder or EmbeddingService()
        # Reuse one embedding model.  Loading a second SentenceTransformer here
        # wastes RAM/VRAM and makes the first request noticeably slower.
        self.vector_store = vector_store or VectorStore(embedder=self.embedder)

    def _ensure_loaded(self) -> None:
        # PostgreSQL is already queryable after the connection is opened.  A
        # COUNT(*) on every retrieval is expensive and does not "load" pgvector.
        if getattr(self.vector_store, "use_pgvector", False):
            return

        chunk_count = getattr(self.vector_store, "chunk_count", None)
        if chunk_count in (None, 0):
            load_fn = getattr(self.vector_store, "load", None)
            if callable(load_fn):
                load_fn()

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

    def _build_query_variants(self, question: str, max_variants: int = 4) -> List[str]:
        q = self._normalize_text(question)
        keywords = self._extract_keywords(q)

        variants = [q]

        if keywords:
            variants.append(" ".join(keywords[:12]))

        legal_boosters = [
            "điều khoản pháp luật",
            "quy định pháp luật",
            "căn cứ pháp lý",
            "nghị định thông tư luật",
        ]

        if any(term in q.lower() for term in ["điều", "khoản", "mục", "chương", "luật", "nghị định", "thông tư"]):
            variants.append(f"{q} {' '.join(legal_boosters)}")

        deduped: List[str] = []
        seen = set()
        for item in variants:
            item = self._normalize_text(item)
            if item and item not in seen:
                seen.add(item)
                deduped.append(item)

        return deduped[:max_variants]

    def _safe_float(self, value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
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

    async def _maybe_await(self, value: Any) -> Any:
        if inspect.isawaitable(value):
            return await value
        return value

    async def _call_store_method(self, method_name: str, query: str, top_k: int) -> List[Dict[str, Any]]:
        method = getattr(self.vector_store, method_name, None)
        if not callable(method):
            return []

        candidates = [
            {"query": query, "top_k": top_k, "embedder": self.embedder},
            {"query": query, "top_k": top_k},
            {"query": query, "k": top_k, "embedder": self.embedder},
            {"query": query, "k": top_k},
            {"query": query, "limit": top_k, "embedder": self.embedder},
            {"query": query, "limit": top_k},
            {"query": query, "embedder": self.embedder},
            {"query": query},
        ]

        for kwargs in candidates:
            try:
                # Pick the first compatible signature, then invoke it exactly
                # once. An empty result is a valid database response; retrying
                # the same query with seven argument variants multiplied RDS
                # timeouts and was a major cause of very slow answers.
                inspect.signature(method).bind(**kwargs)
            except TypeError:
                continue

            try:
                # Run synchronous store method in a thread to avoid blocking the event loop
                result = await asyncio.to_thread(method, **kwargs)
                return self._normalize_results(result)
            except VectorSearchError:
                raise
            except Exception as e:
                # 👈 Bổ sung print lỗi để không bị ẩn exception
                print(f"❌ [Retriever Error] Lỗi khi gọi {method_name}: {e}")
                return []

        return []

    def _merge_results(self, result_sets: List[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
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

    def _format_context(self, results: List[Dict[str, Any]]) -> str:
        blocks: List[str] = []

        for idx, result in enumerate(results, start=1):
            score = self._safe_float(result.get("score", result.get("_rank_score", 0.0)))
            text = str(result.get("text", "")).strip()
            metadata = result.get("metadata", {})

            title = metadata.get("title", "Không rõ tiêu đề")
            so_ky_hieu = metadata.get("so_ky_hieu", "N/A")
            loai_vb = metadata.get("loai_van_ban", "N/A")
            is_proc = metadata.get("is_procedural_law", False)
            proc_tag = " (Luật Tố tụng)" if is_proc else ""

            blocks.append(
                f"[Nguồn {idx} | Score={score:.4f} | Loại: {loai_vb}{proc_tag} | Số hiệu: {so_ky_hieu} | Tiêu đề: {title}]\n{text}"
            )

        return "\n\n---\n\n".join(blocks)

    def _keyword_query(self, question: str) -> str:
        keywords = self._extract_keywords(question)
        return " ".join(keywords[:16]) if keywords else self._normalize_text(question)

    async def retrieve(self, question: str, top_k: Optional[int] = None) -> List[Dict[str, Any]]:
        self._ensure_loaded()
        k = top_k or self.settings.top_k

        # Production/RDS fast path: one question -> one embedding -> one indexed
        # nearest-neighbour query.  The former generic fallback loop called five
        # overlapping methods for multiple query variants and also triggered
        # LOWER(text) LIKE '%...%' full-table scans.
        if getattr(self.vector_store, "use_pgvector", False):
            try:
                return self.vector_store.search(query=question, top_k=k)
            except Exception as e:
                print(f"❌ [Retriever PGVector Error]: {e}")
                return []

        query_variants = self._build_query_variants(question)
        keyword_query = self._keyword_query(question)

        result_sets: List[List[Dict[str, Any]]] = []

        preferred_methods = (
            "hybrid_search",
            "search",
            "retrieve",
            "query",
            "keyword_search",
        )

        for variant in query_variants:
            for method_name in preferred_methods:
                results = await self._call_store_method(method_name, variant, k)
                if results:
                    result_sets.append(results)

            if keyword_query and keyword_query != variant:
                for method_name in ("keyword_search", "search"):
                    results = await self._call_store_method(method_name, keyword_query, k)
                    if results:
                        result_sets.append(results)

        merged = self._merge_results(result_sets)
        return merged[:k]

    async def retrieve_with_context(
        self,
        question: str,
        top_k: Optional[int] = None,
    ) -> Dict[str, Any]:
        results = await self.retrieve(question=question, top_k=top_k)
        context = self._format_context(results)

        return {
            "question": question,
            "top_k": top_k or self.settings.top_k,
            "results": results,
            "context": context,
            "query_variants": self._build_query_variants(question),
            "keyword_query": self._keyword_query(question),
        }
