import os
import sys
sys.path.insert(0, r'D:\Law-Chatbot\src')
from rag_core.vector_store import VectorStore
import asyncio

async def test():
    store = VectorStore()
    print('use_pgvector:', store.use_pgvector)
    if store.use_pgvector:
        with store.conn.cursor() as cur:
            # check if any rows have embedding not null
            cur.execute("SELECT COUNT(*) FROM legal_chunks WHERE embedding IS NOT NULL")
            cnt = cur.fetchone()[0]
            print('rows with embedding:', cnt)
            # check a sample embedding
            if cnt > 0:
                cur.execute("SELECT embedding FROM legal_chunks WHERE embedding IS NOT NULL LIMIT 1")
                row = cur.fetchone()
                print('sample embedding type:', type(row[0]))
                # print first few components
                emb = row[0]
                if hasattr(emb, '__len__'):
                    print('length:', len(emb))
                else:
                    print('it is a Vector object:', emb)
                    # try to get values
                    try:
                        print('as list:', list(emb))
                    except Exception as e:
                        print('cannot convert:', e)
    # test embedding generation
    from rag_core.embeddings import EmbeddingService
    embedder = EmbeddingService()
    q_emb = embedder.embed_query("test")
    print('query embedding length:', len(q_emb))
    print('first 5:', q_emb[:5])
    # now try a manual vector search using sql
    if store.use_pgvector:
        with store.conn.cursor() as cur:
            # set statement timeout high
            cur.execute("SET statement_timeout = 0")
            # use vector literal
            vec_str = '[' + ','.join(str(x) for x in q_emb) + ']'
            sql = f"""
                SELECT id, chunk_id, text, (embedding <=> %s::vector) AS distance
                FROM legal_chunks
                WHERE NOT (metadata_json ? 'deleted_at')
                ORDER BY distance ASC
                LIMIT 5
            """
            cur.execute(sql, (vec_str,))
            rows = cur.fetchall()
            print('raw sql results:', len(rows))
            for r in rows:
                print(r[0], r[1], r[2][:50], float(r[3]))
if __name__ == '__main__':
    asyncio.run(test())