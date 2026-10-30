CREATE TABLE IF NOT EXISTS audit_events (
    event_id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    actor_id UUID NOT NULL,
    tool_name VARCHAR(128) NOT NULL,
    action VARCHAR(255) NOT NULL,
    allowed BOOLEAN NOT NULL,
    reason TEXT,
    approval_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS audit_events_tenant_created_idx
    ON audit_events (tenant_id, created_at DESC);

CREATE INDEX IF NOT EXISTS audit_events_actor_created_idx
    ON audit_events (actor_id, created_at DESC);
