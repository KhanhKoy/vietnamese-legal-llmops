import os
import time
import psycopg
from dotenv import load_dotenv

load_dotenv()

# Lấy cấu hình kết nối từ .env
PGHOST = os.getenv("PGHOST")
PGDATABASE = os.getenv("PGDATABASE", "postgres")
PGUSER = os.getenv("PGUSER", "postgres")
PGPASSWORD = os.getenv("PGPASSWORD")
PGPORT = os.getenv("PGPORT", "5432")

conn_info = f"host={PGHOST} port={PGPORT} dbname={PGDATABASE} user={PGUSER} password={PGPASSWORD}"

print("🚀 Đang kết nối tới AWS RDS...")
start_time = time.time()

try:
    # Kết nối với chế độ autocommit=True để không bị treo transaction
    with psycopg.connect(conn_info, autocommit=True) as conn:
        with conn.cursor() as cur:
            print("⚙️ Cấu hình thông số tránh tràn RAM & tắt timeout...")
            cur.execute("SET statement_timeout = 0;")
            cur.execute("SET max_parallel_maintenance_workers = 0;")
            cur.execute("SET maintenance_work_mem = '256MB';")
            
            print("⌛ Đang tạo HNSW Index cho 456k vectors... (Python sẽ kiên nhẫn chờ, không bị ngắt giữa chừng)")
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_legal_chunks_embedding 
                ON legal_chunks 
                USING hnsw (embedding vector_cosine_ops);
            """)
            
            elapsed = time.time() - start_time
            print(f"🎉 HOÀN THÀNH TẠO HNSW INDEX THÀNH CÔNG sau {elapsed/60:.2f} phút!")

except Exception as e:
    print(f"❌ Lỗi: {e}")