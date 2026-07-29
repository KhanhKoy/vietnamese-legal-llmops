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
    # Hugging Face dataset sạch mới
    hf_dataset_name: str = os.getenv("HF_DATASET_NAME", "NguyenKH/clean_legal_knowledge")
    
    # Text chunking (Giữ kích thước chunk phù hợp với văn bản luật Markdown)
    chunk_size_chars: int = int(os.getenv("CHUNK_SIZE_CHARS", "1200"))
    chunk_overlap_chars: int = int(os.getenv("CHUNK_OVERLAP_CHARS", "200"))

    # Embedding model
    embedding_model_name: str = os.getenv(
        "EMBEDDING_MODEL_NAME",
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    )
    embedding_batch_size: int = int(os.getenv("EMBEDDING_BATCH_SIZE", "32"))

    # LLM Generator (Gemini)
    gemini_model_name: str = os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash")
    
    # Retrieval
    top_k: int = int(os.getenv("TOP_K", "5"))

    # Storage
    vector_store_dir: Path = Path(os.getenv("VECTOR_STORE_DIR", str(VECTOR_STORE_DIR)))

    # PostgreSQL settings for pgvector
    pg_database: str = os.getenv("PGDATABASE", "postgres")
    pg_user: str = os.getenv("PGUSER", "postgres")
    pg_password: str = os.getenv("PGPASSWORD", "password")
    pg_host: str = os.getenv("PGHOST", "localhost")
    pg_port: str = os.getenv("PGPORT", "5432")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.vector_store_dir.mkdir(parents=True, exist_ok=True)
    return settings