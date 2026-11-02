from pathlib import Path


def test_postgres_migrations_have_ordered_bootstrap_files() -> None:
    """Verify Compose can apply the migration chain in deterministic order."""
    migration_dir = Path(__file__).parents[1] / "infra" / "docker" / "migrations"
    migrations = sorted(path.name for path in migration_dir.glob("*.sql"))
    assert migrations == [
        "000_init.sql",
        "001_ingestion.sql",
        "002_chunks.sql",
        "003_assets.sql",
        "004_audit_events.sql",
        "005_tenant_memberships.sql",
    ]