import asyncio
import sys
import os
sys.path.insert(0, r'D:\Law-Chatbot\src')
sys.path.insert(0, r'D:\Law-Chatbot')

from src.rag_core.qa_service import QAService

async def test():
    service = QAService()
    question = "các mức xử phạt đối với việc điều khiển phương tiện có nồng độ cồn"
    result = await service.ask(question, top_k=5)
    # Write result to file to avoid console encoding issues
    out_path = r'D:\Law-Chatbot\debug_result.txt'
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write("Result:\\n")
        for k, v in result.items():
            if isinstance(v, str):
                f.write(f"{k}: {v}\\n")
            else:
                f.write(f"{k}: {type(v)}\\n")
    print(f"Result written to {out_path}")

if __name__ == "__main__":
    asyncio.run(test())