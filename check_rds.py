import os
from dotenv import load_dotenv
import psycopg2

# Load biến môi trường từ .env
load_dotenv()

# Lấy thông tin kết nối từ .env
host = os.getenv("PGHOST")
port = os.getenv("PGPORT")
dbname = os.getenv("PGDATABASE")
user = os.getenv("PGUSER")
password = os.getenv("PGPASSWORD")

print(f"🔍 Đang kết nối đến {host}:{port}/{dbname} với user {user}")

try:
    conn = psycopg2.connect(
        host=host,
        port=port,
        dbname=dbname,
        user=user,
        password=password,
        connect_timeout=5
    )
    conn.autocommit = True
    cur = conn.cursor()

    # 1. Tên database hiện tại
    cur.execute("SELECT current_database();")
    db_name = cur.fetchone()[0]
    print(f"\n📌 Tên database: {db_name}")

    # 2. Kiểm tra bảng system_config (cấu hình hệ thống)
    try:
        cur.execute("SELECT * FROM system_config WHERE id = 1;")
        row = cur.fetchone()
        if row:
            print("\n📊 Cấu hình hệ thống (system_config):")
            print(f"   ID: {row[0]}, top_k: {row[1]}, temperature: {row[2]}, max_tokens: {row[3]}, model_name: {row[4]}, updated_at: {row[5]}")
        else:
            print("⚠️ Không có dữ liệu trong system_config (hoặc bảng chưa tồn tại).")
    except Exception as e:
        print(f"⚠️ Lỗi truy vấn system_config: {e}")

    # 3. Đếm số chunk (bảng legal_chunks - nếu dùng pgvector)
    try:
        cur.execute("SELECT COUNT(*) FROM legal_chunks;")
        chunk_count = cur.fetchone()[0]
        print(f"\n📦 Số chunk trong legal_chunks: {chunk_count}")
    except Exception as e:
        print(f"⚠️ Không có bảng legal_chunks hoặc lỗi: {e}")

    # 4. Danh sách tất cả bảng trong database
    cur.execute("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public'
        ORDER BY table_name;
    """)
    tables = cur.fetchall()
    print("\n📋 Danh sách bảng:")
    for tbl in tables:
        print(f"   - {tbl[0]}")

    # 5. Thống kê nếu có các bảng app_*
    try:
        cur.execute("SELECT COUNT(*) FROM app_users;")
        user_count = cur.fetchone()[0]
        print(f"\n👤 Số user: {user_count}")
    except:
        pass

    try:
        cur.execute("SELECT COUNT(*) FROM app_chat_sessions;")
        session_count = cur.fetchone()[0]
        print(f"💬 Số chat sessions: {session_count}")
    except:
        pass

    try:
        cur.execute("SELECT COUNT(*) FROM app_feedback_events;")
        feedback_count = cur.fetchone()[0]
        print(f"👍 Số feedback events: {feedback_count}")
    except:
        pass

    cur.close()
    conn.close()
    print("\n✅ Kiểm tra hoàn tất.")

except Exception as e:
    print(f"❌ Lỗi kết nối: {e}")