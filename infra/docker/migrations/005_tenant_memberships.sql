CREATE TABLE IF NOT EXISTS tenant_memberships (
    tenant_id UUID NOT NULL,
    actor_id UUID NOT NULL,
    roles TEXT[] NOT NULL DEFAULT '{}',
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, actor_id)
);

CREATE INDEX IF NOT EXISTS tenant_memberships_actor_idx
    ON tenant_memberships (actor_id, active);
