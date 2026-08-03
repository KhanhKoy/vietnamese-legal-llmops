from __future__ import annotations

from typing import Iterator, Optional

from .config import get_settings


def iter_documents(
    metadata_limit: Optional[int] = None,
    content_limit: Optional[int] = None,
    content_batch_size: int = 64,
) -> Iterator[dict]:
    settings = get_settings()
    hf_name = settings.hf_dataset_name.strip() or "NguyenKH/clean_legal_knowledge"

    print(f"🚀 Đang kết nối và tải dataset sạch từ HuggingFace: {hf_name}...")
    
    import pyarrow.parquet as pq
    from huggingface_hub import hf_hub_download

    # Tải file parquet trực tiếp từ Hugging Face Repo của bạn
    try:
        local_file_path = hf_hub_download(
            repo_id=hf_name,
            repo_type="dataset",
            filename="data/clean_legal_knowledge.parquet"
        )
    except Exception:
        # Dự phòng nếu file nằm ở đường dẫn gốc
        local_file_path = hf_hub_download(
            repo_id=hf_name,
            repo_type="dataset",
            filename="clean_legal_knowledge.parquet"
        )

    print(f"📦 Đã xác định file dữ liệu tại local: {local_file_path}")
    
    # Danh sách các cột cần đọc từ file Parquet
    target_columns = [
        "id", "title", "so_ky_hieu", "ngay_ban_hanh", "loai_van_ban",
        "co_quan_ban_hanh", "linh_vuc", "tinh_trang_hieu_luc",
        "nguoi_ky", "chuc_danh", "is_procedural_law", "content_markdown"
    ]

    parquet_file = pq.ParquetFile(local_file_path)
    batch_iterator = parquet_file.iter_batches(batch_size=content_batch_size, columns=target_columns)

    effective_limit = content_limit if content_limit is not None else metadata_limit
    count = 0
    stop_streaming = False

    for batch in batch_iterator:
        if stop_streaming:
            break
        
        df_batch = batch.to_pandas()
        
        for _, row in df_batch.iterrows():
            if effective_limit is not None and count >= effective_limit:
                stop_streaming = True
                break

            doc_id = str(row.get("id") or f"doc_{count}")
            # Lấy nội dung từ cột content_markdown
            text = str(row.get("content_markdown") or "").strip()

            if not text:
                continue

            # Đóng gói Metadata phong phú để RAG và LLM tham chiếu
            metadata = {
                "title": str(row.get("title") or ""),
                "so_ky_hieu": str(row.get("so_ky_hieu") or ""),
                "loai_van_ban": str(row.get("loai_van_ban") or ""),
                "ngay_ban_hanh": str(row.get("ngay_ban_hanh") or ""),
                "co_quan_ban_hanh": str(row.get("co_quan_ban_hanh") or ""),
                "linh_vuc": str(row.get("linh_vuc") or ""),
                "is_procedural_law": bool(row.get("is_procedural_law", False)), # 👉 Lưu nhãn tố tụng vào metadata
                "tinh_trang_hieu_luc": str(row.get("tinh_trang_hieu_luc") or ""),
                "nguoi_ky": str(row.get("nguoi_ky") or ""),
                "chuc_danh": str(row.get("chuc_danh") or "")
            }

            yield {
                "document_id": doc_id,
                "text": text,
                "metadata": metadata
            }
            count += 1