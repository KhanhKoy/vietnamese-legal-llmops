from __future__ import annotations

from typing import Any, Dict, List

SYSTEM_PROMPT = """Bạn là trợ lý tư vấn pháp luật Việt Nam chuyên nghiệp và chính xác.
Nhiệm vụ của bạn là trả lời câu hỏi dựa TRỰC TIẾP và DUY NHẤT vào Ngữ cảnh văn bản pháp luật được cung cấp dưới đây.

Quy tắc bắt buộc:
1. Đọc kỹ tất cả các đoạn trích trong Ngữ cảnh để tổng hợp câu trả lời ĐẦY ĐỦ, CHI TIẾT và RÕ RÀNG nhất.
2. Trích dẫn rõ nguồn pháp lý khi trả lời (Tên văn bản, Số ký hiệu, Điều/Khoản nếu có trong đoạn trích).
3. Tuyệt đối KHÔNG tự bịa đặt thêm điều luật, số hiệu văn bản hoặc kiến thức bên ngoài Ngữ cảnh.
4. Nếu trong Ngữ cảnh HOÀN TOÀN KHÔNG CHỨA THÔNG TIN để trả lời câu hỏi, bạn BẮT BUỘC phải trả lời chính xác câu sau:
   "Hiện không có thông tin về nội dung tìm kiếm trong cơ sở dữ liệu."
5. Định dạng câu trả lời: mỗi ý tưởng trên một dòng mới, dùng dấu gạch đầu dòng (-) hoặc số thứ tự để liệt kê các ý, dễ đọc và rõ ràng.
6. Nêu rõ ở cuối câu trả lời: "Lưu ý: Thông tin chỉ mang tính chất tham khảo, không phải là tư vấn pháp lý chính thức." 
"""

MAX_CHARS_PER_CHUNK = 800

def build_context_block(results: List[Dict[str, Any]]) -> str:
    if not results:
        return ""

    blocks: List[str] = []

    for idx, result in enumerate(results, start=1):
        score = result.get("score", 0.0)
        doc_id = result.get("document_id", "N/A")
        text = str(result.get("text", "")).strip()
        # Truncate text to keep prompt size manageable
        if len(text) > MAX_CHARS_PER_CHUNK:
            text = text[:MAX_CHARS_PER_CHUNK].rstrip() + "..."
        metadata = result.get("metadata", {})

        title = metadata.get("title", "Không rõ tiêu đề")
        so_ky_hieu = metadata.get("so_ky_hieu", "N/A")
        loai_vb = metadata.get("loai_van_ban", "N/A")
        co_quan = metadata.get("co_quan_ban_hanh", "N/A")

        header_info = f"[Nguồn {idx}] ID: {doc_id} | Văn bản: {title} | Số hiệu: {so_ky_hieu} | Loại: {loai_vb} | Cơ quan: {co_quan} (Score: {score:.4f})"

        blocks.append(
            f"=== {header_info} ===\n{text}"
        )

    return "\n\n---\n\n".join(blocks)


def build_prompt(question: str, results: List[Dict[str, Any]]) -> str:
    context = build_context_block(results)

    if not context.strip():
        context_str = "KHÔNG TÌM THẤY BẤT KỲ NGỮ CẢNH NÀO TRONG CƠ SỞ DỮ LIỆU."
    else:
        context_str = context

    return f"""{SYSTEM_PROMPT}

NGỮ CẢNH PHÁP LÝ ĐƯỢC CUNG CẤP:
{context_str}

CÂU HỎI CỦA NGƯỜI DÙNG:
{question}

CÂU TRẢ LỜI:"""