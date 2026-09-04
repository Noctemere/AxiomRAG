CREATE TABLE IF NOT EXISTS document_assets (
    asset_id UUID PRIMARY KEY,
    document_id UUID NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL,
    modality VARCHAR(32) NOT NULL CHECK (modality IN ('image', 'table')),
    storage_key TEXT NOT NULL,
    page_number INTEGER,
    region_id VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT document_assets_page_positive CHECK (page_number IS NULL OR page_number > 0)
);

CREATE INDEX IF NOT EXISTS document_assets_tenant_document_idx
    ON document_assets (tenant_id, document_id);

CREATE INDEX IF NOT EXISTS document_assets_document_page_idx
    ON document_assets (document_id, page_number);