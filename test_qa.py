import os
import sys
sys.path.insert(0, r'D:\Law-Chatbot\src')
from rag_core.qa_service import QAService
import asyncio

async def test():
    service = QAService()
    question = "các mức xử phạt đối với việc điều khiển phương tiện có nồng độ cồn"
    result = await service.ask(question, top_k=5)
    print("Answer:", result.get("answer"))
    print("Results count:", len(result.get("results", [])))
    for i, r in enumerate(result.get("results", [])):
        print(f"{i}: score={r.get('score')}, text={r.get('text')[:200]}")

if __name__ == "__main__":
    asyncio.run(test())