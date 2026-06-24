from __future__ import annotations

from typing import List, Dict, Any


SYSTEM_PROMPT = """Bạn là trợ lý hỏi đáp pháp luật tiếng Việt.
Chỉ trả lời dựa trên ngữ cảnh được cung cấp.
Nếu ngữ cảnh không đủ để kết luận, hãy nói rõ là chưa đủ căn cứ.
Không bịa đặt điều luật, số điều, số khoản.
Trả lời ngắn gọn, rõ ràng, có trích dẫn nguồn nếu có thể.
Nêu rõ đây không phải là tư vấn pháp lý chính thức."""


def build_context_block(results: List[Dict[str, Any]]) -> str:
    blocks: List[str] = []

    for idx, result in enumerate(results, start=1):
        chunk = result.get("chunk", {})
        score = result.get("score", 0.0)

        document_id = chunk.get("document_id", "unknown")
        chunk_id = chunk.get("chunk_id", "unknown")
        text = chunk.get("text", "")
        metadata = chunk.get("metadata", {})

        source_name = metadata.get("name") or metadata.get("title") or metadata.get("law_name") or "unknown"

        blocks.append(
            f"[Nguồn {idx}] score={score:.4f}\n"
            f"document_id={document_id}\n"
            f"chunk_id={chunk_id}\n"
            f"source={source_name}\n"
            f"text:\n{text}"
        )

    return "\n\n---\n\n".join(blocks)


def build_prompt(question: str, results: List[Dict[str, Any]]) -> str:
    context = build_context_block(results)

    return f"""{SYSTEM_PROMPT}

Ngữ cảnh:
{context if context else "Không có ngữ cảnh phù hợp."}

Câu hỏi:
{question}

Yêu cầu:
- Trả lời bằng tiếng Việt.
- Nếu thiếu căn cứ, hãy nói "Chưa đủ thông tin để kết luận".
- Nếu có thể, nêu nguồn trích dẫn.
"""