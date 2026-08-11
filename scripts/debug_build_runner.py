from __future__ import annotations

import sys
import traceback
from pathlib import Path

# Add project root and src to sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

OUTPUT = Path("debug_build_output.log")

def main() -> None:
    with OUTPUT.open("w", encoding="utf-8") as f:
        try:
            f.write(f"cwd={PROJECT_ROOT}\n")
            f.write(f"sys.path={sys.path}\n")
            f.write("\n--- IMPORTING build_index_pipeline ---\n")
            from src.rag_core.pipeline import build_index_pipeline
            f.write("Imported build_index_pipeline\n")

            f.write("\n--- RUNNING build_index_pipeline(content_limit=5) ---\n")
            store = build_index_pipeline(content_limit=5)
            f.write(f"Returned store: {repr(store)}\n")
            try:
                f.write(f"store.chunk_count={getattr(store, 'chunk_count', None)}\n")
            except Exception as e:
                f.write(f"Error accessing store.chunk_count: {e}\n")

            if store is not None:
                try:
                    store.close()
                    f.write("Closed store successfully\n")
                except Exception as e:
                    f.write(f"Error closing store: {e}\n")

        except Exception:
            f.write("\n--- EXCEPTION TRACEBACK ---\n")
            traceback.print_exc(file=f)

    print(f"WROTE {OUTPUT}")

if __name__ == '__main__':
    main()
