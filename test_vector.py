import os
import sys
sys.path.insert(0, r'D:\Law-Chatbot\src')
from rag_core.vector_store import VectorStore
from rag_core.embeddings import EmbeddingService
import asyncio

async def test():
    store = VectorStore()
    print('use_pgvector:', store.use_pgvector)
    if store.use_pgvector:
        print('vector_index_available:', store.vector_index_available)
        # get count
        with store.conn.cursor() as cur:
            cur.execute('SELECT COUNT(*) FROM legal_chunks')
            cnt = cur.fetchone()[0]
            print('row count:', cnt)
            if cnt > 0:
                cur.execute('SELECT embedding FROM legal_chunks LIMIT 1')
                row = cur.fetchone()
                if row:
                    print('first embedding length:', len(row[0]) if row[0] else 0)
    # test search
    query = "các mức xử phạt đối với việc điều khiển phương tiện có nồng độ cồn"
    res = store.search(query, top_k=5)
    print('search results:', len(res))
    for i, r in enumerate(res):
        print(f"{i}: score={r.get('score')}, text={r.get('text')[:80]}")

if __name__ == '__main__':
    asyncio.run(test())