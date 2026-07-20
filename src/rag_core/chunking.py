from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List

from .config import get_settings


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    document_id: str
    text: str
    chunk_index: int
    metadata: Dict[str, Any]


# Pattern to capture legal heading lines (Chương, Điều, Mục, Khoản) possibly with leading whitespace.
# Using multiline flag (?m) so ^ matches start of each line.
_SECTION_SPLIT_PATTERN = re.compile(
    r'(?m)(\s*(?:Chương|Điều|Mục|Khoản)\b[^\n]*)'
)


def _clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _window_chunks(text: str, chunk_size: int, overlap: int) -> List[str]:
    """Fallback sliding‑window chunker (character based)."""
    if len(text) <= chunk_size:
        return [text]

    chunks: List[str] = []
    start = 0
    text_len = len(text)

    while start < text_len:
        end = min(start + chunk_size, text_len)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        if end >= text_len:
            break

        start = max(end - overlap, start + 1)

    return chunks


def split_text(text: str) -> List[str]:
    """
    Split text into chunks, preferring to cut at legal section headings
    (Chương, Điều, Mục, Khoản). If no such headings are found, fall back
    to fixed‑size windowing.
    """
    settings = get_settings()
    text = _clean_text(text)
    if not text:
        return []

    # Tách văn bản theo các mốc cấu trúc luật
    parts = _SECTION_SPLIT_PATTERN.split(text)
    
    chunks: List[str] = []
    # parts[0] là phần văn bản nằm trước tiêu đề đầu tiên (nếu có)
    buffer = parts[0].strip() if parts[0] else ""

    # Duyệt theo cặp luân phiên: parts[i] là Tiêu đề, parts[i+1] là Nội dung
    for i in range(1, len(parts), 2):
        heading = parts[i].strip()
        body = parts[i+1].strip() if (i + 1) < len(parts) else ""
        
        # Buộc chặt Tiêu đề luật và Nội dung của điều đó lại với nhau
        section = f"{heading}\n{body}".strip() if body else heading
        if not section:
            continue
            
        if not buffer:
            buffer = section
            continue
            
        # Kiểm tra xem nếu gộp thêm đoạn luật mới này có bị tràn dung lượng không
        if len(buffer) + len(section) + 2 <= settings.chunk_size_chars:
            buffer = buffer + "\n\n" + section
        else:
            # Nếu tràn, đóng gói chunk cũ lại và khởi tạo túi mới bằng chính đoạn luật này
            chunks.append(buffer)
            buffer = section

    if buffer:
        chunks.append(buffer)

    # Phòng hờ trường hợp có Điều luật quá dài vượt ngưỡng size limit thì dùng cửa sổ trượt
    final_chunks: List[str] = []
    for ch in chunks:
        ch = ch.strip()
        if not ch:
            continue
        if len(ch) <= settings.chunk_size_chars:
            final_chunks.append(ch)
        else:
            sub_chunks = _window_chunks(
                ch, settings.chunk_size_chars, settings.chunk_overlap_chars
            )
            final_chunks.extend([c.strip() for c in sub_chunks if c.strip()])

    return final_chunks

def chunk_document(document: Dict[str, Any]) -> List[Chunk]:
    """
    Split a single document into chunks.
    Expected document dict keys: document_id, text, metadata.
    """
    document_id = str(document.get("document_id", ""))
    text = str(document.get("text", ""))
    metadata = dict(document.get("metadata", {}))

    chunks: List[Chunk] = []
    for idx, chunk_text in enumerate(split_text(text)):
        chunks.append(
            Chunk(
                chunk_id=f"{document_id}::chunk_{idx}",
                document_id=document_id,
                text=chunk_text,
                chunk_index=idx,
                metadata=metadata,
            )
        )
    return chunks


def chunk_documents(documents: List[Dict[str, Any]]) -> List[Chunk]:
    all_chunks: List[Chunk] = []
    for document in documents:
        all_chunks.extend(chunk_document(document))
    return all_chunks