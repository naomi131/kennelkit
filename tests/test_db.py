"""Tests for kennelkit.db.core."""

import pytest

from kennelkit import db
from kennelkit.db import ModuleSetting, ModuleState


@pytest.fixture(autouse=True)
def reset_db_state():
    """Reset DB module state between tests so configure() always starts fresh."""
    yield
    # Best-effort cleanup; ignore errors in case it wasn't configured
    try:
        import asyncio
        asyncio.get_event_loop().run_until_complete(db.shutdown())
    except Exception:
        pass


class TestConfigure:
    def test_get_engine_before_configure_raises(self):
        with pytest.raises(RuntimeError, match="not configured"):
            db.get_engine()

    def test_session_before_configure_raises(self):
        with pytest.raises(RuntimeError, match="not configured"):
            db.session()

    def test_invalid_url_protocol_raises(self):
        with pytest.raises(ValueError, match="only supports Postgres"):
            db.configure("sqlite:///foo.db")

    def test_mysql_url_raises(self):
        with pytest.raises(ValueError, match="only supports Postgres"):
            db.configure("mysql://user:pass@host/db")

    def test_valid_postgres_url(self):
        # We're not actually connecting, just creating the engine
        db.configure("postgresql+asyncpg://user:pass@localhost/test")
        engine = db.get_engine()
        assert engine is not None

    def test_postgres_without_driver_accepted(self):
        """`postgresql://` URLs are auto-upgraded to use asyncpg."""
        db.configure("postgresql://user:pass@localhost/test")
        engine = db.get_engine()
        # The engine's URL should have been rewritten
        assert "asyncpg" in str(engine.url)


class TestModels:
    def test_module_state_table_name(self):
        assert ModuleState.__tablename__ == "kennelkit_module_states"

    def test_module_setting_table_name(self):
        assert ModuleSetting.__tablename__ == "kennelkit_module_settings"

    def test_models_share_base_metadata(self):
        from kennelkit.db import Base
        # Both tables should be in Base's metadata
        table_names = set(Base.metadata.tables.keys())
        assert "kennelkit_module_states" in table_names
        assert "kennelkit_module_settings" in table_names