import os

# Choose sqlite or postgres implementation based on DATABASE_URL env var
if os.environ.get("DATABASE_URL"):
    from .postgres_store import (
        delete_chat_session,
    )
    # Other Postgres-backed functions can be imported here as implemented
    # Fallback to sqlite for any missing functions
    from .sqlite_store import (
        initialize_database,
        hash_password,
        verify_password,
        authenticate_user,
        get_user_by_username,
        list_users,
        create_user,
        update_user_status,
        create_chat_session,
        list_chat_sessions,
        get_chat_session,
        append_message,
        update_chat_session_title,
        set_feedback,
        get_admin_stats,
        get_recent_activity,
    )
else:
    from .sqlite_store import (
        initialize_database,
        hash_password,
        verify_password,
        authenticate_user,
        get_user_by_username,
        list_users,
        create_user,
        update_user_status,
        create_chat_session,
        list_chat_sessions,
        get_chat_session,
        delete_chat_session,
        append_message,
        update_chat_session_title,
        set_feedback,
        get_admin_stats,
        get_recent_activity,
    )
