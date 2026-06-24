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
    parser = argparse.ArgumentParser(description="Build vector index from Hugging Face dataset.")
    parser.add_argument("--metadata-limit", type=int, default=None)
    parser.add_argument("--content-limit", type=int, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    store = build_index_pipeline(
        metadata_limit=args.metadata_limit,
        content_limit=args.content_limit,
    )
    print(f"Built vector store with {store.chunk_count} chunks.")


if __name__ == "__main__":
    main()
