from fastapi.testclient import TestClient

from api import routes
from api.app import app


class _FakeQAService:
    async def ask(self, question: str, top_k: int | None = None):
        return {
            "answer": f"Trả lời: {question}",
            "results": [],
            "latency_ms": 12.5,
        }


def test_chat_works_without_dynamodb(monkeypatch):
    monkeypatch.setenv("AUTH_DISABLED", "true")
    monkeypatch.setenv("ENABLE_CHAT_HISTORY", "false")
    routes.history_store.cache_clear()
    monkeypatch.setattr(routes, "qa_service", lambda: _FakeQAService())

    response = TestClient(app).post(
        "/api/chat",
        json={"question": "Thời hiệu khởi kiện là bao lâu?", "top_k": 5},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["conversation_id"]
    assert payload["answer"].startswith("Trả lời:")
    assert payload["latency_ms"] == 12.5


def test_history_endpoint_explains_when_disabled(monkeypatch):
    monkeypatch.setenv("AUTH_DISABLED", "true")
    monkeypatch.setenv("ENABLE_CHAT_HISTORY", "false")
    routes.history_store.cache_clear()

    response = TestClient(app).get("/api/conversations")

    assert response.status_code == 503
    assert response.json()["detail"] == "Lưu lịch sử chat chưa được bật"
