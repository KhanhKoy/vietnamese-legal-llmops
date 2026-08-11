from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
SRC_ROOT = ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ENV_KEYS = [
    "LOCAL_DEMO_PATH",
    "HF_DATASET_NAME",
    "USE_PGVECTOR",
    "PGHOST",
    "PGPORT",
    "PGDATABASE",
    "PGUSER",
    "PGPASSWORD",
]


def load_environment(env_path: Path) -> Dict[str, Optional[str]]:
    if env_path.exists():
        load_dotenv(env_path)
    return {key: os.getenv(key) for key in ENV_KEYS}


def print_heading(title: str) -> None:
    print("\n" + "#" * 5 + " " + title + " " + "#" * 5)


def check_env_file(env_path: Path) -> None:
    print_heading("ENVIRONMENT CONFIGURATION")
    print(f".env path: {env_path}")
    print(f".env exists: {env_path.exists()}")
    env_values = load_environment(env_path)
    for key, value in env_values.items():
        print(f"{key}={value}")

    if env_values.get("USE_PGVECTOR", "false").lower() in ("1", "true", "yes", "y"):
        print("USE_PGVECTOR is enabled. The pipeline will try to use PostgreSQL + pgvector.")
    else:
        print("USE_PGVECTOR is disabled. The pipeline will use local FAISS/SQLite storage.")


def check_data_demo(data_demo_dir: Path) -> None:
    print_heading("DATA DIRECTORY")
    print(f"data_demo path: {data_demo_dir}")
    print(f"exists: {data_demo_dir.exists()}")
    if data_demo_dir.exists():
        files: List[Path] = [p for p in data_demo_dir.iterdir() if p.is_file()]
        print(f"files count: {len(files)}")
        for file in files:
            print(f"- {file.name} ({file.stat().st_size} bytes)")
    if not data_demo_dir.exists() or not any(data_demo_dir.iterdir()):
        print("WARNING: data_demo/ is empty or missing. The current pipeline reads HuggingFace dataset and may not use local files.")


def check_vector_store_dir(store_dir: Path) -> None:
    print_heading("VECTOR STORE DIRECTORY")
    print(f"vector_store dir: {store_dir}")
    print(f"exists: {store_dir.exists()}")
    try:
        store_dir.mkdir(parents=True, exist_ok=True)
        print("Directory creation OK.")
        test_file = store_dir / ".write_test"
        with test_file.open("w", encoding="utf-8") as f:
            f.write("ok")
        test_file.unlink(missing_ok=True)
        print("Write permission OK.")
    except Exception as exc:
        print(f"ERROR: cannot create/write in vector_store directory: {exc}")


def check_imports() -> None:
    print_heading("IMPORT CHECK")
    try:
        import src.rag_core.pipeline  # noqa: F401
        from src.rag_core.pipeline import build_index_pipeline  # noqa: F401
        print("SUCCESS: Imported src.rag_core.pipeline and build_index_pipeline.")
    except Exception:
        print("ERROR: Import failed.")
        traceback.print_exc()


def check_pgvector_package() -> None:
    print_heading("PGVECTOR / POSTGRES PACKAGE CHECK")
    try:
        import psycopg  # noqa: F401
        print("SUCCESS: psycopg is installed.")
    except ModuleNotFoundError as exc:
        print(f"MISSING PACKAGE: {exc}")
        print("Install with: pip install psycopg[binary]")
    except Exception:
        print("ERROR importing psycopg.")
        traceback.print_exc()
    try:
        import pgvector  # noqa: F401
        print("SUCCESS: pgvector is installed.")
    except ModuleNotFoundError as exc:
        print(f"MISSING PACKAGE: {exc}")
        print("Install with: pip install pgvector")
    except Exception:
        print("ERROR importing pgvector.")
        traceback.print_exc()


def run_build_pipeline(content_limit: int = 1) -> None:
    print_heading("BUILD INDEX PIPELINE TEST")
    try:
        from src.rag_core.pipeline import build_index_pipeline
    except Exception:
        print("ERROR: Could not import build_index_pipeline.")
        traceback.print_exc()
        return

    try:
        store = build_index_pipeline(content_limit=content_limit)
        print("SUCCESS: build_index_pipeline returned a store object.")
        print(f"store: {store}")
        if hasattr(store, "chunk_count"):
            print(f"store.chunk_count={getattr(store, 'chunk_count')}")
        try:
            store.close()
            print("Closed store successfully.")
        except Exception as exc:
            print(f"WARNING: Error closing store: {exc}")
    except Exception as exc:
        print(f"ERROR: build_index_pipeline failed: {exc}")
        traceback.print_exc()
        if os.getenv("USE_PGVECTOR", "0").lower() in ("1", "true", "yes", "y"):
            print("NOTE: USE_PGVECTOR is enabled. If PostgreSQL is unavailable or psycopg is missing, set USE_PGVECTOR=false to use local FAISS/SQLite.")


def main() -> None:
    env_path = ROOT / ".env"
    data_demo_dir = ROOT / "data_demo"
    vector_store_dir = ROOT / "models" / "vector_store"

    check_env_file(env_path)
    check_data_demo(data_demo_dir)
    check_vector_store_dir(vector_store_dir)
    check_imports()

    if os.getenv("USE_PGVECTOR", "0").lower() in ("1", "true", "yes", "y"):
        check_pgvector_package()

    run_build_pipeline(content_limit=1)

    print_heading("CONCLUSION")
    print("- Nếu bạn cần chạy local mà không có RDS, đặt USE_PGVECTOR=false trong .env và khởi động lại.")
    print("- Nếu bạn muốn dùng RDS/pgvector, đảm bảo psycopg và pgvector được cài đặt và kết nối đến PGHOST/PGPORT/PGDATABASE.")
    print("- Kiểm tra file debug_build_output.log nếu cần log chi tiết hơn.")


if __name__ == "__main__":
    main()
