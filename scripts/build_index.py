from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from rag_core.pipeline import build_index_pipeline  # noqa: E402


def parse_args() -> argparse.Namespace:
    # Cập nhật lại description cho đúng thực tế hệ thống (chạy được cả dữ liệu local demo)
    parser = argparse.ArgumentParser(description="Build vector index from Dataset (Hugging Face or Local Demo).")
    parser.add_argument("--metadata-limit", type=int, default=None)
    parser.add_argument("--content-limit", type=int, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    store = None
    try:
        # Chạy pipeline nạp dữ liệu và sinh vector index
        store = build_index_pipeline(
            metadata_limit=args.metadata_limit,
            content_limit=args.content_limit,
        )
        print(f"Built vector store successfully with {store.chunk_count} chunks.")
    except Exception as e:
        print(f"Error during index building: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        # Đảm bảo ngắt kết nối database an toàn kể cả khi script chạy thành công hay gặp lỗi
        if store is not None:
            store.close()
            print("Database connection closed cleanly.")


if __name__ == "__main__":
    main()