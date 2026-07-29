from __future__ import annotations

import asyncio
import inspect
import os
import sys
from pathlib import Path
from typing import Any

import chainlit as cl

# Thêm thư mục src vào sys.path để import các module RAG
PROJECT_ROOT = Path(__file__).resolve().parent
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from rag_core.document_manager import DocumentManager
from rag_core.qa_service import QAService

# Lấy tham số cấu hình từ môi trường
DEFAULT_TOP_K = int(os.getenv("QA_TOP_K", "5"))


# Callback xác thực tài khoản (Dùng test nhanh)
@cl.password_auth_callback
async def auth_callback(username: str, password: str):
    if username == "admin" and password == "admin":
        return cl.User(
            identifier=username,
            metadata={"role": "admin", "provider": "credentials"},
        )
    return None


@cl.on_chat_start
async def start_chatbot():
    try:
        # Khởi tạo QAService một lần duy nhất khi bắt đầu phiên chat
        qa_service = QAService()
        cl.user_session.set("qa_service", qa_service)

        await cl.Message(
            content=(
                "⚖️ **Xin chào! Tôi là Trợ lý AI Tra cứu Pháp luật Việt Nam.**\n\n"
                "Hệ thống đã kết nối thành công với Cơ sở dữ liệu **AWS RDS (pgvector)**.\n"
                "Bạn muốn tra cứu hoặc đặt câu hỏi về quy định pháp luật nào?"
            )
        ).send()
    except Exception as e:
        await cl.Message(content=f"❌ Khởi tạo hệ thống thất bại: {str(e)}").send()


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
        # 🌟 ĐIỂM SỬA MẤU CHỐT: Đưa qa_service.ask vào Thread riêng
        # Giúp Event Loop của Chainlit không bị block bởi truy vấn SQL & Gemini API
        response = await qa_service.ask(
            
            question=question,
            top_k=DEFAULT_TOP_K,
        )

        answer = str(response.get("answer", "")).strip()
        results = response.get("results", []) or []

        if not answer:
            answer = "Hiện không có thông tin về nội dung tìm kiếm trong cơ sở dữ liệu."

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
        loading_msg.content = f"❌ Hệ thống gặp sự cố khi xử lý câu hỏi: {str(e)}"
        await loading_msg.update()


# Khởi tạo manager phục vụ các tính năng Admin
doc_manager = DocumentManager()


def handle_admin_upload(pdf_bytes, title_input, so_ky_hieu_input, is_proc_input):
    try:
        new_id = doc_manager.add_document_from_pdf(
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