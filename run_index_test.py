import os
from src.rag_core.pipeline import build_index_pipeline
from src.rag_core.vector_store import VectorStore

if __name__ == "__main__":
    print("⏳ Đang khởi tạo quá trình build index thử nghiệm...")
    
    store = VectorStore()
    # Kích hoạt dọn dẹp sạch sẽ database lỗi trước đó
    store.reset() 
    
    # CHỈ CHẠY THỬ NGHIỆM VỚI 200 VĂN BẢN ĐẦU TIÊN để test luồng Parquet
    build_index_pipeline(
        content_limit=200, 
        vector_store=store,
        document_batch_size=32,
        commit_interval=50
    )
    
    print("✅ Build index thử nghiệm thành công! Hãy mở chatbot lên kiểm tra thử.")