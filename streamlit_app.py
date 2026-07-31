import streamlit as st
import os

# Hàm nạp file CSS
def load_css(file_path):
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

# Tải cấu hình trang
st.set_page_config(page_title="Trợ lý Pháp luật Việt Nam", page_icon="⚖️", layout="wide")

# Nạp file style.css vừa tạo
load_css("assets/style.css")

# Cấu hình trang Streamlit
st.set_page_config(
    page_title="Trợ lý Pháp luật Việt Nam",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Load Custom CSS
def load_css():
    try:
        with open("assets/style.css", "r", encoding="utf-8") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    except Exception:
        pass

load_css()

# TODO: thay bằng database thật (PostgreSQL / Firestore)
# Khởi tạo Mock Database trong session_state nếu chưa có
if "users" not in st.session_state:
    st.session_state.users = {
        "user1": {"password": "password123", "email": "user1@phapluat.vn", "role": "user", "created_at": "2026-01-10", "status": "Active", "is_deleted": False, "deleted_at": None},
        "admin": {"password": "admin123", "email": "admin@phapluat.vn", "role": "admin", "created_at": "2026-01-01", "status": "Active", "is_deleted": False, "deleted_at": None},
        "minh_tran": {"password": "password123", "email": "minh.tran@lawfirm.vn", "role": "user", "created_at": "2026-03-15", "status": "Active", "is_deleted": False, "deleted_at": None},
        "hoang_nam": {"password": "password123", "email": "nam.hoang@company.com", "role": "user", "created_at": "2026-05-20", "status": "Active", "is_deleted": False, "deleted_at": None},
        "lan_anh": {"password": "password123", "email": "lananh.legal@gmail.com", "role": "user", "created_at": "2026-06-01", "status": "Active", "is_deleted": False, "deleted_at": None}
    }

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user = None
    st.session_state.role = None

if "page" not in st.session_state:
    st.session_state.page = "login"

# Lịch sử hội thoại theo phiên (Sessions)
if "chat_sessions" not in st.session_state:
    st.session_state.chat_sessions = [
        {
            "id": "sess_1",
            "user": "user1",
            "title": "Thời gian thử việc Luật Lao động 2019",
            "timestamp": "10:30 - Hôm nay",
            "messages": [
                {
                    "role": "assistant",
                    "content": "Xin chào! Tôi là **Trợ lý Pháp luật Việt Nam**. Tôi có thể hỗ trợ bạn tra cứu Bộ luật Dân sự, Luật Lao động, Bộ luật Hình sự, Luật Doanh nghiệp và nhiều văn bản pháp luật khác. Bạn muốn đặt câu hỏi gì hôm nay?",
                    "sources": [
                        {"title": "Điều 1, Bộ luật Dân sự 2015", "snippet": "Bộ luật này quy định địa vị pháp lý, chuẩn mực pháp lý cho cách ứng xử của cá nhân, pháp nhân...", "score": 0.95}
                    ],
                    "feedback": None
                }
            ]
        },
        {
            "id": "sess_2",
            "user": "user1",
            "title": "Thủ tục thành lập công ty TNHH 1 thành viên",
            "timestamp": "09:15 - Hôm qua",
            "messages": [
                {
                    "role": "assistant",
                    "content": "Chào bạn! Hồ sơ thành lập công ty TNHH 1 thành viên gồm Giấy đề nghị đăng ký doanh nghiệp, Điều lệ công ty và bản sao CCCD chủ sở hữu.",
                    "sources": [
                        {"title": "Điều 24, Luật Doanh nghiệp 2020", "snippet": "Hồ sơ đăng ký doanh nghiệp công ty TNHH 1 thành viên...", "score": 0.94}
                    ],
                    "feedback": "like"
                }
            ]
        }
    ]

if "active_session_id" not in st.session_state:
    st.session_state.active_session_id = "sess_1"

# Suggestion pools
if "suggestion_index" not in st.session_state:
    st.session_state.suggestion_index = 0

# Settings Defaults
if "settings" not in st.session_state:
    st.session_state.settings = {
        "top_k": 5,
        "temperature": 0.2,
        "max_tokens": 1024,
        "model": "gemini-2.5-flash (Nhanh & Tối ưu chi phí)"
    }

# Điều hướng trang
def main():
    if not st.session_state.logged_in:
        if st.session_state.page == "register":
            import views.register as register_page
            register_page.show()
        else:
            import views.login as login_page
            login_page.show()
    else:
        if st.session_state.role == "admin":
            import views.admin as admin_page
            admin_page.show()
        else:
            import views.chatbot as chatbot_page
            chatbot_page.show()

if __name__ == "__main__":
    main()

