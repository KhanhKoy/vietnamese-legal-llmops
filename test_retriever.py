import os, sys, asyncio
sys.path.insert(0, r'D:\Law-Chatbot\src')
from rag_core.retriever import Retriever
from rag_core.vector_store import VectorStore
from rag_core.embeddings import EmbeddingService

async def test():
    vs = VectorStore()
    emb = EmbeddingService()
    ret = Retriever(vector_store=vs, embedder=emb)
    print('vector_store.use_pgvector:', vs.use_pgvector)
    print('vector_store.vector_index_available:', vs.vector_index_available)
    res = await ret.retrieve("cách mức xử phạt đối với việc điều khiển phương tiện có nồng độ cồn", top_k=5)
    print('retriever result count:', len(res))
    for i, r in enumerate(res):
        print(i, r.get('score'), r.get('text')[:80] if r.get('text') else None)

if __name__ == '__main__':
    asyncio.run(test())