from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

import boto3
from botocore.exceptions import ClientError

from .config import get_settings


def _normalize_id(value: Any) -> str:
    return "" if value is None else str(value)


def _fetch_from_s3(bucket: str, key: str) -> str:
    """Fetch a single object from S3 and return its text content."""
    s3 = boto3.client("s3")
    try:
        response = s3.get_object(Bucket=bucket, Key=key)
        body = response["Body"]
        # Try to decode as utf-8, fallback to latin-1
        try:
            return body.read().decode("utf-8")
        except UnicodeDecodeError:
            return body.read().decode("latin-1")
    except ClientError as e:
        # If the object doesn't exist or any other error, skip this file
        print(f"Warning: Could not fetch s3://{bucket}/{key}: {e}")
        return ""


def _iter_local_files(root_dir: Path, limit: Optional[int] = None) -> Iterator[Dict[str, Any]]:
    """Yield documents from a local directory of .txt and .pdf files."""
    count = 0
    # gather files
    files = sorted(root_dir.rglob("*.txt")) + sorted(root_dir.rglob("*.pdf"))
    for file_path in files:
        if limit is not None and count >= limit:
            break
        try:
            if file_path.suffix.lower() == ".txt":
                text = file_path.read_text(encoding="utf-8", errors="ignore")
            else:  # pdf
                try:
                    import PyPDF2
                except Exception:  # pragma: no cover
                    raise RuntimeError(
                        "PyPDF2 is required to read PDF files. Install it via `pip install pypdf`."
                    )
                pdf_file = file_path.open("rb")
                reader = PyPDF2.PdfReader(pdf_file)
                text_parts = []
                for page in reader.pages:
                    text_parts.append(page.extract_text() or "")
                text = "\n".join(text_parts)
                pdf_file.close()
        except Exception as e:  # pragma: no cover
            print(f"Warning: Could not read {file_path}: {e}")
            continue
        if not text.strip():
            continue
        doc_id = file_path.stem
        yield {
            "document_id": doc_id,
            "text": text,
            "metadata": {
                "source_file": str(file_path.relative_to(root_dir)),
                "file_size": file_path.stat().st_size,
                "extension": file_path.suffix.lower(),
            },
        }
        count += 1


def iter_documents(
    metadata_limit: Optional[int] = None,
    content_limit: Optional[int] = None,
    content_batch_size: int = 64,
) -> Iterator[dict]:
    """
    Yield documents as dictionaries with keys:
        document_id, text, metadata

    This implementation supports three modes:
      1. S3 mode: if USE_S3 environment variable is set to "true", reads objects from an S3 bucket.
      2. Local demo mode: if HF_DATASET_NAME is empty and LOCAL_DEMO_PATH is set, reads from that folder.
      3. HuggingFace mode: otherwise reads the Face dataset) uses snapshot_download of the HF dataset.

    In S3 mode, each object in the bucket (under an optional prefix) is treated as a document.
    The object key (without extension) is used as the document_id.

    In local demo mode, each .txt or .pdf file under LOCAL_DEMO_PATH is treated as a document.
    The file stem (without extension) is used as the document_id.

    The `metadata_limit` and `content_limit` arguments are interpreted as limits on the number of
    documents yielded.
    """
    settings = get_settings()
    use_s3 = os.getenv("USE_S3", "0").lower() in ("1", "true", "yes", "y")

    if use_s3:
        bucket = os.getenv("VECTOR_S3_BUCKET")
        prefix = os.getenv("VECTOR_S3_PREFIX", "").rstrip("/")
        if not bucket:
            raise ValueError("VECTOR_S3_BUCKET must be set when USE_S3 is true")
        s3 = boto3.client("s3")
        paginator = s3.get_paginator("list_objects_v2")
        pages = paginator.paginate(Bucket=bucket, Prefix=prefix)
        count = 0
        for page in pages:
            for obj in page.get("Contents", []):
                key = obj["Key"]
                # Skip directories or non-files (if key ends with '/')
                if key.endswith("/"):
                    continue
                # Apply limits
                if content_limit is not None and count >= content_limit:
                    return
                if metadata_limit is not None and count >= metadata_limit:
                    return
                text = _fetch_from_s3(bucket, key)
                if not text.strip():
                    continue
                # Use the filename (without extension) as document_id
                doc_id = Path(key).stem
                yield {
                    "document_id": doc_id,
                    "text": text,
                    "metadata": {
                        "s3_bucket": bucket,
                        "s3_key": key,
                        "size": obj["Size"],
                    },
                }
                count += 1
    else:
        # Not using S3: check if we should use local demo folder or HF dataset
        hf_name = settings.hf_dataset_name.strip()
        # local_demo_path = os.getenv("LOCAL_DEMO_PATH")
        local_demo_path = r"D:/Law-Chatbot/data_demo" 
        if not hf_name and local_demo_path:
            # Local demo mode
            demo_path = Path(local_demo_path)
            if not demo_path.is_dir():
                raise ValueError(f"LOCAL_DEMO_PATH '{local_demo_path}' does not exist or is not a directory")
            # Determine effective limit: prefer content_limit, fallback to metadata_limit
            effective_limit = None
            if content_limit is not None:
                effective_limit = content_limit
            elif metadata_limit is not None:
                effective_limit = metadata_limit
            yield from _iter_local_files(demo_path, limit=effective_limit)
        else:
            # HuggingFace mode (default)
            repo_id = hf_name if hf_name else settings.hf_dataset_name  # fallback to default if empty but not using local demo
            from huggingface_hub import snapshot_download

            local_dir = snapshot_download(
                repo_id=repo_id,
                repo_type="dataset",
                allow_patterns="*.txt",
            )
            local_path = Path(local_dir)
            txt_files = sorted(local_path.rglob("*.txt"))
            # Apply limits
            if content_limit is not None:
                txt_files = txt_files[:content_limit]
            if metadata_limit is not None:
                txt_files = txt_files[:metadata_limit]
            for file_path in txt_files:
                try:
                    text = file_path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    text = file_path.read_text(encoding="latin-1")
                doc_id = file_path.stem
                yield {
                    "document_id": doc_id,
                    "text": text,
                    "metadata": {},
                }


def load_documents(
    metadata_limit: Optional[int] = None,
    content_limit: Optional[int] = None,
    content_batch_size: int = 64,
) -> list[dict]:
    """Return a list of document dicts (materialises the iterator)."""
    return list(
        iter_documents(
            metadata_limit=metadata_limit,
            content_limit=content_limit,
            content_batch_size=content_batch_size,
        )
    )


def documents_to_dicts(documents: list[dict]) -> list[dict]:
    """Identity helper kept for compatibility with existing code."""
    return documents