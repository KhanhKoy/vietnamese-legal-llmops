import os, sys
sys.path.insert(0, r'D:\Law-Chatbot\src')
from rag_core.vector_store import VectorStore
from rag_core.embeddings import EmbeddingService

store = VectorStore()
embedder = EmbeddingService()
q = "các mức xử phạt đối với việc điều khiển phương tiện có nồng độ cồn"
vec = embedder.embed_query(q)
print('vec len', len(vec))
# call internal
res = store._search_pgvector(q, top_k=5)
print('_search_pgvector result count:', len(res))
for i, r in enumerate(res):
    print(i, r.get('score'), r.get('text')[:80] if r.get('text') else None)