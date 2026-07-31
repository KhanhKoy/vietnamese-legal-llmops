import streamlit as st
import time

# TODO: tích hợp RAG pipeline thật
# TODO: thay bằng database thật

SUGGESTION_POOLS = [
    [
        "Thời gian thử việc tối đa theo Luật Lao động 2019?",
        "Thủ tục thành lập công ty TNHH 1 thành viên?",
        "Mức phạt nồng độ cồn xe máy mới nhất 2026?",
        "Quyền thừa kế đất đai không di chúc chia thế nào?"
    ],
    [
        "Điều kiện đơn phương chấm dứt hợp đồng lao động?",
        "Quy trình giải quyết ly hôn thuận tình tại Tòa án?",
        "Thời hiệu xử lý vi phạm hành chính về thuế?",
        "Thủ tục cấp Giấy chứng nhận quyền sử dụng đất?"
    ],
    [
        "Mức lương tối thiểu vùng mới nhất theo Nghị định?",
        "Thời hạn nộp thuế thu nhập doanh nghiệp hàng quý?",
        "Trách nhiệm bồi thường thiệt hại ngoài hợp đồng?",
        "Thủ tục đăng ký hộ kinh doanh cá thể tại UBND?"
    ]
]

# ================= HÀM XỬ LÝ GỌI CORE / GENERATE RESPONSE =================
def process_user_query(prompt: str, active_sess: dict):
    """Xử lý thêm câu hỏi của user và gọi Core RAG AI tạo phản hồi"""
    messages = active_sess["messages"]
    
    # 1. Thêm câu hỏi của user
    messages.append({"role": "user", "content": prompt})
    
    # Cập nhật title phiên làm việc nếu là phiên mới
    if active_sess["title"] == "Cuộc trò chuyện mới":
        clean_t = prompt.strip()
        if len(clean_t) > 22:
            clean_t = clean_t[:22] + "..."
        active_sess["title"] = clean_t
    active_sess["last_updated"] = time.strftime("%H:%M")

    # 2. Giả lập / Gọi Core RAG AI xử lý
    # TODO: Thay đoạn mock này bằng logic RAG thật của bạn
    time.sleep(1.0)
    mock_answer = f"Căn cứ theo quy định của pháp luật Việt Nam đối với câu hỏi: **\"{prompt}\"**:\n\n1. **Quy định chung:** Các bên có quyền thỏa thuận về quyền, nghĩa vụ và trách nhiệm pháp lý theo quy định của Luật chuyên ngành.\n2. **Chi tiết điều khoản:** Việc thực hiện phải đảm bảo đầy đủ căn cứ pháp lý, hồ sơ chứng từ và tuân thủ trình tự thủ tục hành chính.\n3. **Khuyến nghị pháp lý:** Nên đối chiếu trực tiếp với các văn bản Luật, Nghị định hướng dẫn hiện hành trước khi thực hiện."
    mock_sources = [
        {"title": "Bộ luật Dân sự 2015 (Luật số 91/2015/QH13)", "snippet": "Cá nhân, pháp nhân thực hiện quyền dân sự theo ý chí của mình...", "score": 0.92},
        {"title": "Bộ luật Lao động 2019 (Luật số 45/2019/QH14)", "snippet": "Thời gian thử việc do hai bên thỏa thuận căn cứ tính chất công việc...", "score": 0.88}
    ]

    # 3. Thêm câu trả lời vào lịch sử tin nhắn
    messages.append({
        "role": "assistant",
        "content": mock_answer,
        "sources": mock_sources,
        "feedback": None
    })

def show():
    current_user = st.session_state.get("user") or "user1"

    # 1. KHỞI TẠO STATE CẦN THIẾT
    if "suggestion_index" not in st.session_state:
        st.session_state.suggestion_index = 0

    if "chat_sessions" not in st.session_state:
        st.session_state.chat_sessions = []

    # User chat sessions list filtering
    user_sessions = [s for s in st.session_state.chat_sessions if s.get("user") == current_user]
    
    # Ensure at least one session exists
    if not user_sessions:
        now_time = time.strftime("%H:%M")
        new_id = f"sess_{int(time.time()*1000)}"
        new_sess = {
            "id": new_id,
            "user": current_user,
            "title": "Cuộc trò chuyện mới",
            "created_at": now_time,
            "last_updated": now_time,
            "messages": [
                {
                    "role": "assistant",
                    "content": f"Xin chào **{current_user}**! Tôi là **Trợ lý Pháp luật Việt Nam**. Bạn muốn tra cứu hay tư vấn vấn đề pháp lý nào?",
                    "sources": [
                        {"title": "Bộ luật Dân sự 2015", "snippet": "Quy định nguyên tắc bình đẳng, tự do thỏa thuận trong quan hệ dân sự...", "score": 0.95}
                    ],
                    "feedback": None
                }
            ]
        }
        st.session_state.chat_sessions.append(new_sess)
        st.session_state.active_session_id = new_id
        st.session_state.current_session_id = new_id
        user_sessions = [new_sess]

    # Active session reference
    current_active_id = getattr(st.session_state, "active_session_id", None) or getattr(st.session_state, "current_session_id", None)
    active_sess = next((s for s in user_sessions if s["id"] == current_active_id), user_sessions[0])
    st.session_state.active_session_id = active_sess["id"]
    st.session_state.current_session_id = active_sess["id"]

    # ================= SIDEBAR (USER) =================
    with st.sidebar:
        # Thông tin người dùng
        st.markdown(f"<h2 style='font-size: 2.2rem; font-weight: 800; margin-bottom: 0; color: #0F172A;'>👤 {current_user}</h2>", unsafe_allow_html=True)
        st.markdown("<p style='font-size: 1.1rem; color: #475569; margin-top: 2px; margin-bottom: 12px;'>Trợ lý Pháp luật AI • Trực tuyến</p>", unsafe_allow_html=True)
        st.write("---")

        st.markdown("<h2 style='margin-bottom: 12px;'> QUẢN LÝ PHIÊN LÀM VIỆC</h2>", unsafe_allow_html=True)

        # Nút Tạo cuộc trò chuyện mới
        if st.button("➕ Cuộc trò chuyện mới", use_container_width=True, type="primary", key="btn_new_chat"):
            now_time = time.strftime("%H:%M")
            new_id = f"sess_{int(time.time()*1000)}"
            new_sess = {
                "id": new_id,
                "user": current_user,
                "title": "Cuộc trò chuyện mới",
                "created_at": now_time,
                "last_updated": now_time,
                "messages": [
                    {
                        "role": "assistant",
                        "content": f"Xin chào **{current_user}**! Tôi là **Trợ lý Pháp luật Việt Nam**. Bạn cần tra cứu vấn đề pháp lý gì?",
                        "sources": [],
                        "feedback": None
                    }
                ]
            }
            st.session_state.chat_sessions.insert(0, new_sess)
            st.session_state.active_session_id = new_id
            st.session_state.current_session_id = new_id
            st.toast("Đã tạo phiên làm việc mới!", icon="➕")
            st.rerun()

        st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)
        
        # Danh sách các phiên làm việc (Đổi tỷ lệ cột thành 78 : 22 để nút thùng rác không bị chèn ép)
        for sess in user_sessions:
            is_active = (sess["id"] == active_sess["id"])
            col_title, col_del = st.columns([0.78, 0.22], vertical_alignment="center")

            time_str = sess.get("created_at") or sess.get("last_updated") or "10:30"
            display_title = sess["title"]
            if len(display_title) > 14:
                display_title = display_title[:14] + "..."
            
            btn_label = f"{'' if is_active else '💬 '}{display_title} - {time_str}"

            with col_title:
                btn_type = "primary" if is_active else "secondary"
                if st.button(btn_label, key=f"sel_{sess['id']}", use_container_width=True, type=btn_type):
                    st.session_state.active_session_id = sess["id"]
                    st.session_state.current_session_id = sess["id"]
                    st.rerun()

            with col_del:
                with st.popover("🗑️", help="Xóa phiên này", use_container_width=True):
                    st.write("Xóa phiên này?")
                    if st.button("Xóa", key=f"del_{sess['id']}", type="primary", use_container_width=True):
                        st.session_state.chat_sessions = [s for s in st.session_state.chat_sessions if s["id"] != sess["id"]]
                        
                        rem = [s for s in st.session_state.chat_sessions if s.get("user") == current_user]
                        if rem:
                            st.session_state.active_session_id = rem[0]["id"]
                            st.session_state.current_session_id = rem[0]["id"]
                        else:
                            now_time = time.strftime("%H:%M")
                            blank_id = f"sess_{int(time.time()*1000)}"
                            blank_sess = {
                                "id": blank_id,
                                "user": current_user,
                                "title": "Cuộc trò chuyện mới",
                                "created_at": now_time,
                                "last_updated": now_time,
                                "messages": []
                            }
                            st.session_state.chat_sessions.append(blank_sess)
                            st.session_state.active_session_id = blank_id
                            st.session_state.current_session_id = blank_id

                        st.toast("Đã xóa phiên làm việc!", icon="🗑️")
                        st.rerun()

        st.markdown("---")
        
        # Nút Xóa toàn bộ lịch sử trò chuyện
        if st.button("🗑️ Xóa toàn bộ lịch sử trò chuyện", use_container_width=True, key="btn_clear_all"):
            st.session_state.chat_sessions = [s for s in st.session_state.chat_sessions if s.get("user") != current_user]
            now_time = time.strftime("%H:%M")
            blank_id = f"sess_{int(time.time()*1000)}"
            blank_sess = {
                "id": blank_id,
                "user": current_user,
                "title": "Cuộc trò chuyện mới",
                "created_at": now_time,
                "last_updated": now_time,
                "messages": [
                    {
                        "role": "assistant",
                        "content": f"Xin chào **{current_user}**! Tôi là **Trợ lý Pháp luật Việt Nam**. Bạn muốn tra cứu hay tư vấn vấn đề pháp lý nào?",
                        "sources": [],
                        "feedback": None
                    }
                ]
            }
            st.session_state.chat_sessions.append(blank_sess)
            st.session_state.active_session_id = blank_id
            st.session_state.current_session_id = blank_id
            st.toast("Đã xóa toàn bộ lịch sử!", icon="🗑️")
            st.rerun()

        st.markdown("---")
        
        # Nút Đăng xuất (Đặt class/key đặc biệt để tô màu đỏ)
        if st.button("Đăng xuất", use_container_width=True, key="btn_logout"):
            st.session_state.logged_in = False
            st.session_state.user = None
            st.session_state.role = None
            st.session_state.page = "login"
            st.toast("Đã đăng xuất tài khoản!")
            st.rerun()

    # ================= MAIN CHAT AREA =================
    st.title("⚖️ Trợ lý Pháp luật Việt Nam")
    st.markdown(
    "<p style='font-size: 1.3rem; color: #475569;'>Tra cứu văn bản pháp luật, Bộ luật Dân sự, Luật Lao động, Bộ luật Hình sự và tư vấn pháp lý thông minh với RAG AI.</p>",
    unsafe_allow_html=True
)

    # Render danh sách tin nhắn của session active
    messages = active_sess["messages"]
    for idx, msg in enumerate(messages):
        avatar = "⚖️" if msg["role"] == "assistant" else "👤"
        with st.chat_message(msg["role"], avatar=avatar):
            st.markdown(msg["content"])
            
            # Trích dẫn nguồn tham khảo
            if msg["role"] == "assistant" and msg.get("sources"):
                with st.expander("📚 Nguồn tham khảo văn bản pháp luật"):
                    for src in msg["sources"]:
                        st.markdown(f"- **{src['title']}** (Độ tương đồng: `{src['score']*100:.1f}%`)")
                        st.caption(f"Trích dẫn: \"{src['snippet']}\"")
            
            # Nút Thích / Không thích
            if msg["role"] == "assistant":
                col_fb1, col_fb2, _ = st.columns([0.1, 0.1, 0.8])
                current_fb = msg.get("feedback")

                with col_fb1:
                    like_type = "primary" if current_fb == "like" else "secondary"
                    like_label = "👍" if current_fb != "like" else "👍"
                    if st.button(like_label, key=f"like_{active_sess['id']}_{idx}", type=like_type, help="Hữu ích"):
                        msg["feedback"] = None if current_fb == "like" else "like"
                        if msg["feedback"] == "like":
                            st.toast("Cảm ơn bạn đã đánh giá hữu ích!", icon="👍")
                        else:
                            st.toast("Đã bỏ chọn đánh giá", icon="↩️")
                        st.rerun()

                with col_fb2:
                    dislike_type = "primary" if current_fb == "dislike" else "secondary"
                    dislike_label = "👎" if current_fb != "dislike" else "👎"
                    if st.button(dislike_label, key=f"dislike_{active_sess['id']}_{idx}", type=dislike_type, help="Chưa phù hợp"):
                        msg["feedback"] = None if current_fb == "dislike" else "dislike"
                        if msg["feedback"] == "dislike":
                            st.toast("Đã ghi nhận ý kiến để cải thiện RAG AI!", icon="👎")
                        else:
                            st.toast("Đã bỏ chọn đánh giá", icon="↩️")
                        st.rerun()

    # ================= GỢI Ý CÂU HỎI (CUỘN NGANG TỰ ĐỘNG) =================
    curr_suggestions = SUGGESTION_POOLS[st.session_state.suggestion_index % len(SUGGESTION_POOLS)]
    
    col_sugg_label, col_sugg_ref = st.columns([6, 1])
    with col_sugg_label:
        st.markdown("**Gợi ý câu hỏi pháp lý:**")
    with col_sugg_ref:
        if st.button("🔄 Làm mới", help="Tải danh sách gợi ý khác"):
            st.session_state.suggestion_index += 1
            st.toast("Đã làm mới danh sách gợi ý câu hỏi!", icon="🔄")
            st.rerun()

    # RENDER CÁC NÚT GỢI Ý TRÊN 1 HÀNG DẠNG CHIPS CUỘN NGANG
    sugg_cols = st.columns(len(curr_suggestions))
    for i, sugg_text in enumerate(curr_suggestions):
        with sugg_cols[i]:
            # XỬ LÝ KHI BẤM NÚT GỢI Ý: Gọi chung hàm process_user_query()
            if st.button(sugg_text, key=f"sugg_{i}_{st.session_state.suggestion_index}"):
                with st.spinner("🔍 Đang truy xuất cơ sở dữ liệu văn bản pháp luật và tổng hợp câu trả lời RAG..."):
                    process_user_query(sugg_text, active_sess)
                st.rerun()

    # ================= KHU VỰC NHẬP CÂU HỎI (st.chat_input) =================
    st.markdown("<div style='margin-top: -0.8rem;'></div>", unsafe_allow_html=True)
    
    # XỬ LÝ KHI NHẬP VÀO Ô CHAT INPUT: Cũng gọi chung hàm process_user_query()
    if prompt := st.chat_input("Nhập câu hỏi pháp lý của bạn... (vd: Thời gian thử việc tối đa Luật Lao động 2019 là bao lâu?)"):
        with st.spinner("🔍 Đang truy xuất cơ sở dữ liệu văn bản pháp luật và tổng hợp câu trả lời RAG..."):
            process_user_query(prompt, active_sess)
        st.rerun()