import time
from typing import Any, Dict, List

import requests
import streamlit as st

from src.storage import (
    append_message,
    create_chat_session,
    delete_chat_session,
    get_chat_session,
    get_user_by_username,
    list_chat_sessions,
    set_feedback,
    update_chat_session_title,
)

SUGGESTION_POOLS = [
    [
        "Thời gian thử việc tối đa theo Luật Lao động 2019?",
        "Thủ tục thành lập công ty TNHH 1 thành viên?",
        "Mức phạt nồng độ cồn xe máy mới nhất 2026?",
        "Quyền thừa kế đất đai không di chúc chia thế nào?",
    ],
    [
        "Điều kiện đơn phương chấm dứt hợp đồng lao động?",
        "Quy trình giải quyết ly hôn thuận tình tại Tòa án?",
        "Thời hiệu xử lý vi phạm hành chính về thuế?",
        "Thủ tục cấp Giấy chứng nhận quyền sử dụng đất?",
    ],
    [
        "Mức lương tối thiểu vùng mới nhất theo Nghị định?",
        "Thời hạn nộp thuế thu nhập doanh nghiệp hàng quý?",
        "Trách nhiệm bồi thường thiệt hại ngoài hợp đồng?",
        "Thủ tục đăng ký hộ kinh doanh cá thể tại UBND?",
    ],
]

API_URL = "http://127.0.0.1:8000/ask"


def load_user_sessions(username: str) -> List[Dict[str, Any]]:
    sessions = []
    for meta in list_chat_sessions(username):
        data = get_chat_session(meta["id"])
        sessions.append(
            {
                "id": data["session"]["id"],
                "user": username,
                "title": data["session"]["title"],
                "created_at": data["session"]["created_at"],
                "last_updated": data["session"]["updated_at"],
                "messages": data["messages"],
            }
        )
    return sessions


def process_user_query(prompt: str, username: str, session_id: str) -> None:
    if not session_id:
        return

    session = get_chat_session(session_id)
    if session["session"]["title"] == "Cuộc trò chuyện mới":
        clean_t = prompt.strip()
        if len(clean_t) > 22:
            clean_t = clean_t[:22] + "..."
        update_chat_session_title(session_id, clean_t)

    append_message(session_id, "user", prompt, [])

    top_k = st.session_state.get("settings", {}).get("top_k", 5)
    try:
        payload = {"question": prompt, "top_k": top_k}
        response = requests.post(API_URL, json=payload, timeout=60)
        if response.status_code == 200:
            data = response.json()
            answer_content = data.get("answer", "Không có câu trả lời.")
            sources = data.get("sources", [])
        else:
            answer_content = f"⚠️ Lỗi từ Backend API: HTTP {response.status_code} - {response.text}"
            sources = []
    except requests.exceptions.ConnectionError:
        answer_content = "⚠️ Không thể kết nối tới Backend API. Vui lòng đảm bảo bạn đã khởi chạy FastAPI server bằng lệnh: `python -m uvicorn src.api.main:app --reload --port 8000`"
        sources = []
    except Exception as e:
        answer_content = f"⚠️ Đã xảy ra lỗi khi gọi Backend API: {e}"
        sources = []

    append_message(session_id, "assistant", answer_content, sources, None)


def show():
    current_user = st.session_state.get("user") or "user1"
    user_record = get_user_by_username(current_user)
    if user_record is None:
        st.error("Không tìm thấy người dùng trong hệ thống SQLite.")
        return

    if "suggestion_index" not in st.session_state:
        st.session_state.suggestion_index = 0

    user_sessions = load_user_sessions(current_user)
    if not user_sessions:
        new_session = create_chat_session(user_record["id"], "Cuộc trò chuyện mới")
        append_message(
            new_session["id"],
            "assistant",
            f"Xin chào **{current_user}**! Tôi là **Trợ lý Pháp luật Việt Nam**. Bạn cần tra cứu vấn đề pháp lý gì?",
            [],
            None,
        )
        user_sessions = load_user_sessions(current_user)

    current_active_id = st.session_state.get("active_session_id")
    active_sess = next((s for s in user_sessions if s["id"] == current_active_id), user_sessions[0])
    st.session_state.active_session_id = active_sess["id"]

    with st.sidebar:
        st.markdown(f"<h2 style='font-size: 2.2rem; font-weight: 800; margin-bottom: 0; color: #0F172A;'>👤 {current_user}</h2>", unsafe_allow_html=True)
        st.markdown("<p style='font-size: 1.1rem; color: #475569; margin-top: 2px; margin-bottom: 12px;'>Trợ lý Pháp luật AI • Trực tuyến</p>", unsafe_allow_html=True)
        st.write("---")
        st.markdown("<h2 style='margin-bottom: 12px;'> QUẢN LÝ PHIÊN LÀM VIỆC</h2>", unsafe_allow_html=True)

        if st.button("➕ Cuộc trò chuyện mới", use_container_width=True, type="primary", key="btn_new_chat"):
            new_session = create_chat_session(user_record["id"], "Cuộc trò chuyện mới")
            append_message(
                new_session["id"],
                "assistant",
                f"Xin chào **{current_user}**! Tôi là **Trợ lý Pháp luật Việt Nam**. Bạn cần tra cứu vấn đề pháp lý gì?",
                [],
                None,
            )
            st.session_state.active_session_id = new_session["id"]
            st.toast("Đã tạo phiên làm việc mới!", icon="➕")
            st.rerun()

        st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)

        for sess in user_sessions:
            is_active = sess["id"] == active_sess["id"]
            col_title, col_del = st.columns([0.78, 0.22], vertical_alignment="center")
            display_title = sess["title"]
            if len(display_title) > 14:
                display_title = display_title[:14] + "..."
            btn_label = f"{'💬 ' if not is_active else ''}{display_title} - {sess.get('created_at', '')}"

            with col_title:
                btn_type = "primary" if is_active else "secondary"
                if st.button(btn_label, key=f"sel_{sess['id']}", use_container_width=True, type=btn_type):
                    st.session_state.active_session_id = sess["id"]
                    st.rerun()

            with col_del:
                with st.popover("🗑️", help="Xóa phiên này", use_container_width=True):
                    st.write("Xóa phiên này?")
                    if st.button("Xóa", key=f"del_{sess['id']}", type="primary", use_container_width=True):
                        delete_chat_session(sess["id"])
                        st.session_state.active_session_id = None
                        st.toast("Đã xóa phiên làm việc!", icon="🗑️")
                        st.rerun()

        st.markdown("---")

        if st.button("🗑️ Xóa toàn bộ lịch sử trò chuyện", use_container_width=True, key="btn_clear_all"):
            for sess in user_sessions:
                delete_chat_session(sess["id"])
            st.session_state.active_session_id = None
            new_session = create_chat_session(user_record["id"], "Cuộc trò chuyện mới")
            append_message(new_session["id"], "assistant", f"Xin chào **{current_user}**! Tôi là **Trợ lý Pháp luật Việt Nam**. Bạn muốn tra cứu hay tư vấn vấn đề pháp lý nào?", [], None)
            st.toast("Đã xóa toàn bộ lịch sử!", icon="🗑️")
            st.rerun()

        st.markdown("---")
        if st.button("Đăng xuất", use_container_width=True, key="btn_logout"):
            st.session_state.logged_in = False
            st.session_state.user = None
            st.session_state.role = None
            st.session_state.current_user_id = None
            st.session_state.page = "login"
            st.toast("Đã đăng xuất tài khoản!", icon="🚪")
            st.rerun()

    st.title("⚖️ Trợ lý Pháp luật Việt Nam")
    st.markdown("<p style='font-size: 1.3rem; color: #475569;'>Tra cứu văn bản pháp luật, Bộ luật Dân sự, Luật Lao động, Bộ luật Hình sự và tư vấn pháp lý thông minh với RAG AI.</p>", unsafe_allow_html=True)

    messages = active_sess["messages"]
    for idx, msg in enumerate(messages):
        avatar = "⚖️" if msg["role"] == "assistant" else "👤"
        with st.chat_message(msg["role"], avatar=avatar):
            st.markdown(msg["content"])
            if msg["role"] == "assistant":
                if msg.get("sources"):
                    st.caption("✅ *Phản hồi được trả về từ FastAPI Backend Core RAG*")
                    with st.expander("📚 Nguồn tham khảo văn bản pháp luật"):
                        for src in msg["sources"]:
                            title = src.get("title") or src.get("document_id") or "Văn bản"
                            score = src.get("score", 0.0) * 100
                            snippet = src.get("snippet") or src.get("text", "")
                            st.markdown(f"• **{title}** *(Độ tương đồng: `{score:.1f}%`)*")
                            st.caption(f"Trích dẫn: \"{snippet}\"")
            if msg["role"] == "assistant":
                col_fb1, col_fb2, _ = st.columns([0.1, 0.1, 0.8])
                current_fb = msg.get("feedback")
                with col_fb1:
                    like_type = "primary" if current_fb == "like" else "secondary"
                    if st.button("👍", key=f"like_{active_sess['id']}_{idx}", type=like_type, help="Hữu ích"):
                        new_feedback = None if current_fb == "like" else "like"
                        set_feedback(user_record["id"], active_sess["id"], msg.get("id"), new_feedback)
                        st.toast("Cảm ơn bạn đã đánh giá hữu ích!" if new_feedback == "like" else "Đã bỏ chọn đánh giá", icon="👍" if new_feedback == "like" else "↩️")
                        st.rerun()
                with col_fb2:
                    dislike_type = "primary" if current_fb == "dislike" else "secondary"
                    if st.button("👎", key=f"dislike_{active_sess['id']}_{idx}", type=dislike_type, help="Chưa phù hợp"):
                        new_feedback = None if current_fb == "dislike" else "dislike"
                        set_feedback(user_record["id"], active_sess["id"], msg.get("id"), new_feedback)
                        st.toast("Đã ghi nhận ý kiến để cải thiện RAG AI!" if new_feedback == "dislike" else "Đã bỏ chọn đánh giá", icon="👎" if new_feedback == "dislike" else "↩️")
                        st.rerun()

    curr_suggestions = SUGGESTION_POOLS[st.session_state.suggestion_index % len(SUGGESTION_POOLS)]
    col_sugg_label, col_sugg_ref = st.columns([6, 1])
    with col_sugg_label:
        st.markdown("**Gợi ý câu hỏi pháp lý:**")
    with col_sugg_ref:
        if st.button("🔄 Làm mới", help="Tải danh sách gợi ý khác"):
            st.session_state.suggestion_index += 1
            st.toast("Đã làm mới danh sách gợi ý câu hỏi!", icon="🔄")
            st.rerun()

    sugg_cols = st.columns(len(curr_suggestions))
    for i, sugg_text in enumerate(curr_suggestions):
        with sugg_cols[i]:
            if st.button(sugg_text, key=f"sugg_{i}_{st.session_state.suggestion_index}"):
                with st.spinner("🔍 Đang truy xuất cơ sở dữ liệu văn bản pháp luật và tổng hợp câu trả lời RAG..."):
                    process_user_query(sugg_text, current_user, active_sess["id"])
                st.rerun()

    st.markdown("<div style='margin-top: -0.8rem;'></div>", unsafe_allow_html=True)
    if prompt := st.chat_input("Nhập câu hỏi pháp lý của bạn... (vd: Thời gian thử việc tối đa Luật Lao động 2019 là bao lâu?)"):
        with st.spinner("🔍 Đang truy xuất cơ sở dữ liệu văn bản pháp luật và tổng hợp câu trả lời RAG..."):
            process_user_query(prompt, current_user, active_sess["id"])
        st.rerun()