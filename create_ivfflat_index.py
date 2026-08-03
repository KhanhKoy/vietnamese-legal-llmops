import os
import time

import psycopg
from dotenv import load_dotenv

load_dotenv()

PGHOST = os.getenv("PGHOST")
PGDATABASE = os.getenv("PGDATABASE", "postgres")
PGUSER = os.getenv("PGUSER", "postgres")
PGPASSWORD = os.getenv("PGPASSWORD")
PGPORT = os.getenv("PGPORT", "5432")

conn_info = f"host={PGHOST} port={PGPORT} dbname={PGDATABASE} user={PGUSER} password={PGPASSWORD}"

print("🚀 Đang kết nối AWS RDS để tạo IVFFlat Index...")
start_time = time.time()

with psycopg.connect(conn_info, autocommit=True) as conn:
    with conn.cursor() as cur:
        print("⚙️ Đang nâng maintenance_work_mem lên 512MB...")
        # 1. Tắt timeout ngắt giữa chừng
        cur.execute("SET statement_timeout = 0;")
        
        # 2. CẤP ĐỦ RAM CHO IVFFLAT (Cần 229MB -> Cấp hẳn 512MB cho thoải mái)
        cur.execute("SET maintenance_work_mem = '512MB';")
        
        print("⚡ Đang khởi tạo IVFFlat Index...")
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_legal_chunks_embedding 
            ON legal_chunks 
            USING ivfflat (embedding vector_cosine_ops) 
            WITH (lists = 675);
        """)
        
        elapsed = time.time() - start_time
        print(f"🎉 TẠO INDEX THÀNH CÔNG! Tổng thời gian: {elapsed:.2f} giây.")