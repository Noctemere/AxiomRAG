CREATE TABLE IF NOT EXISTS documents (
    document_id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    filename VARCHAR(255) NOT NULL,
    content_type VARCHAR(255) NOT NULL,
    size_bytes BIGINT NOT NULL CHECK (size_bytes > 0),
    sha256 CHAR(64) NOT NULL,
    storage_key TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT documents_tenant_sha256_unique UNIQUE (tenant_id, sha256)
);

CREATE TABLE IF NOT EXISTS ingestion_jobs (
    job_id UUID PRIMARY KEY,
    document_id UUID NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL,
    status VARCHAR(32) NOT NULL CHECK (status IN ('queued', 'processing', 'completed', 'failed')),
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ingestion_jobs_tenant_status_idx
    ON ingestion_jobs (tenant_id, status);

CREATE INDEX IF NOT EXISTS ingestion_jobs_document_created_idx
    ON ingestion_jobs (document_id, created_at DESC);

CREATE OR REPLACE FUNCTION update_ingestion_job_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS ingestion_jobs_updated_at ON ingestion_jobs;
CREATE TRIGGER ingestion_jobs_updated_at
    BEFORE UPDATE ON ingestion_jobs
    FOR EACH ROW
    EXECUTE FUNCTION update_ingestion_job_updated_at();
