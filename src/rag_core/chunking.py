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


HTML_TAG_PATTERN = re.compile(r"<[^>]+>")

ARTICLE_HEADING_PATTERN = re.compile(
    r"(?im)^\s*(Điều\s+\d+[a-zA-ZăâđêôơưĂÂĐÊÔƠƯ]?\s*[\.:]?(?:\s+.*)?)$"
)

LEGAL_HEADING_SEPARATOR_REGEXES = [
    r"\n(?=Chương\s+[IVXLCDM\d]+[\.:]?(?:\s+|$))",
    r"\n(?=Mục\s+\d+[\.:]?(?:\s+|$))",
    r"\n(?=Điều\s+\d+[a-zA-ZăâđêôơưĂÂĐÊÔƠƯ]?\s*[\.:]?(?:\s+|$))",
    r"\n(?=Khoản\s+\d+[a-zA-ZăâđêôơưĂÂĐÊÔƠƯ]?\s*[\.:]?(?:\s+|$))",
    r"\n(?=\d+\.\s+)",
    r"\n\n",
    r"\n",
    r"(?<=\.)\s+",
    r"\s+",
    "",
]


def html_to_text(content_html: str) -> str:
    """
    Convert HTML thô trong cột `content_html` thành plain text sạch.

    Hàm này cố tình nằm trong `chunking.py` vì mọi input trước khi chunking
    phải được chuẩn hóa về plain text. `dataset_reader.py` cũng gọi lại hàm
    này để bảo đảm không embed raw HTML.
    """
    if not content_html:
        return ""

    from bs4 import BeautifulSoup

    soup = BeautifulSoup(str(content_html), "html.parser")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    for tag in soup.find_all(["br", "p", "div", "tr", "li"]):
        tag.append("\n")

    text = soup.get_text(separator="\n")
    return _clean_text(text)


def _looks_like_html(text: str) -> bool:
    return bool(text and HTML_TAG_PATTERN.search(text[:2000]))


def _clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _prepare_text(text: str) -> str:
    text = "" if text is None else str(text)
    if _looks_like_html(text):
        return html_to_text(text)
    return _clean_text(text)


def _window_chunks(text: str, chunk_size: int, overlap: int) -> List[str]:
    if len(text) <= chunk_size:
        return [text] if text else []

    chunks: List[str] = []
    start = 0
    text_len = len(text)
    safe_overlap = max(0, min(overlap, chunk_size - 1))

    while start < text_len:
        end = min(start + chunk_size, text_len)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        if end >= text_len:
            break

        start = max(end - safe_overlap, start + 1)

    return chunks


def _recursive_chunks(text: str, chunk_size: int, overlap: int) -> List[str]:
    try:
        from langchain_text_splitters import RecursiveCharacterTextSplitter
    except ImportError:
        return _window_chunks(text, chunk_size=chunk_size, overlap=overlap)

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=max(0, min(overlap, chunk_size // 2)),
        separators=LEGAL_HEADING_SEPARATOR_REGEXES,
        is_separator_regex=True,
        keep_separator=True,
        strip_whitespace=True,
    )
    return [chunk.strip() for chunk in splitter.split_text(text) if chunk.strip()]


def _split_by_articles(text: str) -> List[str]:
    matches = list(ARTICLE_HEADING_PATTERN.finditer(text))
    if not matches:
        return [text]

    sections: List[str] = []
    first_start = matches[0].start()
    preamble = text[:first_start].strip()
    if preamble:
        sections.append(preamble)

    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        section = text[start:end].strip()
        if section:
            sections.append(section)

    return sections


def split_text(text: str) -> List[str]:
    """
    Chunk văn bản pháp luật Việt Nam.

    Chiến lược:
    1. Parse HTML nếu input vẫn là `content_html`.
    2. Ưu tiên giữ nguyên ranh giới `Điều N.` để không cắt đứt context pháp lý.
    3. Nếu một Điều quá dài, dùng RecursiveCharacterTextSplitter với separator
       pháp luật: Chương, Mục, Điều, Khoản, dòng, câu, khoảng trắng.
    """
    settings = get_settings()
    chunk_size = max(200, int(settings.chunk_size_chars))
    overlap = max(0, int(settings.chunk_overlap_chars))

    text = _prepare_text(text)
    if not text:
        return []

    chunks: List[str] = []
    buffer = ""

    for section in _split_by_articles(text):
        if len(section) > chunk_size:
            if buffer:
                chunks.append(buffer.strip())
                buffer = ""
            chunks.extend(_recursive_chunks(section, chunk_size, overlap))
            continue

        candidate = f"{buffer}\n\n{section}".strip() if buffer else section
        if len(candidate) <= chunk_size:
            buffer = candidate
        else:
            if buffer:
                chunks.append(buffer.strip())
            buffer = section

    if buffer:
        chunks.append(buffer.strip())

    normalized_chunks: List[str] = []
    for chunk in chunks:
        if len(chunk) <= chunk_size:
            normalized_chunks.append(chunk)
        else:
            normalized_chunks.extend(_recursive_chunks(chunk, chunk_size, overlap))

    return normalized_chunks


def chunk_document(document: Dict[str, Any]) -> List[Chunk]:
    """
    Chia một document thành nhiều chunk và giữ metadata cho citation.

    Document input kỳ vọng:
    - document_id
    - text: plain text hoặc HTML thô
    - metadata
    """
    document_id = str(document.get("document_id", "")).strip()
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
