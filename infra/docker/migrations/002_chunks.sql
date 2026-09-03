CREATE TABLE IF NOT EXISTS document_chunks (
    chunk_id UUID PRIMARY KEY,
    document_id UUID NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL,
    content TEXT NOT NULL,
    modality VARCHAR(32) NOT NULL CHECK (modality IN ('text', 'table', 'image')),
    page_number INTEGER,
    region_id VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT document_chunks_page_positive CHECK (page_number IS NULL OR page_number > 0)
);

CREATE INDEX IF NOT EXISTS document_chunks_tenant_document_idx
    ON document_chunks (tenant_id, document_id);

CREATE INDEX IF NOT EXISTS document_chunks_document_page_idx
    ON document_chunks (document_id, page_number);
