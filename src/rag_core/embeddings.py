from __future__ import annotations

import os
from typing import Any, Sequence

import numpy as np
import torch

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
            import boto3
            from botocore.config import Config

            self.region = os.getenv(
                "AWS_DEFAULT_REGION",
                getattr(self.settings, "aws_default_region", "us-east-1"),
            )
            self.model_id = os.getenv(
                "BEDROCK_EMBEDDING_MODEL",
                "amazon.titan-embed-text-v1",
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
            self._dim: int | None = None
        else:
            self.model_name = self.settings.embedding_model_name or "AITeamVN/Vietnamese_Embedding"
            requested_device = os.getenv("DEVICE", "auto").lower()
            self.device = (
                requested_device
                if requested_device in {"cpu", "cuda"}
                else ("cuda" if torch.cuda.is_available() else "cpu")
            )
            
            # Chạy local bằng AutoModel & AutoTokenizer (dùng use_fast=False chống crash Windows)
            from transformers import AutoModel, AutoTokenizer

            self.tokenizer = AutoTokenizer.from_pretrained(self.model_name, use_fast=False)
            self.model = AutoModel.from_pretrained(self.model_name)
            self.model.to(self.device)
            self.model.eval()

            self._dim: int | None = getattr(self.model.config, "hidden_size", 768)

    def _ensure_dim(self, length: int) -> None:
        if self._dim is None:
            self._dim = length

    def _mean_pooling(self, model_output: Any, attention_mask: torch.Tensor) -> torch.Tensor:
        token_embeddings = model_output[0]
        input_mask_expanded = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
        sum_embeddings = torch.sum(token_embeddings * input_mask_expanded, 1)
        sum_mask = torch.clamp(input_mask_expanded.sum(1), min=1e-9)
        return sum_embeddings / sum_mask

    def _embed_via_bedrock(self, texts: list[str]) -> list[list[float]]:
        import json

        embeddings: list[list[float]] = []
        for txt in texts:
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

    def _embed_via_transformers(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, self.dimension), dtype=np.float32)

        all_embeddings = []
        batch_size = max(1, self.batch_size)
        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i : i + batch_size]
            encoded_input = self.tokenizer(
                batch_texts,
                padding=True,
                truncation=True,
                max_length=512,
                return_tensors="pt",
            ).to(self.device)

            with torch.no_grad():
                model_output = self.model(**encoded_input)
                sentence_embeddings = self._mean_pooling(model_output, encoded_input["attention_mask"])
                sentence_embeddings = torch.nn.functional.normalize(sentence_embeddings, p=2, dim=1)
                all_embeddings.append(sentence_embeddings.cpu().numpy())

        res = np.vstack(all_embeddings).astype(np.float32)
        self._ensure_dim(res.shape[1])
        return res

    def embed_texts(self, texts: Sequence[str]) -> np.ndarray:
        texts_list = [str(t).strip() for t in texts]
        if not texts_list:
            return np.empty((0, self.dimension), dtype=np.float32)

        if self.use_bedrock:
            raw_embeds = self._embed_via_bedrock(list(texts_list))
            arr = np.asarray(raw_embeds, dtype=np.float32)
        else:
            arr = self._embed_via_transformers(list(texts_list))

        if self._dim is None:
            self._dim = arr.shape[1]
        return np.asarray(arr, dtype=np.float32)

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        return self.embed_texts(texts)

    def embed_query(self, query: str) -> np.ndarray:
        query = (query or "").strip()
        if not query:
            return np.zeros(self.dimension, dtype=np.float32)

        if self.use_bedrock:
            raw = self._embed_via_bedrock([query])[0]
            vec = np.asarray(raw, dtype=np.float32)
        else:
            vec = self._embed_via_transformers([query])[0]

        if self._dim is None:
            self._dim = len(vec)
        return np.asarray(vec, dtype=np.float32)

    @property
    def dimension(self) -> int:
        if self._dim is None:
            dummy_vec = self.embed_query("dummy")
            self._dim = len(dummy_vec)
        return int(self._dim)