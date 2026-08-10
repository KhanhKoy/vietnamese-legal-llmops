import os

import streamlit as st

from src.storage import initialize_database, list_users
from src.rag_core.config_manager import initialize_config


def load_css(file_path: str) -> None:
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)


st.set_page_config(page_title="Trợ lý Pháp luật Việt Nam", page_icon="⚖️", layout="wide", initial_sidebar_state="expanded")
load_css("assets/style.css")

initialize_database()
initialize_config()

if "users" not in st.session_state:
    st.session_state.users = {user["username"]: user for user in list_users()}

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user = None
    st.session_state.role = None
    st.session_state.current_user_id = None

if "page" not in st.session_state:
    st.session_state.page = "login"

if "active_session_id" not in st.session_state:
    st.session_state.active_session_id = None

if "suggestion_index" not in st.session_state:
    st.session_state.suggestion_index = 0



def main() -> None:
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

