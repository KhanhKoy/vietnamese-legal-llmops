from __future__ import annotations

import asyncio
import os
import sys
from functools import lru_cache
from pathlib import Path

import chainlit as cl

# Thêm thư mục src vào sys.path để import các module RAG
PROJECT_ROOT = Path(__file__).resolve().parent
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from rag_core.document_manager import DocumentManager  # noqa: E402
from rag_core.qa_service import QAService  # noqa: E402
from services.chat_history import ChatHistoryStore  # noqa: E402

# Lấy tham số cấu hình từ môi trường
DEFAULT_TOP_K = int(os.getenv("QA_TOP_K", "5"))


# Local-only password callback. Production should run behind Cognito/FastAPI;
# there is intentionally no default password in source code.
async def auth_callback(username: str, password: str):
    expected_user = os.getenv("CHAINLIT_DEV_USERNAME", "")
    expected_password = os.getenv("CHAINLIT_DEV_PASSWORD", "")
    if expected_user and expected_password and username == expected_user and password == expected_password:
        return cl.User(
            identifier=username,
            metadata={"role": "admin", "provider": "credentials"},
        )
    return None


# Register local password authentication only when it is actually configured.
# Otherwise Chainlit requires CHAINLIT_AUTH_SECRET and the blank credentials
# make every login fail.
if os.getenv("CHAINLIT_DEV_USERNAME") and os.getenv("CHAINLIT_DEV_PASSWORD"):
    cl.password_auth_callback(auth_callback)


@cl.on_chat_start
async def start_chatbot():
    try:
        # Model embedding is expensive; share one initialized service across
        # Chainlit sessions instead of loading it again for every browser tab.
        qa_service = await asyncio.to_thread(get_qa_service)
        cl.user_session.set("qa_service", qa_service)

        if os.getenv("ENABLE_CHAT_HISTORY", "0").lower() in {"1", "true", "yes", "y"}:
            user = cl.user_session.get("user")
            user_id = getattr(user, "identifier", "anonymous")
            history = ChatHistoryStore()
            conversation_id = await asyncio.to_thread(
                history.create_conversation, user_id, "Cuộc trò chuyện Chainlit"
            )
            cl.user_session.set("history_store", history)
            cl.user_session.set("conversation_id", conversation_id)
            cl.user_session.set("history_user_id", user_id)

        await cl.Message(
            content=(
                "⚖️ **Xin chào! Tôi là Trợ lý AI Tra cứu Pháp luật Việt Nam.**\n\n"
                "Hệ thống tra cứu văn bản pháp luật đã sẵn sàng.\n"
                "Bạn muốn tra cứu hoặc đặt câu hỏi về quy định pháp luật nào?"
            )
        ).send()
    except Exception as e:
        print(f"[Chainlit] initialization failed: {e}")
        await cl.Message(content="❌ Khởi tạo hệ thống thất bại. Vui lòng thử lại sau.").send()


@cl.on_message
async def handle_user_message(message: cl.Message):
    qa_service: QAService = cl.user_session.get("qa_service")  # type: ignore

    if qa_service is None:
        await cl.Message(content="❌ Phiên làm việc chưa khởi tạo QAService. Vui lòng tải lại trang.").send()
        return

    question = message.content.strip()
    if not question:
        return

    loading_msg = cl.Message(content="🔍 *Đang tối ưu hóa truy vấn & tra cứu văn bản pháp luật trên AWS RDS...*")
    await loading_msg.send()

    try:
        history: ChatHistoryStore | None = cl.user_session.get("history_store")
        conversation_id = cl.user_session.get("conversation_id")
        history_user_id = cl.user_session.get("history_user_id")
        if history and conversation_id and history_user_id:
            await asyncio.to_thread(
                history.append_message,
                conversation_id,
                history_user_id,
                "user",
                question,
            )

        response = await qa_service.ask(
            question=question,
            top_k=DEFAULT_TOP_K,
        )

        answer = str(response.get("answer", "")).strip()
        results = response.get("results", []) or []

        if not answer:
            answer = "Hiện không có thông tin về nội dung tìm kiếm trong cơ sở dữ liệu."

        if history and conversation_id and history_user_id:
            sources = [str(item.get("chunk_id")) for item in results if item.get("chunk_id")]
            await asyncio.to_thread(
                history.append_message,
                conversation_id,
                history_user_id,
                "assistant",
                answer,
                sources,
                response.get("latency_ms"),
            )

        # 1. Cập nhật câu trả lời tổng hợp từ LLM
        loading_msg.content = answer
        await loading_msg.update()

        # 2. Hiển thị Trích dẫn Nguồn & Metadata chi tiết bên dưới
        if results:
            source_section = "### 📊 **Cơ sở pháp lý tìm thấy trong CSDL:**\n\n"
            
            for idx, doc in enumerate(results[:DEFAULT_TOP_K], start=1):
                score = float(doc.get("score", doc.get("_rank_score", 0.0)))
                text_snippet = str(doc.get("text", "")).strip()[:180].replace("\n", " ")
                metadata = doc.get("metadata", {})

                # Bóc tách Metadata đã được chuẩn hóa từ PostgreSQL
                title = metadata.get("title") or doc.get("document_id") or "Không rõ tiêu đề"
                so_ky_hieu = metadata.get("so_ky_hieu", "N/A")
                loai_vb = metadata.get("loai_van_ban", "N/A")
                co_quan = metadata.get("co_quan_ban_hanh", "N/A")
                is_proc = metadata.get("is_procedural_law", False)
                proc_tag = " ⚖️ *(Luật Tố tụng)*" if is_proc else ""

                source_section += (
                    f"**[{idx}] {title}**{proc_tag}\n"
                    f"* **Số hiệu:** `{so_ky_hieu}` | **Loại:** `{loai_vb}` | **Cơ quan:** `{co_quan}` | **Độ tương đồng:** `{score:.4f}`\n"
                    f"> *Trích đoạn:* {text_snippet}...\n\n"
                )

            await cl.Message(content=source_section).send()

    except Exception as e:
        print(f"[Chainlit] question handling failed: {e}")
        loading_msg.content = "❌ Hệ thống gặp sự cố khi xử lý câu hỏi. Vui lòng thử lại."
        await loading_msg.update()


@lru_cache(maxsize=1)
def get_qa_service() -> QAService:
    return QAService()


@lru_cache(maxsize=1)
def get_document_manager() -> DocumentManager:
    # Do not load a second embedding model during normal chat startup. Admin
    # dependencies are initialized only when the upload helper is actually used.
    return DocumentManager()


def handle_admin_upload(pdf_bytes, title_input, so_ky_hieu_input, is_proc_input):
    try:
        new_id = get_document_manager().add_document_from_pdf(
            pdf_file_bytes=pdf_bytes,
            title=title_input,
            so_ky_hieu=so_ky_hieu_input,
            loai_van_ban="Thông tư",
            co_quan_ban_hanh="Bộ Tư pháp",
            is_procedural_law=is_proc_input,
            tinh_trang_hieu_luc="Còn hiệu lực",
        )
        print(f"✅ Thêm văn bản thành công với ID: {new_id}")
    except Exception as e:
        print(f"❌ Lỗi khi thêm văn bản: {e}")
