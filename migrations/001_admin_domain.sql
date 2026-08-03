BEGIN;

CREATE TABLE IF NOT EXISTS legal_documents (
    document_id TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    title TEXT NOT NULL DEFAULT '',
    so_ky_hieu TEXT NOT NULL DEFAULT '',
    loai_van_ban TEXT NOT NULL DEFAULT '',
    co_quan_ban_hanh TEXT NOT NULL DEFAULT '',
    ngay_ban_hanh TEXT NOT NULL DEFAULT '',
    ngay_co_hieu_luc TEXT NOT NULL DEFAULT '',
    ngay_het_hieu_luc TEXT NOT NULL DEFAULT '',
    tinh_trang_hieu_luc TEXT NOT NULL DEFAULT '',
    is_procedural_law BOOLEAN NOT NULL DEFAULT FALSE,
    source_s3_key TEXT NOT NULL DEFAULT '',
    content_hash TEXT NOT NULL DEFAULT '',
    processing_status TEXT NOT NULL DEFAULT 'INDEXED',
    created_by TEXT NOT NULL DEFAULT 'migration',
    updated_by TEXT NOT NULL DEFAULT 'migration',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ,
    PRIMARY KEY (document_id, version),
    CHECK (processing_status IN (
        'UPLOADED', 'QUEUED', 'EXTRACTING', 'CHUNKING',
        'EMBEDDING', 'INDEXED', 'FAILED', 'DELETED'
    ))
);

ALTER TABLE legal_documents
    ADD COLUMN IF NOT EXISTS is_procedural_law BOOLEAN NOT NULL DEFAULT FALSE;

-- Backfill one document record from the existing chunk metadata.  This keeps
-- the migration usable with the current 456k-row legal_chunks table.
INSERT INTO legal_documents (
    document_id, title, so_ky_hieu, loai_van_ban, co_quan_ban_hanh,
    ngay_ban_hanh, ngay_het_hieu_luc, tinh_trang_hieu_luc,
    is_procedural_law,
    source_s3_key, deleted_at
)
SELECT DISTINCT ON (document_id)
    document_id,
    COALESCE(metadata_json->>'title', ''),
    COALESCE(metadata_json->>'so_ky_hieu', ''),
    COALESCE(metadata_json->>'loai_van_ban', ''),
    COALESCE(metadata_json->>'co_quan_ban_hanh', ''),
    COALESCE(metadata_json->>'ngay_ban_hanh', ''),
    COALESCE(metadata_json->>'ngay_het_hieu_luc', ''),
    COALESCE(metadata_json->>'tinh_trang_hieu_luc', ''),
    LOWER(COALESCE(metadata_json->>'is_procedural_law', 'false'))
        IN ('1', 'true', 'yes', 'y'),
    COALESCE(metadata_json->>'s3_key', ''),
    CASE
        WHEN COALESCE(metadata_json->>'deleted_at', '')
            ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}[T ]'
        THEN NULLIF(metadata_json->>'deleted_at', '')::timestamptz
        ELSE NULL
    END
FROM legal_chunks
ORDER BY document_id, id
ON CONFLICT (document_id, version) DO NOTHING;

ALTER TABLE legal_chunks
    ADD COLUMN IF NOT EXISTS document_version INTEGER NOT NULL DEFAULT 1;

CREATE INDEX IF NOT EXISTS idx_legal_documents_status
    ON legal_documents (processing_status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_legal_documents_active
    ON legal_documents (updated_at DESC) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_legal_chunks_document_version
    ON legal_chunks (document_id, document_version);

CREATE TABLE IF NOT EXISTS ingestion_jobs (
    job_id UUID PRIMARY KEY,
    document_id TEXT NOT NULL,
    document_version INTEGER NOT NULL DEFAULT 1,
    s3_bucket TEXT NOT NULL,
    s3_key TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'QUEUED',
    attempts INTEGER NOT NULL DEFAULT 0,
    error_message TEXT NOT NULL DEFAULT '',
    created_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ingestion_jobs_status
    ON ingestion_jobs (status, updated_at DESC);

CREATE TABLE IF NOT EXISTS application_audit_log (
    audit_id BIGSERIAL PRIMARY KEY,
    actor_id TEXT NOT NULL,
    actor_role TEXT NOT NULL DEFAULT '',
    action TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    before_data JSONB,
    after_data JSONB,
    request_id TEXT NOT NULL DEFAULT '',
    source_ip INET,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_audit_resource
    ON application_audit_log (resource_type, resource_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_actor
    ON application_audit_log (actor_id, created_at DESC);

COMMIT;
