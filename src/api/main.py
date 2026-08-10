import sys
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Any

# Đảm bảo có thể import từ src
ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.rag_core.config_manager import initialize_config
from src.rag_core.qa_service import QAService

# Singleton QAService instance
qa_service_instance = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global qa_service_instance
    print("[API INIT] Khởi tạo system config và QAService (Load FAISS & Embedding)...")
    try:
        initialize_config()
        qa_service_instance = QAService()
        print("[API INIT SUCCESS] ✅ Core RAG & Vector Store tải thành công!")
    except Exception as e:
        print(f"[API INIT ERROR] ❌ Lỗi khi khởi tạo QAService: {e}")
    yield
    print("[API SHUTDOWN] Đóng kết nối QAService...")
    qa_service_instance = None

app = FastAPI(title="Vietnamese Legal LLMOps - Core RAG API", lifespan=lifespan)

class ChatRequest(BaseModel):
    question: str
    top_k: Optional[int] = 5

class SourceItem(BaseModel):
    title: str
    snippet: str
    score: float

class ChatResponse(BaseModel):
    answer: str
    sources: List[SourceItem]

@app.get("/")
def read_root():
    return {"status": "ok", "message": "Core RAG API is running"}

@app.post("/ask", response_model=ChatResponse)
async def ask_question(request: ChatRequest):
    if not qa_service_instance:
        raise HTTPException(status_code=503, detail="QAService chưa sẵn sàng hoặc khởi tạo lỗi.")
    
    print(f"[API INCOMING] Yêu cầu tra cứu: '{request.question}' (top_k={request.top_k})")
    try:
        rag_res = await qa_service_instance.ask(request.question, top_k=request.top_k)
        
        raw_answer = rag_res.get("answer", "Không nhận được câu trả lời từ Core RAG AI.")
        raw_results = rag_res.get("results", [])
        
        sources = []
        for doc in raw_results:
            if isinstance(doc, dict):
                title = doc.get("document_id") or doc.get("source") or doc.get("title") or "Văn bản Pháp luật"
                snippet = doc.get("text") or doc.get("content") or doc.get("snippet") or ""
                score = float(doc.get("_rank_score") or doc.get("score") or 0.0)
                
                clean_snippet = snippet.strip()
                if len(clean_snippet) > 250:
                    clean_snippet = clean_snippet[:250] + "..."
                
                sources.append(SourceItem(
                    title=str(title),
                    snippet=clean_snippet,
                    score=score
                ))
        
        print(f"[API SUCCESS] Đã tạo phản hồi thành công (Số trích dẫn: {len(sources)})")
        return ChatResponse(answer=raw_answer, sources=sources)
        
    except Exception as e:
        print(f"[API ERROR] Lỗi khi xử lý QAService.ask(): {e}")
        raise HTTPException(status_code=500, detail=str(e))
