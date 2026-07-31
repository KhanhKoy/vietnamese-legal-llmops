import streamlit as st
import pandas as pd
import plotly.express as px
import re
from datetime import datetime

# TODO: thay bằng database thật
# TODO: tích hợp CloudWatch/X-Ray
# TODO: tích hợp RAG pipeline thật

def validate_email(email: str) -> bool:
    pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
    return bool(re.match(pattern, email.strip()))

def validate_password(pwd: str) -> bool:
    if len(pwd) < 6:
        return False
    has_upper = bool(re.search(r"[A-Z]", pwd))
    has_digit = bool(re.search(r"[0-9]", pwd))
    return has_upper and has_digit

def show():
    current_admin = st.session_state.user or "admin"

    # ================= SIDEBAR (ADMIN) =================
    with st.sidebar:
        st.markdown(f"### {current_admin}")
        st.caption("Bảng Quản Trị Hệ Thống")
        st.write("---")

        if st.button("💬 Mở Giao diện Chatbot", use_container_width=True):
            st.session_state.role = "user"
            st.rerun()

        st.markdown("---")
        if st.button("Đăng xuất", use_container_width=True, key="btn_logout"):
            st.session_state.logged_in = False
            st.session_state.user = None
            st.session_state.role = None
            st.session_state.page = "login"
            st.toast("Đã đăng xuất tài khoản admin!", icon="🚪")
            st.rerun()

    # Header chính
    st.title("Admin Dashboard")

    # 4 Tabs chính còn lại (đã loại bỏ "Phân Tích Tương Tác", "Trace & Giám Sát", và "Cảnh Báo")
    tab_titles = [
        "📊 Dashboard",
        "👥 Quản Lý Người Dùng",
        "📜 Logs & Lịch Sử",
        "⚙️ Cài Đặt Hệ Thống"
    ]
    tabs = st.tabs(tab_titles)
    
    # Gán biến rõ ràng để tránh xung đột chỉ số khi thêm/bớt tab trong tương lai
    tab_dashboard = tabs[0]
    tab_users = tabs[1]
    tab_logs = tabs[2]
    tab_settings = tabs[3]

    # ------------------ TAB: DASHBOARD ------------------
    with tab_dashboard:
        st.subheader("📊 Chỉ Số Tổng Quan (KPI Cards)")
        col_m1, col_m2, col_m3, col_m4, col_m5, col_m6 = st.columns(6)
        col_m1.metric("Tổng User", f"{len(st.session_state.users)}", "+12 tuần này")
        col_m2.metric("Tổng Câu Hỏi", "18,450", "+850 hôm nay")
        col_m3.metric("Tỷ Lệ Hài Lòng", "94.2%", "+1.5%")
        col_m4.metric("User Active Hôm Nay", "312", "+24%")
        col_m5.metric("Tổng Token", "4.2M", "+350K")
        col_m6.metric("Chi Phí Ước Tính", "$18.40", "+$1.20")

        st.markdown("---")
        col_chart1, col_chart2 = st.columns([3, 2])

        with col_chart1:
            st.markdown("##### Xu hướng lượt truy vấn theo ngày")
            df_trend = pd.DataFrame({
                "Ngày": pd.date_range(start="2026-07-20", periods=7).strftime("%d/%m"),
                "Số câu hỏi": [1120, 1340, 1450, 1600, 1520, 1890, 2100]
            })
            fig_line = px.line(df_trend, x="Ngày", y="Số câu hỏi", markers=True, color_discrete_sequence=["#1E88E5"])
            st.plotly_chart(fig_line, use_container_width=True)

        with col_chart2:
            st.markdown("##### Top Lĩnh vực pháp luật được tra cứu")
            df_pie = pd.DataFrame({
                "Lĩnh vực": ["Luật Lao động", "Bộ luật Dân sự", "Luật Doanh nghiệp", "Hình sự", "Đất đai"],
                "Tỷ lệ": [35, 28, 18, 11, 8]
            })
            # SỬA LỖI 1: Thay qualitative.Blues bằng sequential.Blues (đúng cú pháp Plotly)
            fig_pie = px.pie(df_pie, values="Tỷ lệ", names="Lĩnh vực", color_discrete_sequence=px.colors.sequential.Blues_r)
            st.plotly_chart(fig_pie, use_container_width=True)

        st.markdown("##### 10 Hoạt động tra cứu gần đây nhất")
        # TODO: thay bằng database thật
        recent_logs = pd.DataFrame([
            {"Mã Log": "LOG-1001", "User": "user1", "Thời gian": "00:14:10", "Câu hỏi": "Thời gian thử việc tối đa Luật Lao động?", "Đánh giá": "👍 Like"},
            {"Mã Log": "LOG-1002", "User": "minh_tran", "Thời gian": "00:12:05", "Câu hỏi": "Thành lập công ty TNHH 1 thành viên cần thủ tục gì?", "Đánh giá": "👍 Like"},
            {"Mã Log": "LOG-1003", "User": "hoang_nam", "Thời gian": "00:09:40", "Câu hỏi": "Mức phạt vi phạm nồng độ cồn xe máy?", "Đánh giá": "👍 Like"},
            {"Mã Log": "LOG-1004", "User": "lan_anh", "Thời gian": "00:05:12", "Câu hỏi": "Quyền thừa kế theo pháp luật gồm những ai?", "Đánh giá": "👎 Dislike"},
            {"Mã Log": "LOG-1005", "User": "user1", "Thời gian": "23:58:00", "Câu hỏi": "Đơn phương chấm dứt hợp đồng lao động báo trước mấy ngày?", "Đánh giá": "👍 Like"},
            {"Mã Log": "LOG-1006", "User": "minh_tran", "Thời gian": "23:50:15", "Câu hỏi": "Thủ tục sang tên sổ đỏ đất đai hộ gia đình?", "Đánh giá": "👍 Like"},
            {"Mã Log": "LOG-1007", "User": "hoang_nam", "Thời gian": "23:42:30", "Câu hỏi": "Lương tối thiểu vùng I năm 2026?", "Đánh giá": "👍 Like"},
            {"Mã Log": "LOG-1008", "User": "lan_anh", "Thời gian": "23:30:10", "Câu hỏi": "Mức vi phạm bản quyền phần mềm doanh nghiệp?", "Đánh giá": "👍 Like"},
            {"Mã Log": "LOG-1009", "User": "user1", "Thời gian": "23:15:00", "Câu hỏi": "Điều kiện tạm ngừng kinh doanh công ty cổ phần?", "Đánh giá": "👍 Like"},
            {"Mã Log": "LOG-1010", "User": "minh_tran", "Thời gian": "23:02:45", "Câu hỏi": "Hồ sơ quyết toán thuế TNDN cuối năm?", "Đánh giá": "👍 Like"},
        ])
        st.dataframe(recent_logs, use_container_width=True)

    # ------------------ TAB: QUẢN LÝ NGƯỜI DÙNG ------------------
    with tab_users:
        st.subheader("👥 Danh Sách Quản Lý Người Dùng")
        
        col_s1, col_s2, col_s3, col_s4 = st.columns([3, 2, 2, 2])
        search_kw = col_s1.text_input("🔍 Tìm kiếm username / email", placeholder="Nhập từ khóa...")
        role_filter = col_s2.selectbox("Lọc theo Vai trò", ["Tất cả", "user", "admin"])
        status_filter = col_s3.selectbox("Lọc theo Trạng thái", ["Tất cả", "Active", "Inactive"])
        
        with col_s4:
            st.markdown("<br>", unsafe_allow_html=True)
            with st.popover("➕ Thêm User Mới"):
                st.markdown("##### Form Thêm Người Dùng")
                new_u = st.text_input("Username mới", placeholder=">= 3 ký tự, không khoảng trắng")
                new_e = st.text_input("Email", placeholder="user@example.com")
                new_p = st.text_input("Mật khẩu", type="password", placeholder=">= 6 ký tự, 1 chữ hoa, 1 số")
                
                if st.button("Lưu Người Dùng Mới", type="primary"):
                    u_clean = new_u.strip()
                    e_clean = new_e.strip()
                    
                    if not u_clean or not e_clean or not new_p:
                        st.error("Vui lòng điền đầy đủ các trường thông tin!")
                    elif len(u_clean) < 3 or " " in u_clean:
                        st.error("Username phải ít nhất 3 ký tự và không chứa khoảng trắng!")
                    elif u_clean in st.session_state.users:
                        st.error("Username đã tồn tại trong hệ thống!")
                    elif not validate_email(e_clean):
                        st.error("Địa chỉ email không đúng định dạng hợp lệ!")
                    elif not validate_password(new_p):
                        st.error("Mật khẩu phải từ 6 ký tự trở lên, chứa ít nhất 1 chữ hoa và 1 số!")
                    else:
                        st.session_state.users[u_clean] = {
                            "password": new_p,
                            "email": e_clean,
                            "role": "user",
                            "created_at": "2026-07-27",
                            "status": "Active",
                            "is_deleted": False,
                            "deleted_at": None
                        }
                        st.toast(f"🎉 Đã thêm người dùng mới {u_clean} thành công!", icon="👤")
                        st.rerun()

        # Render Bảng Users
        users_list = []
        for u, data in st.session_state.users.items():
            u_role = data.get("role", "user")
            u_status = data.get("status", "Active")
            
            if role_filter != "Tất cả" and u_role != role_filter:
                continue
            if status_filter != "Tất cả" and u_status != status_filter:
                continue
            if search_kw and (search_kw.lower() not in u.lower() and search_kw.lower() not in data["email"].lower()):
                continue
            
            status_badge = "🟢 Active" if u_status == "Active" else "🔴 Inactive"
            deleted_time = data.get("deleted_at") if data.get("is_deleted") else "-"
            
            users_list.append({
                "Username": u,
                "Email": data.get("email", ""),
                "Role": u_role,
                "Trạng thái": status_badge,
                "Ngày tạo": data.get("created_at", "2026-01-01"),
                "Thời gian xóa": deleted_time
            })

        df_users = pd.DataFrame(users_list)
        st.dataframe(df_users, use_container_width=True)

        # Action Section per Selected User
        st.markdown("##### ⚙️ Thao tác người dùng:")
        col_act1, col_act2 = st.columns([3, 3])
        target_usr = col_act1.selectbox("Chọn User thao tác", [u for u in st.session_state.users.keys()])
        
        target_data = st.session_state.users.get(target_usr, {})
        is_inactive = target_data.get("status") == "Inactive" or target_data.get("is_deleted") == True
        
        with col_act2:
            if not is_inactive:
                with st.popover("🗑️ Xóa (Vô hiệu hóa)"):
                    st.write(f"Xác nhận vô hiệu hóa người dùng `{target_usr}`?")
                    if st.button("Xác nhận Xóa", type="primary"):
                        if target_usr == "admin":
                            st.error("Không thể vô hiệu hóa tài khoản admin hệ thống!")
                        else:
                            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            st.session_state.users[target_usr]["status"] = "Inactive"
                            st.session_state.users[target_usr]["is_deleted"] = True
                            st.session_state.users[target_usr]["deleted_at"] = now_str
                            st.toast("Đã vô hiệu hóa người dùng thành công!", icon="🔴")
                            st.rerun()
            else:
                if st.button("🟢 Khôi phục tài khoản", type="primary"):
                    st.session_state.users[target_usr]["status"] = "Active"
                    st.session_state.users[target_usr]["is_deleted"] = False
                    st.session_state.users[target_usr]["deleted_at"] = None
                    st.toast("Đã khôi phục người dùng thành công!", icon="🟢")
                    st.rerun()

        # Export CSV
        csv_data = df_users.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Xuất danh sách người dùng (CSV)", data=csv_data, file_name="users_list.csv", mime="text/csv")

    # ------------------ TAB: LOGS & LỊCH SỬ ------------------
    with tab_logs:
        st.subheader("📜 Nhật Ký & Lịch Sử Truy Vấn Chi Tiết")
        col_f1, col_f2 = st.columns(2)
        user_sel = col_f1.selectbox("Chọn User để tra cứu", ["Tất cả"] + list(st.session_state.users.keys()))
        date_sel = col_f2.date_input("Chọn ngày tra cứu", [])

        st.markdown("##### Bảng dữ liệu nhật ký cuộc hội thoại")
        mock_logs = pd.DataFrame([
            {"ID": "LOG-1001", "User": "user1", "Thời gian": "2026-07-27 00:10:00", "Câu hỏi": "Thời gian thử việc Luật Lao động?", "Answer Summary": "Thời gian thử việc tối đa 180 ngày đối với người quản lý, 60 ngày đối với trình độ chuyên môn...", "Feedback": "Like", "Latency": "1.12s"},
            {"ID": "LOG-1002", "User": "admin", "Thời gian": "2026-07-27 00:08:22", "Câu hỏi": "Thủ tục đăng ký hộ kinh doanh cá thể?", "Answer Summary": "Nộp hồ sơ tại UBND cấp huyện gồm Giấy đề nghị và bản sao CCCD...", "Feedback": "Like", "Latency": "0.95s"},
            {"ID": "LOG-1003", "User": "minh_tran", "Thời gian": "2026-07-26 23:45:10", "Câu hỏi": "Trách nhiệm bồi thường hợp đồng mua bán?", "Answer Summary": "Bồi thường thiệt hại thực tế phát sinh trực tiếp do vi phạm nghĩa vụ hợp đồng...", "Feedback": "Dislike", "Latency": "1.85s"},
        ])
        
        if user_sel != "Tất cả":
            mock_logs = mock_logs[mock_logs["User"] == user_sel]

        st.dataframe(mock_logs, use_container_width=True)

        with st.expander("🔍 Xem chi tiết log hội thoại & RAG Metadata (LOG-1001)"):
            st.json({
                "log_id": "LOG-1001",
                "user": "user1",
                "question": "Thời gian thử việc Luật Lao động?",
                "retrieved_documents": [
                    {"document": "Điều 25, Luật Lao động 2019", "score": 0.94},
                    {"document": "Nghị định 145/2020/NĐ-CP", "score": 0.88}
                ],
                "llm_prompt_tokens": 420,
                "llm_completion_tokens": 185,
                "latency_ms": 1120
            })

        csv_logs = mock_logs.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Xuất dữ liệu Logs (CSV)", data=csv_logs, file_name="logs_export.csv", mime="text/csv")

    # ------------------ TAB: CÀI ĐẶT HỆ THỐNG ------------------
    with tab_settings:
        st.subheader("⚙️ Cấu Hình Cài Đặt RAG Pipeline & LLM Model")
        
        cfg = st.session_state.settings

        col_cfg1, col_cfg2 = st.columns(2)
        with col_cfg1:
            st.markdown("##### 🎛️ Cấu hình Tham số RAG")
            top_k_val = st.number_input("Số đoạn văn bản lấy ra (top-k: 1..20)", min_value=1, max_value=20, value=int(cfg["top_k"]))
            temp_val = st.number_input("Độ sáng tạo (Temperature: 0.0..1.0)", min_value=0.0, max_value=1.0, value=float(cfg["temperature"]), step=0.05)
            max_tok_val = st.number_input("Max Tokens trả về (100..4096)", min_value=100, max_value=4096, value=int(cfg["max_tokens"]))
            
            # Model Selection Dropdown
            model_options = [
                "gemini-2.5-flash (Nhanh & Tối ưu chi phí)",
                "gemini-2.5-pro (Tư duy pháp lý chuyên sâu)",
                "gpt-4o-mini"
            ]
            
            # Tính toán index hiện tại trong session_state động
            current_model = cfg.get("model", model_options[0])
            model_index = model_options.index(current_model) if current_model in model_options else 0
            model_val = st.selectbox("LLM Model Engine", model_options, index=model_index)

            if st.button("💾 Lưu Cài Đặt Hệ Thống", type="primary"):
                # Form validation
                st.session_state.settings["top_k"] = min(max(1, top_k_val), 20)
                st.session_state.settings["temperature"] = min(max(0.0, temp_val), 1.0)
                st.session_state.settings["max_tokens"] = min(max(100, max_tok_val), 4096)
                st.session_state.settings["model"] = model_val
                st.toast("💾 Cấu hình cài đặt hệ thống đã được lưu thành công!", icon="✅")

        with col_cfg2:
            st.markdown("##### 📂 Trạng Thái Vector Database")
            st.write("- **Loại DB:** Qdrant / Milvus / Chroma")
            st.write("- **Tổng số Chunks:** `142,500` văn bản luật")
            st.write("- **Lần Sync gần nhất:** `2026-07-26 18:00`")
            
            if st.button("🚀 Sync Embeddings lên S3", use_container_width=True):
                st.toast("🚀 Đã phát lệnh đồng bộ Embeddings lên S3 thành công!", icon="🚀")