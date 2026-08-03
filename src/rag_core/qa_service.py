from __future__ import annotations

import asyncio
import inspect
import os
import re
import time
from typing import Any, Dict, List, Optional

from .generator import GeneratorService
from .prompt import build_prompt
from .reranker import RerankerService  # 👈 Import RerankerService mới
from .retriever import Retriever
from .vector_store import VectorIndexMissingError, VectorSearchError, VectorSearchTimeoutError

VIETNAMESE_STOPWORDS = {
    "và", "hoặc", "là", "của", "cho", "với", "một", "những", "các", "theo",
    "trong", "khi", "nào", "ở", "đâu", "thì", "có", "không", "bị", "được",
    "phải", "nên", "về", "tại", "từ", "đến", "này", "đó", "kia", "ấy"
}


class QAService:
    def __init__(
        self,
        retriever: Optional[Retriever] = None,
        generator: Optional[GeneratorService] = None,
        reranker: Optional[RerankerService] = None,  # 👈 Bổ sung tham số reranker
    ) -> None:
        self.retriever = retriever or Retriever()
        self.generator = generator or GeneratorService()
        self.reranker = reranker or RerankerService()  # 👈 Khởi tạo Reranker
        self.enable_query_rewrite = os.getenv("ENABLE_QUERY_REWRITE", "0").lower() in (
            "1", "true", "yes", "y"
        )
        self.llm_timeout_seconds = float(os.getenv("LLM_TIMEOUT_SECONDS", "45"))
        self.retrieval_timeout_seconds = float(os.getenv("RETRIEVAL_TIMEOUT_SECONDS", "15"))

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

    def _build_query_variants(self, question: str) -> List[str]:
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

        if any(
            term in q.lower()
            for term in ["điều", "khoản", "mục", "chương", "luật", "nghị định", "thông tư"]
        ):
            variants.append(f"{q} {' '.join(legal_boosters)}")

        deduped: List[str] = []
        seen = set()
        for item in variants:
            item = self._normalize_text(item)
            if item and item not in seen:
                seen.add(item)
                deduped.append(item)

        return deduped[:4]

    async def _maybe_await(self, value: Any) -> Any:
        if inspect.isawaitable(value):
            return await value
        return value

    async def _safe_generate(self, prompt: str, default: str = "") -> str:
        generate_fn = getattr(self.generator, "generate", None)
        if not callable(generate_fn):
            return default

        try:
            if inspect.iscoroutinefunction(generate_fn):
                result = await asyncio.wait_for(
                    generate_fn(prompt), timeout=self.llm_timeout_seconds
                )
            else:
                # google-genai is synchronous in this project. Run it outside
                # Chainlit's event loop and bound the user's waiting time.
                result = await asyncio.wait_for(
                    asyncio.to_thread(generate_fn, prompt),
                    timeout=self.llm_timeout_seconds,
                )
                result = await self._maybe_await(result)
            text = self._normalize_text(str(result))
            return text or default
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

    def _safe_float(self, value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except Exception:
            return default

    def _normalize_retrieval(self, retrieval: Any, top_k: int) -> Dict[str, Any]:
        if isinstance(retrieval, dict):
            results = retrieval.get("results") or retrieval.get("documents") or []
            context = retrieval.get("context", "")
            return {
                "results": results if isinstance(results, list) else [],
                "context": context,
                "top_k": retrieval.get("top_k", top_k),
            }

        if isinstance(retrieval, list):
            return {"results": retrieval, "context": "", "top_k": top_k}

        return {"results": [], "context": "", "top_k": top_k}

    async def _retrieve(self, query: str, top_k: int) -> Dict[str, Any]:
        method_names = (
            "retrieve_with_context",
            "retrieve",
            "search",
            "query",
        )

        for method_name in method_names:
            method = getattr(self.retriever, method_name, None)
            if not callable(method):
                continue

            try:
                try:
                    result = method(query, top_k=top_k)
                except TypeError:
                    result = method(query)

                result = await self._maybe_await(result)
                normalized = self._normalize_retrieval(result, top_k)
                # A successful empty response is final. Calling another alias
                # on the same retriever would execute the same RDS query again.
                return normalized
            except VectorSearchError:
                raise
            except Exception:
                continue

        return {"results": [], "context": "", "top_k": top_k}

    def _merge_results(self, retrievals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        merged: Dict[str, Dict[str, Any]] = {}

        for retrieval in retrievals:
            results = retrieval.get("results", []) or []
            for idx, doc in enumerate(results):
                if not isinstance(doc, dict):
                    continue

                fp = self._doc_fingerprint(doc)
                current = merged.get(fp)

                doc_score = self._safe_float(doc.get("score", 0.0))
                if doc_score <= 0.0:
                    doc_score = 1.0 / (idx + 1)

                if current is None:
                    new_doc = dict(doc)
                    new_doc["_rank_score"] = doc_score
                    merged[fp] = new_doc
                    continue

                current_score = self._safe_float(current.get("_rank_score", current.get("score", 0.0)))
                if doc_score > current_score:
                    new_doc = dict(doc)
                    new_doc["_rank_score"] = doc_score
                    merged[fp] = new_doc

        return sorted(
            merged.values(),
            key=lambda d: self._safe_float(d.get("_rank_score", d.get("score", 0.0))),
            reverse=True,
        )

    def _broaden_question(self, question: str) -> str:
        q = self._normalize_text(question)
        q = re.sub(r"\b(mục|điều|khoản|chương)\s*\d+\b", "", q, flags=re.IGNORECASE)
        q = re.sub(r"\b(số|no\.?)\s*\d+\b", "", q, flags=re.IGNORECASE)
        q = self._normalize_text(q)
        keywords = self._extract_keywords(q)
        return " ".join(keywords[:12]) if keywords else q

    async def ask(self, question: str, top_k: Optional[int] = None) -> Dict[str, Any]:
        started_at = time.perf_counter()
        top_k = top_k or 5
        question = self._normalize_text(question)

        # 🌟 Lấy số lượng ứng viên rộng hơn (Top 15 - 20) để Reranker đánh giá
        candidate_k = (
            max(top_k * 3, 15) if getattr(self.reranker, "enabled", False) else top_k
        )

        # Keep the default path deliberately small. Query expansion can improve
        # recall, but must be opt-in because each variant is another embedding
        # and database round trip.
        variants = [question]
        broadened = self._broaden_question(question)

        optimized_query = ""
        if self.enable_query_rewrite:
            rewrite_prompt = (
                "Bạn là chuyên gia ngôn ngữ pháp luật. Hãy chuyển câu hỏi dưới đây "
                "thành một câu tra cứu ngắn, giữ nguyên ý nghĩa pháp lý. Chỉ trả về "
                "câu tra cứu, không giải thích.\n\n"
                f"Câu hỏi: {question}\nCâu tra cứu:"
            )
            optimized_query = await self._safe_generate(rewrite_prompt, default="")
            if optimized_query and optimized_query not in variants:
                variants.append(optimized_query)

        retrievals: List[Dict[str, Any]] = []
        for variant in variants:
            try:
                retrieval = await asyncio.wait_for(
                    self._retrieve(variant, top_k=candidate_k),
                    timeout=self.retrieval_timeout_seconds,
                )
            except VectorIndexMissingError:
                return self._retrieval_error_response(
                    question,
                    top_k,
                    variants,
                    optimized_query or broadened,
                    "VECTOR_INDEX_MISSING",
                    "Cơ sở dữ liệu chưa có HNSW/IVFFlat index hợp lệ nên tra cứu vector đã bị tạm dừng.",
                    started_at,
                )
            except VectorSearchTimeoutError:
                return self._retrieval_error_response(
                    question,
                    top_k,
                    variants,
                    optimized_query or broadened,
                    "VECTOR_SEARCH_TIMEOUT",
                    "Truy vấn cơ sở dữ liệu đã quá thời gian cho phép. Vui lòng thử lại sau.",
                    started_at,
                )
            except asyncio.TimeoutError:
                retrieval = {"results": [], "context": "", "top_k": candidate_k}
            if retrieval.get("results"):
                retrievals.append(retrieval)

        merged_results = self._merge_results(retrievals)

        # Fallback search nếu chưa ra kết quả
        if not merged_results and broadened:
            try:
                fallback = await asyncio.wait_for(
                    self._retrieve(broadened, top_k=candidate_k * 2),
                    timeout=self.retrieval_timeout_seconds,
                )
            except asyncio.TimeoutError:
                fallback = {"results": [], "context": "", "top_k": candidate_k * 2}
            if fallback.get("results"):
                merged_results = fallback.get("results", [])

        # 🎯 CHUẨN HÓA CÂU TRẢ LỜI KHI KHÔNG TÌM THẤY THÔNG TIN
        if not merged_results:
            fallback_answer = "Hiện không có thông tin về nội dung tìm kiếm trong cơ sở dữ liệu."
            return {
                "question": question,
                "answer": fallback_answer,
                "top_k": top_k,
                "results": [],
                "context": "",
                "prompt": "",
                "query_variants": variants,
                "optimized_query": optimized_query or broadened,
                "latency_ms": round((time.perf_counter() - started_at) * 1000, 2),
            }

        # 🌟 ĐIỂM NÂNG CẤP MỚI: Tiến hành Re-rank danh sách ứng viên thu được
        final_results = await asyncio.to_thread(
            self.reranker.rerank,
            query=question,
            documents=merged_results,
            top_k=top_k,
        )

        prompt = build_prompt(question, final_results)
        answer = await self._safe_generate(prompt, default="")

        if not self._normalize_text(answer):
            answer = "Hiện không có thông tin về nội dung tìm kiếm trong cơ sở dữ liệu."

        response = {
            "question": question,
            "answer": answer,
            "top_k": top_k,
            "results": final_results,
            "context": "\n\n".join(str(d.get("text", "")).strip() for d in final_results),
            "prompt": prompt,
            "query_variants": variants,
            "optimized_query": optimized_query or broadened,
            "latency_ms": round((time.perf_counter() - started_at) * 1000, 2),
        }
        # ASCII log prefix also works on Windows consoles configured with cp1252.
        print(f"[QA] total_latency_ms={response['latency_ms']}")
        return response

    @staticmethod
    def _retrieval_error_response(
        question: str,
        top_k: int,
        variants: List[str],
        optimized_query: str,
        error_code: str,
        message: str,
        started_at: float,
    ) -> Dict[str, Any]:
        return {
            "question": question,
            "answer": message,
            "top_k": top_k,
            "results": [],
            "context": "",
            "prompt": "",
            "query_variants": variants,
            "optimized_query": optimized_query,
            "error_code": error_code,
            "latency_ms": round((time.perf_counter() - started_at) * 1000, 2),
        }
