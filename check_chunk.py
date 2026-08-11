import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

conn = psycopg2.connect(
    host=os.getenv('PGHOST'),
    port=os.getenv('PGPORT'),
    dbname=os.getenv('PGDATABASE'),
    user=os.getenv('PGUSER'),
    password=os.getenv('PGPASSWORD')
)
cur = conn.cursor()

# Tìm các chunk chứa cụm từ "phạt tiền từ"
cur.execute("SELECT text FROM legal_chunks WHERE text ILIKE '%phạt tiền từ%' LIMIT 3;")
rows = cur.fetchall()
for idx, row in enumerate(rows):
    print(f"\n--- CHUNK {idx+1} ---")
    print(row[0])
    print("---")
conn.close()