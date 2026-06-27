from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CHUNKS_DB = PROJECT_ROOT / "models" / "indexing" / "chunks.sqlite3"
DEFAULT_VECTOR_DIR = PROJECT_ROOT / "models" / "vector_store"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run indexing as two isolated phases: ingestion then embedding."
    )
    parser.add_argument("--metadata-limit", type=int, default=None)
    parser.add_argument("--content-limit", type=int, default=None)
    parser.add_argument("--chunks-db", type=Path, default=DEFAULT_CHUNKS_DB)
    parser.add_argument("--vector-store-dir", type=Path, default=DEFAULT_VECTOR_DIR)
    parser.add_argument(
        "--embedding-batch-size",
        type=int,
        default=16,
        help="Use 16 or 32 for GTX 1650 4GB VRAM.",
    )
    parser.add_argument("--skip-phase-a", action="store_true")
    parser.add_argument("--skip-phase-b", action="store_true")
    return parser.parse_args()


def append_optional_limit(command: list[str], flag: str, value: int | None) -> None:
    if value is not None:
        command.extend([flag, str(value)])


def run_command(command: list[str], phase_name: str) -> None:
    print(f"[build_index] Starting {phase_name}", flush=True)
    print("[build_index] Command:", " ".join(command), flush=True)
    completed = subprocess.run(command, cwd=PROJECT_ROOT)
    if completed.returncode != 0:
        raise SystemExit(
            f"[build_index] {phase_name} failed with exit code {completed.returncode}"
        )
    print(f"[build_index] Finished {phase_name}", flush=True)


def main() -> None:
    args = parse_args()

    phase_a_script = PROJECT_ROOT / "scripts" / "phase_a_ingestion.py"
    phase_b_script = PROJECT_ROOT / "scripts" / "phase_b_embedding.py"

    if not args.skip_phase_a:
        phase_a_command = [
            sys.executable,
            "-u",
            str(phase_a_script),
            "--output",
            str(args.chunks_db),
        ]
        append_optional_limit(
            phase_a_command,
            "--metadata-limit",
            args.metadata_limit,
        )
        append_optional_limit(
            phase_a_command,
            "--content-limit",
            args.content_limit,
        )
        run_command(phase_a_command, "Phase A ingestion")

    if not args.skip_phase_b:
        phase_b_command = [
            sys.executable,
            "-u",
            str(phase_b_script),
            "--chunks-db",
            str(args.chunks_db),
            "--vector-store-dir",
            str(args.vector_store_dir),
            "--batch-size",
            str(args.embedding_batch_size),
        ]
        run_command(phase_b_command, "Phase B embedding")

    print("[build_index] Done.", flush=True)


if __name__ == "__main__":
    main()
