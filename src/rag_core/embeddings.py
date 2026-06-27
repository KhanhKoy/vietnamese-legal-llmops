from __future__ import annotations

from typing import Any, Sequence

import numpy as np

from .config import get_settings


def _safe_print(message: object) -> None:
    try:
        print(message, flush=True)
    except UnicodeEncodeError:
        print(str(message).encode("ascii", errors="replace").decode("ascii"), flush=True)


class EmbeddingService:
    """
    CUDA embedding backend using HuggingFace Transformers directly.

    We intentionally do not import `sentence_transformers` here because it is
    crashing the user's Windows environment at native import time.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self.model_name = (
            settings.embedding_model_name
            or "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
        )
        self.device = "cuda"
        self.batch_size = self._resolve_batch_size(settings.embedding_batch_size)

        _safe_print("[embeddings] Importing torch backend...")
        import torch

        if not torch.cuda.is_available():
            raise RuntimeError(
                "CUDA is not available in this Python environment. "
                "Run: python -c \"import torch; print(torch.cuda.is_available())\""
            )

        _safe_print("[embeddings] Importing transformers backend...")
        from transformers import AutoModel, AutoTokenizer

        _safe_print(
            f"[embeddings] Loading tokenizer/model: {self.model_name} on {self.device}"
        )
        self.torch: Any = torch
        self.tokenizer: Any = AutoTokenizer.from_pretrained(self.model_name)
        self.model: Any = AutoModel.from_pretrained(self.model_name).to(self.device)
        self.model.eval()
        self._dimension: int = int(self.model.config.hidden_size)
        _safe_print(f"Dang su dung thiet bi: {self.device}")
        _safe_print(f"[embeddings] batch_size={self.batch_size}, dim={self._dimension}")

    def _resolve_batch_size(self, configured_batch_size: int) -> int:
        batch_size = max(1, int(configured_batch_size or 16))
        return min(batch_size, 32)

    def _encode_batch(self, texts: Sequence[str], batch_size: int) -> np.ndarray:
        all_embeddings: list[np.ndarray] = []

        for start in range(0, len(texts), batch_size):
            batch_texts = list(texts[start : start + batch_size])
            encoded = self.tokenizer(
                batch_texts,
                padding=True,
                truncation=True,
                max_length=512,
                return_tensors="pt",
            )
            encoded = {
                key: value.to(self.device)
                for key, value in encoded.items()
            }

            with self.torch.no_grad():
                outputs = self.model(**encoded)
                token_embeddings = outputs.last_hidden_state
                attention_mask = encoded["attention_mask"].unsqueeze(-1)
                attention_mask = attention_mask.expand(token_embeddings.size()).float()
                summed = (token_embeddings * attention_mask).sum(dim=1)
                counts = attention_mask.sum(dim=1).clamp(min=1e-9)
                embeddings = summed / counts
                embeddings = self.torch.nn.functional.normalize(
                    embeddings,
                    p=2,
                    dim=1,
                )

            all_embeddings.append(embeddings.detach().cpu().numpy())

        return np.vstack(all_embeddings).astype(np.float16)

    def embed_texts(self, texts: Sequence[str]) -> np.ndarray:
        texts_list = [str(text).strip() for text in texts if str(text).strip()]
        if not texts_list:
            return np.empty((0, self.dimension), dtype=np.float16)

        try:
            return self._encode_batch(texts_list, batch_size=self.batch_size)
        except RuntimeError as exc:
            if "out of memory" not in str(exc).lower():
                raise
            self.torch.cuda.empty_cache()
            safe_batch_size = max(1, self.batch_size // 2)
            _safe_print(
                f"[embeddings] CUDA OOM. Retrying with batch_size={safe_batch_size}"
            )
            return self._encode_batch(texts_list, batch_size=safe_batch_size)

    def embed_query(self, query: str) -> np.ndarray:
        query = (query or "").strip()
        if not query:
            return np.zeros(self.dimension, dtype=np.float16)
        return self.embed_texts([query])[0]

    @property
    def dimension(self) -> int:
        return self._dimension
