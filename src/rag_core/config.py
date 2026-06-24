from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
MODEL_DIR = PROJECT_ROOT / "models"
VECTOR_STORE_DIR = MODEL_DIR / "vector_store"


@dataclass(frozen=True)
class Settings:
    # Hugging Face dataset
    hf_dataset_name: str = os.getenv(
        "HF_DATASET_NAME", "th1nhng0/vietnamese-legal-documents"
    )
    hf_metadata_config: str = os.getenv("HF_METADATA_CONFIG", "metadata")
    hf_content_parquet_url: str = os.getenv(
        "HF_CONTENT_PARQUET_URL",
        "https://huggingface.co/datasets/th1nhng0/vietnamese-legal-documents/resolve/main/legacy/content.parquet",
    )

    # Text chunking
    chunk_size_chars: int = int(os.getenv("CHUNK_SIZE_CHARS", "1200"))
    chunk_overlap_chars: int = int(os.getenv("CHUNK_OVERLAP_CHARS", "200"))

    # Embedding model
    embedding_model_name: str = os.getenv(
        "EMBEDDING_MODEL_NAME",
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    )
    embedding_batch_size: int = int(os.getenv("EMBEDDING_BATCH_SIZE", "32"))

    # Retrieval
    top_k: int = int(os.getenv("TOP_K", "5"))

    # Storage
    vector_store_dir: Path = Path(
        os.getenv("VECTOR_STORE_DIR", str(VECTOR_STORE_DIR))
    )

    # Runtime
    device: str = os.getenv("DEVICE", "auto")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.vector_store_dir.mkdir(parents=True, exist_ok=True)
    return settings