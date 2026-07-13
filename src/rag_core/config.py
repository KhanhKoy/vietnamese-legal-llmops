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
    hf_dataset_name: str = os.getenv("HF_DATASET_NAME", "")  # Để trống mặc định để ưu tiên chạy Local Demo
    hf_metadata_config: str = os.getenv("HF_METADATA_CONFIG", "metadata")
    hf_content_parquet_url: str = os.getenv(
        "HF_CONTENT_PARQUET_URL",
        "https://huggingface.co/datasets/th1nhng0/vietnamese-legal-documents/resolve/main/legacy/content.parquet",
    )

    # Local Demo Path
    local_demo_path: str = os.getenv("LOCAL_DEMO_PATH", r"D:\Law-Chatbot\data_demo")

    # Text chunking
    chunk_size_chars: int = int(os.getenv("CHUNK_SIZE_CHARS", "1200"))
    chunk_overlap_chars: int = int(os.getenv("CHUNK_OVERLAP_CHARS", "200"))

    # Embedding model
    embedding_model_name: str = os.getenv(
        "EMBEDDING_MODEL_NAME",
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    )
    embedding_batch_size: int = int(os.getenv("EMBEDDING_BATCH_SIZE", "32"))

    # LLM Generator (AWS Bedrock)
    use_bedrock_llm: bool = os.getenv("USE_BEDROCK_LLM", "1").lower() in ("1", "true", "yes", "y")
    bedrock_llm_model: str = os.getenv("BEDROCK_LLM_MODEL", "anthropic.claude-3-sonnet-20240229-v1:0")

    # Cấu hình mặc định cho Gemini LLM
    gemini_model_name: str = os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash")
    
    # Retrieval
    top_k: int = int(os.getenv("TOP_K", "5"))

    # Storage
    vector_store_dir: Path = Path(os.getenv("VECTOR_STORE_DIR", str(VECTOR_STORE_DIR)))

    # Runtime
    device: str = os.getenv("DEVICE", "auto")

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