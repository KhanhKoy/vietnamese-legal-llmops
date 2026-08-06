import asyncio

from rag_core.retriever import Retriever


class FakeEmbedder:
    pass


class FakePgVectorStore:
    use_pgvector = True

    def __init__(self):
        self.calls = []

    def search(self, query, top_k=5, embedder=None):
        self.calls.append((query, top_k))
        return [
            {
                "document_id": "law-1",
                "chunk_id": "law-1::chunk_0",
                "text": "Điều 1. Nội dung thử nghiệm",
                "metadata": {},
                "score": 0.9,
            }
        ]


class EmptyPgVectorStore(FakePgVectorStore):
    def search(self, query, top_k=5, embedder=None):
        self.calls.append((query, top_k))
        return []


def test_pgvector_retrieval_executes_one_search_only():
    store = FakePgVectorStore()
    retriever = Retriever(vector_store=store, embedder=FakeEmbedder())

    results = asyncio.run(retriever.retrieve("quy định thử nghiệm", top_k=15))

    assert len(results) == 1
    assert store.calls == [("quy định thử nghiệm", 15)]


def test_empty_pgvector_result_is_not_retried_with_other_signatures():
    store = EmptyPgVectorStore()
    retriever = Retriever(vector_store=store, embedder=FakeEmbedder())

    results = asyncio.run(retriever.retrieve("không có kết quả", top_k=5))

    assert results == []
    assert store.calls == [("không có kết quả", 5)]
