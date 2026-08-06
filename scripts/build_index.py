from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Thêm cả PROJECT_ROOT và SRC_ROOT vào sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from src.rag_core.pipeline import build_index_pipeline  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build vector index từ Dataset Hugging Face / Parquet Sạch lên AWS RDS PostgreSQL.")
    parser.add_argument("--metadata-limit", type=int, default=None, help="Giới hạn số lượng metadata cần đọc")
    parser.add_argument("--content-limit", type=int, default=None, help="Giới hạn số lượng văn bản nạp để test")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    store = None
    try:
        print("🚀 Bắt đầu quá trình Build Vector Index...")
        store = build_index_pipeline(
            metadata_limit=args.metadata_limit,
            content_limit=args.content_limit,
        )
        print(f"🎉 Build vector store hoàn tất thành công! Tổng số chunks đã nạp: {store.chunk_count}")
    except Exception as e:
        print(f"❌ Lỗi trong quá trình build index: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        if store is not None:
            store.close()
            print("🔒 Đã đóng kết nối Cơ sở dữ liệu an toàn.")


if __name__ == "__main__":
    main()
