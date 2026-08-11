import psycopg2
from dotenv import load_dotenv
import os

load_dotenv()

conn = psycopg2.connect(
    host=os.getenv('PGHOST'),
    port=os.getenv('PGPORT'),
    database=os.getenv('PGDATABASE'),
    user=os.getenv('PGUSER'),
    password=os.getenv('PGPASSWORD')
)
cur = conn.cursor()

# Liệt kê tất cả cột của bảng legal_chunks
cur.execute("""
    SELECT column_name, data_type
    FROM information_schema.columns
    WHERE table_name = 'legal_chunks'
    ORDER BY ordinal_position;
""")
columns = cur.fetchall()
print("📋 Các cột trong bảng legal_chunks:")
for col_name, data_type in columns:
    print(f"  - {col_name} ({data_type})")

conn.close()