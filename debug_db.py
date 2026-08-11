# debug_db.py
import inspect
from dotenv import load_dotenv

load_dotenv(override=True)

from src.rag_core.vector_store import VectorStore
from src.rag_core.embeddings import EmbeddingService

def debug():
    embedder = EmbeddingService()
    print(f"📏 Kích thước Embedding Model hiện tại: {embedder.dimension} chiều")
    print(f"📦 Model name: {getattr(embedder, 'model_name', 'Bedrock/Other')}")

    vstore = VectorStore(embedder=embedder)
    
    # 1. Kiểm tra chữ ký hàm search
    if hasattr(vstore, "search"):
        sig = inspect.signature(vstore.search)
        print(f"🔍 Chữ ký hàm vstore.search: search{sig}")
    else:
        print("❌ VectorStore không có hàm 'search'")

    # 2. Chạy thử search trực tiếp từ VectorStore và in ra lỗi
    query = "các mức xử phạt vi phạm đối với điều khiển phương tiện đường bộ có chứa nồng độ cồn"
    print("\n🚀 Đang test gọi vstore.search() trực tiếp...")
    try:
        # Thử các kiểu gọi phổ biến
        if hasattr(vstore, "search"):
            try:
                res = vstore.search(query=query, top_k=5)
            except TypeError:
                res = vstore.search(query, k=5)
            
            print(f"✅ Số kết quả trả về từ VectorStore: {len(res)}")
            if res:
                print("📄 Đoạn văn mẫu:", str(res[0].get("text", ""))[:150])
        else:
            print("❌ Không tìm thấy phương thức search phù hợp.")
    except Exception as e:
        print(f"❌ [LỖI THỰC SỰ TRONG SQL/VECTORSTORE]: {e}")

if __name__ == "__main__":
    debug()