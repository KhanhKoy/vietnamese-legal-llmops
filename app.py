import inspect
import os
import re
import sys
from pathlib import Path
from typing import Any

import chainlit as cl

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from rag_core.qa_service import QAService


DEFAULT_TOP_K = int(os.getenv("QA_TOP_K", "10"))
MAX_QUERY_VARIANTS = int(os.getenv("QA_MAX_QUERY_VARIANTS", "4"))
MIN_ACCEPTABLE_SCORE = float(os.getenv("QA_MIN_ACCEPTABLE_SCORE", "0.25"))

VIETNAMESE_STOPWORDS = {
    "và", "hoặc", "là", "của", "cho", "với", "một", "những", "các", "theo",
    "trong", "khi", "nào", "ở", "đâu", "thì", "có", "không", "bị", "được",
    "phải", "nên", "về", "tại", "từ", "đến", "này", "đó", "kia", "ấy"
}


def normalize_question(question: str) -> str:
    return re.sub(r"\s+", " ", (question or "").strip())


def extract_keywords(question: str) -> list[str]:
    tokens = re.findall(r"[A-Za-zÀ-ỹ0-9_]+", (question or "").lower())
    keywords = [
        token for token in tokens
        if token not in VIETNAMESE_STOPWORDS and len(token) > 1
    ]
    seen = set()
    unique_keywords = []
    for token in keywords:
        if token not in seen:
            seen.add(token)
            unique_keywords.append(token)
    return unique_keywords


def build_query_variants(question: str) -> list[str]:
    q = normalize_question(question)
    keywords = extract_keywords(q)

    variants = [q]
    if keywords:
        variants.append(" ".join(keywords[:12]))

    legal_boosters = [
        "điều khoản pháp luật",
        "quy định pháp luật",
        "căn cứ pháp lý",
        "nghị định thông tư luật",
    ]

    if any(term in q.lower() for term in ["điều", "khoản", "mục", "chương", "luật", "nghị định", "thông tư"]):
        variants.append(f"{q} {' '.join(legal_boosters)}")

    deduped = []
    seen = set()
    for item in variants:
        item = normalize_question(item)
        if item and item not in seen:
            seen.add(item)
            deduped.append(item)

    return deduped[:MAX_QUERY_VARIANTS]


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def doc_fingerprint(doc: dict) -> str:
    return str(
        doc.get("document_id")
        or doc.get("source")
        or doc.get("id")
        or doc.get("chunk_id")
        or doc.get("text", "")[:250]
    )


def merge_results(responses: list[dict]) -> list[dict]:
    merged: dict[str, dict] = {}

    for resp in responses:
        for doc in resp.get("results", []) or []:
            if not isinstance(doc, dict):
                continue

            fp = doc_fingerprint(doc)
            current = merged.get(fp)

            score = safe_float(doc.get("score", 0.0))
            if score <= 0.0:
                score = 1.0

            if current is None or score > safe_float(current.get("score", 0.0)):
                new_doc = dict(doc)
                new_doc["score"] = score
                merged[fp] = new_doc

    return sorted(merged.values(), key=lambda d: safe_float(d.get("score", 0.0)), reverse=True)


async def call_qa_service(qa_service: QAService, question: str):
    ask_fn = qa_service.ask
    signature = inspect.signature(ask_fn)
    params = signature.parameters

    kwargs: dict[str, Any] = {"question": question}

    for name in ("top_k", "k", "limit", "num_results"):
        if name in params:
            kwargs[name] = DEFAULT_TOP_K
            break

    if "rerank" in params:
        kwargs["rerank"] = True

    result = ask_fn(**kwargs)
    if inspect.isawaitable(result):
        return await result
    return result


# Authentication callback
@cl.password_auth_callback
async def auth_callback(username: str, password: str):
    # For demo, use hardcoded credentials. In production, validate against a database.
    if username == "admin" and password == "admin":
        return cl.User(
            identifier=username,
            metadata={"role": "admin", "provider": "credentials"},
        )
    # Optionally, allow any user with a placeholder (not recommended for production)
    # return cl.User(identifier=username, metadata={"role": "user", "provider": "credentials"})
    return None


@cl.on_chat_start
async def start_chatbot():
    try:
        qa_service = QAService()
        cl.user_session.set("qa_service", qa_service)

        await cl.Message(
            content=(
                "⚖️ **Xin chào! Tôi là Trợ lý AI tra cứu Luật pháp Việt Nam.**\n\n"
                "Bạn muốn tra cứu vấn đề gì?"
            )
        ).send()
    except Exception as e:
        await cl.Message(content=f"❌ Khởi tạo hệ thống thất bại: {str(e)}").send()


@cl.on_message
async def handle_user_message(message: cl.Message):
    qa_service = cl.user_session.get("qa_service")

    if qa_service is None:
        await cl.Message(content="❌ Phiên làm việc chưa khởi tạo QAService. Vui lòng tải lại trang.").send()
        return

    loading_msg = cl.Message(content="🔍 *Đang truy lục các điều luật liên quan...*")
    await loading_msg.send()

    try:
        question = normalize_question(message.content)
        query_variants = build_query_variants(question)

        responses = []
        for variant in query_variants:
            resp = await call_qa_service(qa_service, variant)
            if isinstance(resp, dict):
                responses.append(resp)

        if not responses:
            loading_msg.content = "⚠️ Tôi chưa truy hồi được kết quả phù hợp."
            await loading_msg.update()
            return

        merged_results = merge_results(responses)
        best = max(
            responses,
            key=lambda resp: (
                max((safe_float(d.get("score", 0.0)) for d in resp.get("results", []) or []), default=0.0),
                len(resp.get("results", []) or []),
                len(str(resp.get("answer", "")).strip()),
            ),
            default={"answer": "", "results": []},
        )

        answer = str(best.get("answer", "")).strip()
        if not answer:
            answer = "Tôi chưa thể tổng hợp câu trả lời chắc chắn từ dữ liệu hiện có."

        loading_msg.content = answer
        await loading_msg.update()

        if merged_results:
            source_section = "\n\n---\n📊 **Cơ sở pháp lý tìm thấy:**\n"
            for idx, doc in enumerate(merged_results[:10], start=1):
                doc_id = doc.get("document_id", "Không rõ nguồn")
                score = safe_float(doc.get("score", 0.0))
                snippet = str(doc.get("text", ""))[:150].replace("\n", " ")
                source_section += (
                    f"📌 **[{idx}] Văn bản:** `{doc_id}` | *Độ tương đồng:* `{score:.4f}`\n"
                    f"> *Trích đoạn:* {snippet}...\n\n"
                )

            await cl.Message(content=source_section).send()

    except Exception as e:
        loading_msg.content = f"❌ Hệ thống gặp sự cố khi xử lý câu hỏi: {str(e)}"
        await loading_msg.update()