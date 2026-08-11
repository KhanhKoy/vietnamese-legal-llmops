import re

import streamlit as st

from src.storage import create_user, get_user_by_username, list_users


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
    col1, col2, col3 = st.columns([1, 2, 1])

    with col2:
        st.markdown("<h1 style='text-align: center; color: #1E88E5;'>⚖️ Trợ lý Pháp luật Việt Nam</h1>", unsafe_allow_html=True)
        st.markdown("<h3 style='text-align: center;'>Đăng Ký Tài Khoản Mới</h3>", unsafe_allow_html=True)
        st.write("---")

        username = st.text_input("Tên đăng nhập (Username)", placeholder="Nhập ít nhất 3 ký tự, không chứa khoảng trắng")
        email = st.text_input("Địa chỉ Email", placeholder="example@domain.com")
        password = st.text_input("Mật khẩu", type="password", placeholder="Tối thiểu 6 ký tự, gồm ít nhất 1 chữ hoa & 1 số")
        confirm_password = st.text_input("Xác nhận mật khẩu", type="password", placeholder="Nhập lại mật khẩu")

        if st.button("Đăng ký ngay", use_container_width=True, type="primary"):
            u_clean = username.strip()
            e_clean = email.strip()

            if not u_clean or not e_clean or not password or not confirm_password:
                st.error("Vui lòng điền đầy đủ tất cả thông tin!")
            elif len(u_clean) < 3 or " " in u_clean:
                st.error("Username phải từ 3 ký tự trở lên và không chứa khoảng trắng!")
            elif get_user_by_username(u_clean) is not None:
                st.error("Tên đăng nhập đã tồn tại trong hệ thống!")
            elif not validate_email(e_clean):
                st.error("Email không hợp lệ (phải chứa ký tự @ và tên miền hợp lệ)!")
            elif not validate_password(password):
                st.error("Mật khẩu phải từ 6 ký tự trở lên, chứa ít nhất 1 chữ hoa (A-Z) và 1 chữ số (0-9)!")
            elif password != confirm_password:
                st.error("Mật khẩu xác nhận không trùng khớp!")
            else:
                create_user(u_clean, e_clean, password, role="user")
                st.session_state.users = {user["username"]: user for user in list_users()}
                st.session_state.page = "login"
                st.toast("🎉 Đăng ký tài khoản thành công! Đang chuyển hướng...", icon="✨")
                st.rerun()

        st.markdown("<br>", unsafe_allow_html=True)
        st.write("Đã có tài khoản?")
        if st.button("Quay lại Đăng nhập", use_container_width=True):
            st.session_state.page = "login"
            st.rerun()

