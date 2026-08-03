from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import boto3


class IngestionService:
    """Create a manifest and a short-lived direct-to-S3 upload form."""

    def __init__(self) -> None:
        self.bucket = os.getenv("LEGAL_DOCUMENTS_BUCKET") or os.getenv("VECTOR_S3_BUCKET", "")
        if not self.bucket:
            raise RuntimeError("LEGAL_DOCUMENTS_BUCKET chưa được cấu hình")
        self.s3 = boto3.client("s3")
        self.expiry_seconds = int(os.getenv("UPLOAD_URL_EXPIRY_SECONDS", "900"))

    def create_upload(self, filename: str, metadata: Dict[str, Any], actor_id: str) -> Dict[str, Any]:
        extension = Path(filename).suffix.lower()
        if extension not in {".pdf", ".txt"}:
            raise ValueError("Chỉ chấp nhận file PDF hoặc TXT")

        safe_stem = re.sub(r"[^A-Za-z0-9_.-]+", "-", Path(filename).stem).strip("-") or "document"
        document_id = f"admin_{uuid.uuid4().hex}"
        object_key = f"incoming/files/{document_id}/{safe_stem}{extension}"
        manifest_key = f"incoming/manifests/{document_id}.json"
        manifest = {
            "document_id": document_id,
            "object_key": object_key,
            "metadata": metadata,
            "created_by": actor_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "schema_version": 1,
        }
        self.s3.put_object(
            Bucket=self.bucket,
            Key=manifest_key,
            Body=json.dumps(manifest, ensure_ascii=False).encode("utf-8"),
            ContentType="application/json",
            ServerSideEncryption="AES256",
        )
        upload = self.s3.generate_presigned_post(
            Bucket=self.bucket,
            Key=object_key,
            Fields={"Content-Type": "application/pdf" if extension == ".pdf" else "text/plain"},
            Conditions=[
                ["content-length-range", 1, int(os.getenv("MAX_UPLOAD_BYTES", "52428800"))],
                {"Content-Type": "application/pdf" if extension == ".pdf" else "text/plain"},
            ],
            ExpiresIn=self.expiry_seconds,
        )
        return {
            "document_id": document_id,
            "object_key": object_key,
            "manifest_key": manifest_key,
            "upload": upload,
            "expires_in": self.expiry_seconds,
        }
