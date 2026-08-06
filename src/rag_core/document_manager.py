from __future__ import annotations

import uuid
from typing import Optional

import pypdf

from .chunking import chunk_document
from .embeddings import EmbeddingService
from .vector_store import VectorStore


class DocumentManager:
    def __init__(
        self,
        vector_store: Optional[VectorStore] = None,
        embedder: Optional[EmbeddingService] = None,
    ):
        self.embedder = embedder or EmbeddingService()
        self.vector_store = vector_store or VectorStore(embedder=self.embedder)

    def extract_text_from_pdf(self, pdf_file_bytes) -> str:
        """Trích xuất nội dung text từ file PDF"""
        reader = pypdf.PdfReader(pdf_file_bytes)
        text_parts = []
        for page in reader.pages:
            extracted = page.extract_text()
            if extracted:
                text_parts.append(extracted)
        return "\n".join(text_parts)

    def add_document_from_pdf(
        self,
        pdf_file_bytes,
        title: str,
        so_ky_hieu: str,
        loai_van_ban: str,
        co_quan_ban_hanh: str,
        is_procedural_law: bool = False,
        tinh_trang_hieu_luc: str = "Còn hiệu lực",
        ngay_het_hieu_luc: str = "",
    ) -> str:
        """
        Xử lý trọn gói: Đọc PDF -> Chunking -> Embedding -> Lưu AWS RDS
        """
        # 1. Trích xuất text từ file PDF
        raw_text = self.extract_text_from_pdf(pdf_file_bytes)
        if not raw_text.strip():
            raise ValueError("File PDF trống hoặc không thể đọc được văn bản.")

        # 2. Sinh document_id mới (UUID)
        doc_id = f"custom_doc_{uuid.uuid4().hex[:8]}"

        # 3. Đóng gói Metadata
        metadata = {
            "title": title,
            "so_ky_hieu": so_ky_hieu,
            "loai_van_ban": loai_van_ban,
            "co_quan_ban_hanh": co_quan_ban_hanh,
            "is_procedural_law": is_procedural_law,
            "tinh_trang_hieu_luc": tinh_trang_hieu_luc,
            "ngay_het_hieu_luc": ngay_het_hieu_luc,
        }

        doc_dict = {
            "document_id": doc_id,
            "text": raw_text,
            "metadata": metadata,
        }

        # 4. Chunking văn bản
        chunks = chunk_document(doc_dict)
        if not chunks:
            raise ValueError("Không thể tạo chunk nào từ văn bản này.")

        # 5. Sinh Embeddings
        texts = [c.text for c in chunks]
        embeddings = self.embedder.embed_texts(texts)

        # 6. Đẩy vào CSDL AWS RDS
        self.vector_store.add(chunks, embeddings)
        self.vector_store.save()

        return doc_id

    def update_status(self, document_id: str, new_status: str, ngay_het_hieu_luc: str) -> bool:
        """Cập nhật trạng thái hiệu lực"""
        return self.vector_store.update_document_metadata(
            document_id=document_id,
            updates={
                "tinh_trang_hieu_luc": new_status,
                "ngay_het_hieu_luc": ngay_het_hieu_luc,
            }
        )

    def update_document_info(
        self,
        document_id: str,
        tinh_trang_hieu_luc: Optional[str] = None,
        ngay_het_hieu_luc: Optional[str] = None,
        is_procedural_law: Optional[bool] = None,
    ) -> bool:
        """
        Cập nhật các thuộc tính của văn bản. Chỉ gửi các trường có thay đổi lên DB.
        """
        updates = {}
        if tinh_trang_hieu_luc is not None:
            updates["tinh_trang_hieu_luc"] = tinh_trang_hieu_luc
        if ngay_het_hieu_luc is not None:
            updates["ngay_het_hieu_luc"] = ngay_het_hieu_luc
        if is_procedural_law is not None:
            updates["is_procedural_law"] = bool(is_procedural_law)

        if not updates:
            return False

        return self.vector_store.update_document_metadata(
            document_id=document_id,
            updates=updates
        )

    
    
    def delete_document(self, document_id: str) -> bool:
        """Soft-delete a document so it can be audited/restored."""
        from datetime import datetime, timezone

        return self.vector_store.update_document_metadata(
            document_id=document_id,
            updates={
                "deleted_at": datetime.now(timezone.utc).isoformat(),
                "tinh_trang_hieu_luc": "Đã ẩn",
            },
        )

    def list_documents(self, limit: int = 50, offset: int = 0):
        return self.vector_store.list_documents(limit=limit, offset=offset)
