import io
import json
import os
from typing import Any

import boto3

try:
    from src.rag_core.chunking import chunk_document
    from src.rag_core.embeddings import EmbeddingService
    from src.rag_core.vector_store import VectorStore
except ImportError:
    from chunking import chunk_document
    from embeddings import EmbeddingService
    from vector_store import VectorStore

s3_client = boto3.client("s3")


def _get_object_text(bucket: str, key: str) -> str:
    resp = s3_client.get_object(Bucket=bucket, Key=key)
    body = resp["Body"].read()
    content_type = resp.get("ContentType", "")

    if key.lower().endswith(".txt") or "text/plain" in content_type:
        try:
            return body.decode("utf-8")
        except UnicodeDecodeError:
            return body.decode("latin-1")
    elif key.lower().endswith(".pdf") or "application/pdf" in content_type:
        import pypdf
        pdf_file = io.BytesIO(body)
        reader = pypdf.PdfReader(pdf_file)
        text_parts = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(text_parts)
    else:
        try:
            return body.decode("utf-8")
        except UnicodeDecodeError:
            return body.decode("latin-1")


def lambda_handler(event: dict, context: Any) -> dict:
    for record in event.get("Records", []):
        if record.get("eventSource") != "aws:s3":
            continue
        s3_info = record.get("s3", {})
        bucket = s3_info.get("bucket", {}).get("name")
        key = s3_info.get("object", {}).get("key")
        if not bucket or not key:
            continue

        try:
            text = _get_object_text(bucket, key)
        except Exception as e:
            print(f"Không thể đọc object s3://{bucket}/{key}: {e}")
            continue

        if not text.strip():
            print(f"Tài liệu trống: s3://{bucket}/{key}")
            continue

        document_id = os.path.splitext(os.path.basename(key))[0]
        document = {
            "document_id": document_id,
            "text": text,
            "metadata": {
                "s3_bucket": bucket,
                "s3_key": key,
                "size": len(text),
            },
        }

        # Đã sửa lỗi: chunk_document trả về List[Chunk] (Dataclass)
        chunks = chunk_document(document)
        if not chunks:
            print(f"Không thể chia nhỏ tài liệu: {document_id}")
            continue

        # Đã sửa lỗi: sử dụng c.text để lấy nội dung text từ đối tượng Chunk
        texts = [c.text for c in chunks]
        embedder = EmbeddingService()
        embeddings = embedder.embed_texts(texts)

        try:
            store = VectorStore()
            store.add(chunks, embeddings)
            store.close()
        except Exception as e:
            print(f"Lỗi khi lưu trữ Vector cho {document_id}: {e}")
            continue

    return {"statusCode": 200, "body": "OK"}
