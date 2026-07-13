import os
import sys
from pathlib import Path
import chainlit as cl

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from rag_core.qa_service import QAService


@cl.on_chat_start
async def start_chatbot():
    try:
        qa_service = QAService()
        cl.user_session.set("qa_service", qa_service)

        await cl.Message(
            content="⚖️ **Xin chào! Tôi là Trợ lý AI tra cứu Luật pháp Việt Nam.**\n\nTôi có thể giúp bạn tìm kiếm thông tin hành chính dựa trên bộ dữ liệu luật được nạp sẵn. Bạn muốn tra cứu vấn đề gì?"
        ).send()
    except Exception as e:
        await cl.Message(content=f"❌ Khởi tạo hệ thống thất bại: {str(e)}").send()


@cl.on_message
async def handle_user_message(message: cl.Message):
    qa_service = cl.user_session.get("qa_service")

    if qa_service is None:
        await cl.Message(
            content="❌ Phiên làm việc chưa khởi tạo QAService. Vui lòng tải lại trang."
        ).send()
        return

    loading_msg = cl.Message(content="🔍 *Đang truy lục các điều luật liên quan và tổng hợp câu trả lời...*")
    await loading_msg.send()

    try:
        response_data = qa_service.ask(question=message.content)

        loading_msg.content = response_data["answer"]
        await loading_msg.update()

        if response_data.get("results"):
            source_section = "\n\n---\n📊 **Cơ sở pháp lý được hệ thống tìm thấy:**\n"
            for idx, doc in enumerate(response_data["results"], start=1):
                doc_id = doc.get("document_id", "Không rõ nguồn")
                score = doc.get("score", 0.0)
                snippet = doc.get("text", "")[:150].replace("\n", " ") + "..."

                source_section += f"📌 **[{idx}] Văn bản:** `{doc_id}` | *Độ tương đồng:* `{score:.4f}`\n"
                source_section += f"> *Trích đoạn:* {snippet}\n\n"

            await cl.Message(content=source_section).send()

    except Exception as e:
        loading_msg.content = f"❌ Hệ thống gặp sự cố khi xử lý câu hỏi: {str(e)}"
        await loading_msg.update()