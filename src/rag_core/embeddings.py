from __future__ import annotations

from typing import Any, Sequence

import numpy as np
from sentence_transformers import SentenceTransformer

from .config import get_settings


class EmbeddingService:
    def __init__(self) -> None:
        import torch # Khai báo torch để kiểm tra GPU
        settings = get_settings()
        self.model_name = settings.embedding_model_name or "AITeamVN/Vietnamese_Embedding"
        self.batch_size = settings.embedding_batch_size
        
        # Tự động chọn 'cuda' nếu môi trường (Kaggle/PC) có GPU, ngược lại dùng 'cpu'
        device = "cuda" if torch.cuda.is_available() else "cpu"
        
        # Truyền thêm tham số device vào đây
        self.model: Any = SentenceTransformer(self.model_name, device=device)

    def embed_texts(self, texts: Sequence[str]) -> np.ndarray:
        texts_list = [str(text).strip() for text in texts]
        if not texts_list:
            return np.empty((0, self.dimension), dtype=np.float16)

        embeddings = self.model.encode(
            texts_list,
            batch_size=self.batch_size,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return np.asarray(embeddings, dtype=np.float16)

    def embed_query(self, query: str) -> np.ndarray:
        query = (query or "").strip()
        if not query:
            return np.zeros(self.dimension, dtype=np.float16)

        embedding = self.model.encode(
            [query],
            batch_size=1,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return np.asarray(embedding[0], dtype=np.float16)

    @property
    def dimension(self) -> int:
        getter = getattr(self.model, "get_sentence_embedding_dimension", None)
        if getter is None:
            raise AttributeError("Embedding model không hỗ trợ get_sentence_embedding_dimension().")
        return int(getter())