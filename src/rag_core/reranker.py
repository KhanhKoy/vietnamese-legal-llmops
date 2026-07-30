from __future__ import annotations

import os
from typing import Any, Dict, List, Optional


class RerankerService:
    def __init__(self, model_name: str = "BAAI/bge-reranker-v2-m3") -> None:
        self.model_name = model_name
        self._model = None
        # Kiểm tra xem có bật Reranker qua biến môi trường không (mặc định BẬT)
        self.enabled = os.getenv("USE_RERANKER", "1").lower() in ("1", "true", "yes", "y")

    def _load_model(self) -> None:
        """Chỉ tải model vào RAM/GPU khi có truy vấn đầu tiên (Lazy Loading)."""
        if self._model is None and self.enabled:
            try:
                from sentence_transformers import CrossEncoder

                print(f"📦 [Reranker] Đang tải model Cross-Encoder: {self.model_name}...")
                self._model = CrossEncoder(self.model_name)
                print("✅ [Reranker] Tải model thành công!")
            except Exception as e:
                print(f"⚠️ [Reranker] Không thể tải model {self.model_name}: {e}")
                self.enabled = False

    def rerank(
        self,
        query: str,
        documents: List[Dict[str, Any]],
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Nhận vào câu hỏi và danh sách văn bản thô (Top 15-20),
        chấm điểm lại ngữ cảnh và trả về Top K chuẩn xác nhất.
        """
        if not documents or not query or not self.enabled:
            return documents[:top_k]

        try:
            self._load_model()

            if self._model is None:
                return documents[:top_k]

            # 1. Tạo các cặp (Câu hỏi, Nội dung đoạn luật)
            pairs = []
            for doc in documents:
                text = str(doc.get("text", "")).strip()
                pairs.append((query, text))

            # 2. Cross-Encoder tính toán điểm số tương quan
            scores = self._model.predict(pairs)

            # 3. Gán điểm rerank_score vào từng document
            reranked_docs = []
            for idx, doc in enumerate(documents):
                new_doc = dict(doc)
                new_doc["rerank_score"] = float(scores[idx])
                reranked_docs.append(new_doc)

            # 4. Sắp xếp lại danh sách theo điểm Rerank giảm dần
            reranked_docs.sort(key=lambda d: d.get("rerank_score", 0.0), reverse=True)

            print(f"🎯 [Reranker] Đã re-rank thành công {len(documents)} văn bản -> Chọn Top {top_k}")
            return reranked_docs[:top_k]

        except Exception as e:
            print(f"⚠️ [Reranker] Lỗi trong quá trình re-rank: {e}. Trả về kết quả gốc.")
            return documents[:top_k]