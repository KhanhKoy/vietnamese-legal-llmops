from __future__ import annotations

import os
from typing import Any, Sequence

import numpy as np

from .config import get_settings


class EmbeddingService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.batch_size = self.settings.embedding_batch_size
        self.use_bedrock = (
            os.getenv("USE_BEDROCK_EMBEDDING", "0").lower()
            in ("1", "true", "yes", "y")
        )
        if self.use_bedrock:
            # Lazy import boto3 to avoid hard dependency when not used
            import boto3
            from botocore.config import Config

            # Region can be overridden via env; otherwise default from settings or us-east-1
            self.region = os.getenv(
                "AWS_DEFAULT_REGION",
                getattr(self.settings, "aws_default_region", "us-east-1"),
            )
            # Model ID can be overridden via env
            self.model_id = os.getenv(
                "BEDROCK_EMBEDDING_MODEL",
                "amazon.titan-embed-text-v1",  # default Titan Text Embedding v1
            )
            boto_config = Config(
                retries={"max_attempts": 5, "mode": "standard"},
                connect_timeout=int(os.getenv("AWS_CONNECT_TIMEOUT_SECONDS", "5")),
                read_timeout=int(os.getenv("AWS_READ_TIMEOUT_SECONDS", "30")),
            )
            self._client = boto3.client(
                service_name="bedrock-runtime",
                region_name=self.region,
                config=boto_config,
            )
            self._dim: int | None = None  # will be determined on first embed
        else:
            # Local sentence‑transformers path
            import torch  # noqa: F401

            self.model_name = self.settings.embedding_model_name
            requested_device = os.getenv("DEVICE", "auto").lower()
            device = (
                requested_device
                if requested_device in {"cpu", "cuda"}
                else ("cuda" if torch.cuda.is_available() else "cpu")
            )
            from sentence_transformers import SentenceTransformer

            self.model: Any = SentenceTransformer(self.model_name, device=device)
            self._dim: int | None = None  # will be determined on first embed

    # -----------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------
    def _ensure_dim(self, length: int) -> None:
        if self._dim is None:
            self._dim = length

    def _embed_via_bedrock(self, texts: list[str]) -> list[list[float]]:
        """Call Bedrock Titan Embedding for each text (serial)."""
        import json

        embeddings: list[list[float]] = []
        for txt in texts:
            # Titan accepts up to ~8192 tokens; we truncate to be safe
            body = {"inputText": txt[:8000]}
            response = self._client.invoke_model(
                body=json.dumps(body),
                modelId=self.model_id,
                accept="application/json",
                contentType="application/json",
            )
            response_body = json.loads(response["body"].read())
            embedding = response_body.get("embedding")
            if embedding is None:
                raise RuntimeError("Bedrock returned empty embedding")
            self._ensure_dim(len(embedding))
            embeddings.append(embedding)
        return embeddings

    def _embed_via_st(self, texts: list[str]) -> np.ndarray:
        embeddings = self.model.encode(
            texts,
            batch_size=self.batch_size,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return np.asarray(embeddings, dtype=np.float32)

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------
    def embed_texts(self, texts: Sequence[str]) -> np.ndarray:
        texts_list = [str(t).strip() for t in texts]
        if not texts_list:
            return np.empty((0, self.dimension), dtype=np.float32)

        if self.use_bedrock:
            raw_embeds = self._embed_via_bedrock(list(texts_list))
            arr = np.asarray(raw_embeds, dtype=np.float32)
        else:
            arr = self._embed_via_st(list(texts_list))

        # Ensure dimension known
        if self._dim is None:
            self._dim = arr.shape[1]
        # Convert to float32 to match original storage format
        return np.asarray(arr, dtype=np.float32)

    def embed_query(self, query: str) -> np.ndarray:
        query = (query or "").strip()
        if not query:
            return np.zeros(self.dimension, dtype=np.float32)

        if self.use_bedrock:
            raw = self._embed_via_bedrock([query])[0]
            vec = np.asarray(raw, dtype=np.float32)
        else:
            vec = self.model.encode(
                [query],
                batch_size=1,
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            )[0]

        if self._dim is None:
            self._dim = len(vec)
        return np.asarray(vec, dtype=np.float32)

    @property
    def dimension(self) -> int:
        if self._dim is None:
            # Trigger a dummy embed to initialise dimension
            dummy_vec = self.embed_query("dummy")
            self._dim = len(dummy_vec)
        return int(self._dim)
