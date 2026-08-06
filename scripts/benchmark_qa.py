from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from rag_core.qa_service import QAService  # noqa: E402


DEFAULT_QUESTIONS = [
    "Thoi hieu khoi kien vu an dan su la bao lau?",
    "Nguoi lao dong duoc nghi thai san bao nhieu thang?",
    "Dieu kien cap giay chung nhan quyen su dung dat la gi?",
    "Hop dong lao dong phai co nhung noi dung nao?",
    "Xu phat vi pham hanh chinh trong linh vuc giao thong duoc quy dinh ra sao?",
]


def _load_questions(path: Path | None) -> list[str]:
    if path is None:
        return DEFAULT_QUESTIONS

    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        raise ValueError(f"Question file is empty: {path}")

    if path.suffix.lower() == ".json":
        data = json.loads(raw)
        if isinstance(data, list):
            questions = []
            for item in data:
                if isinstance(item, str):
                    questions.append(item)
                elif isinstance(item, dict):
                    value = item.get("question") or item.get("query")
                    if value:
                        questions.append(str(value))
            return questions
        raise ValueError("JSON question file must be a list of strings or objects")

    return [line.strip() for line in raw.splitlines() if line.strip()]


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return round(values[0], 2)
    sorted_values = sorted(values)
    rank = (len(sorted_values) - 1) * percentile
    lower = int(rank)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = rank - lower
    return round(sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight, 2)


def _summary(rows: list[dict[str, Any]], key: str) -> dict[str, float]:
    values = [
        float(row.get("timings_ms", {}).get(key, 0.0) or 0.0)
        for row in rows
    ]
    return {
        "avg": round(statistics.mean(values), 2) if values else 0.0,
        "p50": _percentile(values, 0.50),
        "p95": _percentile(values, 0.95),
        "max": round(max(values), 2) if values else 0.0,
    }


async def _run(args: argparse.Namespace) -> int:
    questions = _load_questions(args.questions_file)
    questions = questions[: args.limit] if args.limit else questions
    if not questions:
        raise ValueError("No benchmark questions were provided")

    service = QAService()
    rows: list[dict[str, Any]] = []

    for idx, question in enumerate(questions, start=1):
        started_at = time.perf_counter()
        response = await service.ask(question=question, top_k=args.top_k)
        elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
        timings = response.get("timings_ms") or {}
        if "total_ms" not in timings:
            timings["total_ms"] = elapsed_ms

        row = {
            "index": idx,
            "question": question,
            "answer_chars": len(str(response.get("answer", ""))),
            "result_count": len(response.get("results") or []),
            "error_code": response.get("error_code", ""),
            "timings_ms": timings,
        }
        rows.append(row)
        print(
            f"[{idx}/{len(questions)}] "
            f"total={timings.get('total_ms')}ms "
            f"retrieval={timings.get('retrieval_ms')}ms "
            f"embedding={timings.get('embedding_ms')}ms "
            f"db={timings.get('db_search_ms')}ms "
            f"llm={timings.get('llm_ms')}ms "
            f"results={row['result_count']}"
        )

    keys = ["total_ms", "retrieval_ms", "embedding_ms", "db_search_ms", "rerank_ms", "llm_ms"]
    print("\nSummary:")
    for key in keys:
        stats = _summary(rows, key)
        print(
            f"- {key}: avg={stats['avg']}ms "
            f"p50={stats['p50']}ms p95={stats['p95']}ms max={stats['max']}ms"
        )

    if args.output:
        args.output.write_text(
            json.dumps({"rows": rows}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\nWrote details to {args.output}")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark QA latency by stage.")
    parser.add_argument(
        "--questions-file",
        type=Path,
        default=None,
        help="Text file with one question per line, or JSON list of strings/objects.",
    )
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
