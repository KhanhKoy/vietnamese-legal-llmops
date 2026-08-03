"""SQS/S3 ingestion entrypoint.

Production flow: S3 ObjectCreated -> SQS -> this Lambda.  SQS partial batch
responses preserve failed jobs for retry/DLQ while successful jobs are removed.
"""

from __future__ import annotations

import io
import json
import os
from functools import lru_cache
from typing import Any, Dict, Iterable, Tuple
from urllib.parse import unquote_plus

import boto3

try:
    from src.rag_core.chunking import chunk_document
    from src.rag_core.embeddings import EmbeddingService
    from src.rag_core.vector_store import VectorStore
except ImportError:
    from chunking import chunk_document
    from embeddings import EmbeddingService
    from vector_store import VectorStore


@lru_cache(maxsize=1)
def _s3_client():
    """Create the client lazily so importing the module never contacts AWS metadata."""
    return boto3.client("s3")


@lru_cache(maxsize=1)
def _services() -> Tuple[EmbeddingService, VectorStore]:
    embedder = EmbeddingService()
    return embedder, VectorStore(embedder=embedder)


def _get_object_text(bucket: str, key: str) -> str:
    response = _s3_client().get_object(Bucket=bucket, Key=key)
    body = response["Body"].read()
    content_type = response.get("ContentType", "")

    if key.lower().endswith(".txt") or "text/plain" in content_type:
        return body.decode("utf-8", errors="replace")
    if key.lower().endswith(".pdf") or "application/pdf" in content_type:
        import pypdf

        reader = pypdf.PdfReader(io.BytesIO(body))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    raise ValueError(f"Định dạng file không được hỗ trợ: {key}")


def _load_manifest(bucket: str, document_id: str) -> Dict[str, Any]:
    key = f"incoming/manifests/{document_id}.json"
    response = _s3_client().get_object(Bucket=bucket, Key=key)
    return json.loads(response["Body"].read().decode("utf-8"))


def _extract_s3_records(payload: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    # SNS can wrap an S3 notification before it reaches SQS.
    if "Message" in payload and isinstance(payload["Message"], str):
        payload = json.loads(payload["Message"])
    for record in payload.get("Records", []):
        if record.get("eventSource") == "aws:s3":
            yield record


def _process_s3_record(record: Dict[str, Any]) -> None:
    s3_info = record.get("s3", {})
    bucket = s3_info.get("bucket", {}).get("name")
    key = unquote_plus(s3_info.get("object", {}).get("key", ""))
    if not bucket or not key or not key.startswith("incoming/files/"):
        return

    parts = key.split("/")
    if len(parts) < 4:
        raise ValueError(f"S3 key không đúng cấu trúc ingestion: {key}")
    document_id = parts[2]
    manifest = _load_manifest(bucket, document_id)
    if manifest.get("object_key") != key:
        raise ValueError("Manifest không khớp object đang xử lý")

    text = _get_object_text(bucket, key)
    if not text.strip():
        raise ValueError("Tài liệu trống hoặc PDF scan cần OCR")

    metadata = dict(manifest.get("metadata", {}))
    metadata.update(
        {
            "s3_bucket": bucket,
            "s3_key": key,
            "created_by": manifest.get("created_by", ""),
            "ingestion_schema_version": manifest.get("schema_version", 1),
        }
    )
    document = {"document_id": document_id, "text": text, "metadata": metadata}
    chunks = chunk_document(document)
    if not chunks:
        raise ValueError("Không thể tạo chunk từ tài liệu")

    embedder, store = _services()
    batch_size = int(os.getenv("INGESTION_EMBED_BATCH_SIZE", "32"))
    for start in range(0, len(chunks), batch_size):
        batch = chunks[start : start + batch_size]
        embeddings = embedder.embed_texts([chunk.text for chunk in batch])
        store.add(batch, embeddings)
    store.commit()
    print(f"✅ Ingested document={document_id}, chunks={len(chunks)}, key={key}")


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    failures = []
    records = event.get("Records", [])

    for envelope in records:
        is_sqs = envelope.get("eventSource") == "aws:sqs"
        message_id = envelope.get("messageId", "")
        try:
            if is_sqs:
                payload = json.loads(envelope.get("body", "{}"))
                for s3_record in _extract_s3_records(payload):
                    _process_s3_record(s3_record)
            elif envelope.get("eventSource") == "aws:s3":
                _process_s3_record(envelope)
        except Exception as exc:
            print(f"❌ Ingestion failed message={message_id}: {exc}")
            if is_sqs and message_id:
                failures.append({"itemIdentifier": message_id})
            else:
                raise

    return {"batchItemFailures": failures}
