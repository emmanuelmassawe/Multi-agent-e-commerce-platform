"""Schema metadata invariants for tenant isolation."""

from pathlib import Path

from clos.adapters.db.models import TENANT_TABLE_NAMES, Base


def test_every_tenant_owned_table_has_tenant_id_and_rls_migration() -> None:
    expected_tables = set(Base.metadata.tables) - {"tenants"}
    assert set(TENANT_TABLE_NAMES) == expected_tables
    assert all("tenant_id" in Base.metadata.tables[name].columns for name in expected_tables)
    migration = Path("migrations/versions/0001_phase1_core.py").read_text(encoding="utf-8")
    assert "ENABLE ROW LEVEL SECURITY" in migration
    assert "FORCE ROW LEVEL SECURITY" in migration
    assert "current_setting('app.current_tenant_id', true)" in migration
