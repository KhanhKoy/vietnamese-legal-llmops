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

    # Split while keeping the delimiters (the heading lines)
    parts = _SECTION_SPLIT_PATTERN.split(text)
    # parts format: [text0, heading1, text1, heading2, text2, ...]

    chunks: List[str] = []
    buffer = ""

    for idx, part in enumerate(parts):
        if idx % 3 == 0:  # plain text segment
            if not part:
                continue
            # Try to add to current buffer respecting size limit
            if len(buffer) + len(part) <= settings.chunk_size_chars:
                buffer = (buffer + " " + part).strip() if buffer else part.strip()
            else:
                if buffer:
                    chunks.append(buffer.strip())
                # start new buffer with this segment
                buffer = part.strip()
        else:
            # This is a heading line (including possible leading whitespace)
            heading = part.strip()
            # If adding heading would exceed limit, start a new chunk with it
            if len(buffer) + len(heading) + 1 <= settings.chunk_size_chars:
                # Add a space before heading if there is already content
                buffer = (
                    (buffer + " " + heading).strip() if buffer else heading
                )
            else:
                if buffer:
                    chunks.append(buffer.strip())
                buffer = heading

    if buffer:
        chunks.append(buffer.strip())

    # Any chunk still too large (unlikely but possible) gets windowed
    final_chunks: List[str] = []
    for ch in chunks:
        if len(ch) <= settings.chunk_size_chars:
            if ch:
                final_chunks.append(ch)
        else:
            sub_chunks = _window_chunks(
                ch, settings.chunk_size_chars, settings.chunk_overlap_chars
            )
            final_chunks.extend([c for c in sub_chunks if c])

    return [c for c in final_chunks if c]


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