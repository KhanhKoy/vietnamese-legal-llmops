import streamlit as st

# TODO: thay bằng database thật

def show():
    # Tỷ lệ 1 : 2.5 : 1 giúp Form ở giữa mở rộng vừa vặn màn hình PC
    col1, col2, col3 = st.columns([1, 2.5, 1])
    
    with col2:
        st.markdown("<h1 style='text-align: center; color: #1E88E5; font-size: 2.4rem; font-weight: 800; margin-bottom: 0px;'>⚖️ Trợ lý Pháp luật Việt Nam</h1>", unsafe_allow_html=True)
        st.markdown("<h3 style='text-align: center; color: #475569; font-size: 1.35rem; font-weight: 600; margin-top: 6px;'>Đăng Nhập Hệ Thống</h3>", unsafe_allow_html=True)
        st.write("")
        
        # BỌC CÁC Ô NHẬP LIỆU VÀ NÚT ĐĂNG NHẬP VÀO ST.FORM
        with st.form("login_form", clear_on_submit=False):
            username = st.text_input("Tên đăng nhập (Username)", placeholder="Nhập username (vd: user1 hoặc admin)")
            password = st.text_input("Mật khẩu (Password)", type="password", placeholder="Nhập mật khẩu (vd: password123 hoặc admin123)")
            
            st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)
            # Thay st.button bằng st.form_submit_button
            submit_login = st.form_submit_button("Đăng nhập", use_container_width=True, type="primary")

        # XỬ LÝ LOGIC KHI BẤM NÚT HOẶC NHẤN ENTER
        if submit_login:
            # Validation form 4.2
            if not username.strip() or not password:
                st.error("Vui lòng nhập đầy đủ tên đăng nhập và mật khẩu!")
            else:
                users = st.session_state.users
                target_u = username.strip()
                if target_u in users and users[target_u]["password"] == password:
                    if users[target_u].get("status") == "Inactive" or users[target_u].get("is_deleted"):
                        st.error("Tài khoản này đã bị vô hiệu hóa! Vui lòng liên hệ Admin.")
                    else:
                        st.session_state.logged_in = True
                        st.session_state.user = target_u
                        st.session_state.role = users[target_u]["role"]
                        st.toast("🎉 Đăng nhập thành công!", icon="✅")
                        st.rerun()
                else:
                    st.error("Sai tên đăng nhập hoặc mật khẩu!")
                
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("<p style='font-size: 1.15rem; font-weight: 600; color: #0F172A; margin-bottom: 8px;'>Chưa có tài khoản?</p>", unsafe_allow_html=True)
        if st.button("Đăng ký tài khoản", use_container_width=True):
            st.session_state.page = "register"
            st.rerun()
            
        st.write("")
        st.info("💡 **Tài khoản dùng thử mẫu:**\n- User: `user1` / `password123`\n- Admin: `admin` / `admin123`", icon="ℹ️")