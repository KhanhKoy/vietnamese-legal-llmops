from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List

from .config import get_settings


@dataclass
class Chunk:
    chunk_id: str
    document_id: str
    text: str
    chunk_index: int
    metadata: Dict[str, Any]


_SECTION_SPLIT_PATTERN = re.compile(
    r"(?m)^(?=\s*(Chương|Điều|Mục|Khoản)\b)"
)


def _clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _window_chunks(text: str, chunk_size: int, overlap: int) -> List[str]:
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
    Ưu tiên tách theo heading luật (Chương/Điều/Mục/Khoản).
    Nếu không hợp lệ thì fallback sang window theo ký tự.
    """
    settings = get_settings()
    text = _clean_text(text)

    if not text:
        return []

    parts = [p.strip() for p in _SECTION_SPLIT_PATTERN.split(text) if p.strip()]

    if len(parts) > 1:
        # Ghép lại thành các phần nhỏ tương đối theo heading
        merged: List[str] = []
        buffer = ""
        for part in parts:
            if len(buffer) + len(part) + 2 <= settings.chunk_size_chars:
                buffer = f"{buffer}\n{part}".strip()
            else:
                if buffer:
                    merged.append(buffer.strip())
                buffer = part
        if buffer:
            merged.append(buffer.strip())
        return merged

    return _window_chunks(
        text=text,
        chunk_size=settings.chunk_size_chars,
        overlap=settings.chunk_overlap_chars,
    )


def chunk_document(document: Dict[str, Any]) -> List[Chunk]:
    """
    Chia 1 document thành nhiều chunk.
    Document input phải có: document_id, text, metadata.
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