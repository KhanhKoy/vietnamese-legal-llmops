import psycopg2
from pgvector.psycopg2 import register_vector
import os
from dotenv import load_dotenv

load_dotenv()

try:
    conn = psycopg2.connect(
        host=os.getenv('PGHOST'),
        port=os.getenv('PGPORT'),
        database=os.getenv('PGDATABASE'),
        user=os.getenv('PGUSER'),
        password=os.getenv('PGPASSWORD')
    )
    register_vector(conn)
    cur = conn.cursor()

    # 1. Liệt kê tất cả các bảng trong schema public
    cur.execute("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public' 
        ORDER BY table_name;
    """)
    tables = cur.fetchall()
    print("📋 Các bảng có trong cơ sở dữ liệu:")
    if not tables:
        print("  (Không có bảng nào trong schema public)")
    for (table_name,) in tables:
        print(f"  - {table_name}")

    # 2. Với mỗi bảng, thử đếm số dòng và hiển thị cấu trúc
    for (table_name,) in tables:
        try:
            cur.execute(f"SELECT COUNT(*) FROM {table_name};")
            count = cur.fetchone()[0]
            print(f"  ✅ Bảng '{table_name}' có {count} dòng.")
            
            # Lấy 3 cột đầu tiên để xem kiểu dữ liệu
            cur.execute(f"""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = '{table_name}' 
                ORDER BY ordinal_position 
                LIMIT 5;
            """)
            cols = cur.fetchall()
            if cols:
                col_info = ", ".join([f"{c[0]} ({c[1]})" for c in cols])
                print(f"     Cột mẫu: {col_info}")
        except Exception as e:
            print(f"  ⚠️ Lỗi khi đếm bảng '{table_name}': {e}")

    conn.close()
except Exception as e:
    print(f"❌ Kết nối thất bại: {e}")