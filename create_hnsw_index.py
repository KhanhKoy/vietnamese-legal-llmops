"""Create the pgvector HNSW index with explicit, configurable resources.

Run this during a maintenance window after the initial data load.  Defaults are
conservative; size them from the RDS instance's free memory and vCPU count.
"""

import os
import time

import psycopg
from dotenv import load_dotenv
from psycopg import sql

load_dotenv()

PGHOST = os.getenv("PGHOST")
PGDATABASE = os.getenv("PGDATABASE", "postgres")
PGUSER = os.getenv("PGUSER", "postgres")
PGPASSWORD = os.getenv("PGPASSWORD")
PGPORT = os.getenv("PGPORT", "5432")

INDEX_NAME = os.getenv("HNSW_INDEX_NAME", "idx_legal_chunks_embedding_hnsw")
MAINTENANCE_WORK_MEM = os.getenv("HNSW_MAINTENANCE_WORK_MEM", "1GB")
PARALLEL_WORKERS = int(os.getenv("HNSW_PARALLEL_WORKERS", "2"))
M = int(os.getenv("HNSW_M", "16"))
EF_CONSTRUCTION = int(os.getenv("HNSW_EF_CONSTRUCTION", "64"))
CONCURRENTLY = os.getenv("HNSW_CREATE_CONCURRENTLY", "0").lower() in (
    "1", "true", "yes", "y"
)

conn_info = (
    f"host={PGHOST} port={PGPORT} dbname={PGDATABASE} "
    f"user={PGUSER} password={PGPASSWORD} sslmode=require connect_timeout=10"
)


def main() -> None:
    print("🚀 Đang kết nối tới AWS RDS...")
    started_at = time.time()

    with psycopg.connect(conn_info, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT set_config('statement_timeout', '0', false)")
            cur.execute(
                "SELECT set_config('maintenance_work_mem', %s, false)",
                (MAINTENANCE_WORK_MEM,),
            )
            cur.execute(
                "SELECT set_config('max_parallel_maintenance_workers', %s, false)",
                (str(PARALLEL_WORKERS),),
            )

            cur.execute(
                """
                SELECT indexname, indexdef
                FROM pg_indexes
                WHERE schemaname = current_schema()
                  AND tablename = 'legal_chunks'
                ORDER BY indexname
                """
            )
            existing = cur.fetchall()
            for name, definition in existing:
                print(f"ℹ️ Index hiện có: {name} -> {definition}")

            cur.execute(
                """
                SELECT i.indisready, i.indisvalid
                FROM pg_index i
                JOIN pg_class c ON c.oid = i.indexrelid
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = current_schema() AND c.relname = %s
                """,
                (INDEX_NAME,),
            )
            existing_status = cur.fetchone()
            if existing_status and not all(existing_status):
                raise RuntimeError(
                    f"Index {INDEX_NAME} đang tồn tại nhưng invalid/unfinished. "
                    "Hãy DROP INDEX trong maintenance window rồi chạy lại."
                )
            if existing_status:
                print(f"✅ Index {INDEX_NAME} đã hợp lệ; không cần tạo lại.")
                return

            concurrent_sql = sql.SQL("CONCURRENTLY ") if CONCURRENTLY else sql.SQL("")
            query = sql.SQL(
                """
                CREATE INDEX {concurrently}IF NOT EXISTS {index_name}
                ON legal_chunks
                USING hnsw (embedding vector_cosine_ops)
                WITH (m = {m}, ef_construction = {ef_construction})
                """
            ).format(
                concurrently=concurrent_sql,
                index_name=sql.Identifier(INDEX_NAME),
                m=sql.Literal(M),
                ef_construction=sql.Literal(EF_CONSTRUCTION),
            )

            print(
                "⌛ Tạo HNSW index "
                f"(memory={MAINTENANCE_WORK_MEM}, workers={PARALLEL_WORKERS}, "
                f"concurrently={CONCURRENTLY})..."
            )
            cur.execute(query)

            cur.execute(
                """
                SELECT i.indisready, i.indisvalid, pg_size_pretty(pg_relation_size(c.oid))
                FROM pg_index i
                JOIN pg_class c ON c.oid = i.indexrelid
                WHERE c.relname = %s
                """,
                (INDEX_NAME,),
            )
            status = cur.fetchone()
            if not status or not status[0] or not status[1]:
                raise RuntimeError(f"Index tạo xong nhưng chưa ready/valid: {status}")
            print(f"✅ Index status (ready, valid, size): {status}")

    elapsed = time.time() - started_at
    print(f"🎉 Hoàn thành sau {elapsed / 60:.2f} phút")


if __name__ == "__main__":
    main()
