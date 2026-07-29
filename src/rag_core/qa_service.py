from __future__ import annotations

import inspect
import re
from typing import Any, Dict, List, Optional

from .generator import GeneratorService
from .prompt import build_prompt
from .retriever import Retriever


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
    ) -> None:
        self.retriever = retriever or Retriever()
        self.generator = generator or GeneratorService()

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
            result = generate_fn(prompt)
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
                if normalized["results"]:
                    return normalized
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
        top_k = top_k or 5
        question = self._normalize_text(question)

        variants = self._build_query_variants(question)
        broadened = self._broaden_question(question)
        if broadened and broadened not in variants:
            variants.append(broadened)

        # 🚀 Tối ưu hóa truy vấn bằng Gemini LLM
        rewrite_prompt = (
            f"Bạn là chuyên gia ngôn ngữ pháp luật. Hãy chuyển đổi câu hỏi dưới đây thành một câu khẳng định ngắn gọn, "
            f"chứa các từ khóa học thuật chính xác theo văn phong văn bản luật Việt Nam để phục vụ tra cứu.\n"
            f"Chỉ trả ra đúng câu văn sau khi chuyển đổi, không giải thích gì thêm.\n\n"
            f"Câu hỏi người dùng: {question}\n"
            f"Câu tra cứu chuẩn hóa:"
        )
        optimized_query = await self._safe_generate(rewrite_prompt, default="")
        if optimized_query and optimized_query not in variants:
            variants.append(optimized_query)

        retrievals: List[Dict[str, Any]] = []
        for variant in variants:
            retrieval = await self._retrieve(variant, top_k=top_k)
            if retrieval.get("results"):
                retrievals.append(retrieval)

        merged_results = self._merge_results(retrievals)

        # Fallback search nếu chưa ra kết quả
        if not merged_results and broadened:
            fallback = await self._retrieve(broadened, top_k=top_k * 2)
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
            }

        prompt = build_prompt(question, merged_results[:top_k])
        answer = await self._safe_generate(prompt, default="")
        
        if not self._normalize_text(answer):
            answer = "Hiện không có thông tin về nội dung tìm kiếm trong cơ sở dữ liệu."

        return {
            "question": question,
            "answer": answer,
            "top_k": top_k,
            "results": merged_results[:top_k],
            "context": "\n\n".join(str(d.get("text", "")).strip() for d in merged_results[:top_k]),
            "prompt": prompt,
            "query_variants": variants,
            "optimized_query": optimized_query or broadened,
        }