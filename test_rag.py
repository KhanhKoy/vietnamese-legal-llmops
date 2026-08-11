# test_rag.py
import asyncio
from dotenv import load_dotenv

load_dotenv(override=True)

from src.rag_core.qa_service import QAService

async def main():
    qa = QAService()
    
    # In kiểm tra chế độ kết nối
    use_pg = getattr(qa.retriever.vector_store, "use_pgvector", False)
    print(f"🔌 Trạng thái USE_PGVECTOR: {use_pg}")
    
    query = "các mức xử phạt vi phạm đối với điều khiển phương tiện đường bộ có chứa nồng độ cồn"
    print(f"🔍 Đang truy vấn: {query}")
    
    res = await qa.ask(query)
    
    print("\n--- KẾT QUẢ ---")
    print(f"👉 Số kết quả tìm thấy: {len(res.get('results', []))}")
    print(f"👉 Câu trả lời: {res.get('answer')}")

if __name__ == "__main__":
    asyncio.run(main())