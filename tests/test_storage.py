"""Tests for kennelkit.storage. Requires Postgres."""

import os

import pytest
import pytest_asyncio
from sqlalchemy import text

from kennelkit import db
from kennelkit.fields import ChannelField, FieldError, IntField, TextField
from kennelkit.modules import Module, registry
from kennelkit.storage import (
    is_enabled,
    load_settings,
    save_setting,
    save_settings,
    set_enabled,
)


# Skip these tests if no test DB is configured. Avoids breaking CI for users
# who only want to run unit tests.
TEST_DB_URL = os.environ.get("KENNELKIT_TEST_DB_URL")
pytestmark = pytest.mark.skipif(
    TEST_DB_URL is None,
    reason="KENNELKIT_TEST_DB_URL not set; skipping integration tests.",
)


@pytest_asyncio.fixture(autouse=True)
async def configure_db():
    """Configure the test DB and create tables before each test."""
    db.configure(TEST_DB_URL)
    engine = db.get_engine()

    async with engine.begin() as conn:
        await conn.run_sync(db.Base.metadata.create_all)

    yield

    # Wipe rows between tests
    async with db.session() as s:
        await s.execute(text("DELETE FROM kennelkit_module_settings"))
        await s.execute(text("DELETE FROM kennelkit_module_states"))
        await s.commit()

    await db.shutdown()


@pytest.fixture(autouse=True)
def clean_registry():
    registry._clear()
    yield
    registry._clear()


def make_module():
    """Helper: define a fresh Module class for each test."""
    class TestMod(Module):
        id = "test"
        name = "Test"
        description = "A test module"

        class Settings:
            channel = ChannelField(label="Channel", required=True)
            count = IntField(label="Count", default=5)
            message = TextField(label="Message")

    return TestMod


# ---------- load_settings ----------


class TestLoadSettings:
    async def test_empty_returns_defaults(self):
        Mod = make_module()
        s = await load_settings(Mod.id, Mod.__schema__, guild_id=1)
        assert s.channel is None     # required, no default
        assert s.count == 5          # has default
        assert s.message is None     # optional, no default

    async def test_returns_saved_values(self):
        Mod = make_module()
        await save_setting(Mod.id, Mod.__schema__, 1, "channel", 999)
        await save_setting(Mod.id, Mod.__schema__, 1, "count", 42)

        s = await load_settings(Mod.id, Mod.__schema__, guild_id=1)
        assert s.channel == 999
        assert s.count == 42
        assert s.message is None

    async def test_isolated_per_guild(self):
        Mod = make_module()
        await save_setting(Mod.id, Mod.__schema__, 1, "count", 100)
        await save_setting(Mod.id, Mod.__schema__, 2, "count", 200)

        s1 = await load_settings(Mod.id, Mod.__schema__, guild_id=1)
        s2 = await load_settings(Mod.id, Mod.__schema__, guild_id=2)
        assert s1.count == 100
        assert s2.count == 200


# ---------- save_setting / save_settings ----------


class TestSaveSetting:
    async def test_save_and_load_roundtrip(self):
        Mod = make_module()
        await save_setting(Mod.id, Mod.__schema__, 1, "count", 42)
        s = await load_settings(Mod.id, Mod.__schema__, 1)
        assert s.count == 42

    async def test_save_updates_existing(self):
        Mod = make_module()
        await save_setting(Mod.id, Mod.__schema__, 1, "count", 1)
        await save_setting(Mod.id, Mod.__schema__, 1, "count", 2)
        s = await load_settings(Mod.id, Mod.__schema__, 1)
        assert s.count == 2

    async def test_save_unknown_key_raises(self):
        Mod = make_module()
        with pytest.raises(FieldError, match="Unknown setting"):
            await save_setting(Mod.id, Mod.__schema__, 1, "bogus", 1)

    async def test_save_invalid_value_raises(self):
        Mod = make_module()
        with pytest.raises(FieldError):
            # IntField with invalid type
            await save_setting(Mod.id, Mod.__schema__, 1, "count", "not a number")


class TestSaveSettings:
    async def test_save_multiple(self):
        Mod = make_module()
        await save_settings(Mod.id, Mod.__schema__, 1, {
            "channel": 100,
            "count": 7,
        })
        s = await load_settings(Mod.id, Mod.__schema__, 1)
        assert s.channel == 100
        assert s.count == 7

    async def test_atomic_on_validation_error(self):
        """If one value is invalid, none should be saved."""
        Mod = make_module()
        with pytest.raises(FieldError):
            await save_settings(Mod.id, Mod.__schema__, 1, {
                "count": 7,
                "channel": "not an int",  # invalid
            })

        # Verify nothing was saved
        s = await load_settings(Mod.id, Mod.__schema__, 1)
        assert s.count == 5  # default, not 7
        assert s.channel is None


# ---------- is_enabled ----------


class TestIsEnabled:
    async def test_default_is_disabled(self):
        Mod = make_module()
        assert await is_enabled(Mod.id, Mod.__schema__, 1) is False

    async def test_toggle_off_is_disabled(self):
        Mod = make_module()
        await set_enabled(Mod.id, 1, False)
        assert await is_enabled(Mod.id, Mod.__schema__, 1) is False

    async def test_toggle_on_but_required_missing_is_disabled(self):
        Mod = make_module()
        await set_enabled(Mod.id, 1, True)
        # `channel` is required and not set
        assert await is_enabled(Mod.id, Mod.__schema__, 1) is False

    async def test_toggle_on_and_required_set_is_enabled(self):
        Mod = make_module()
        await set_enabled(Mod.id, 1, True)
        await save_setting(Mod.id, Mod.__schema__, 1, "channel", 999)
        assert await is_enabled(Mod.id, Mod.__schema__, 1) is True

    async def test_no_required_fields_just_needs_toggle(self):
        class NoRequired(Module):
            id = "nr"
            name = "NoRequired"
            description = "x"
            class Settings:
                count = IntField(label="Count", default=5)

        await set_enabled(NoRequired.id, 1, True)
        assert await is_enabled(NoRequired.id, NoRequired.__schema__, 1) is True


# ---------- Module classmethods ----------


class TestModuleClassmethods:
    async def test_settings_for_classmethod(self):
        Mod = make_module()
        s = await Mod.settings_for(1)
        assert s.count == 5

    async def test_set_enabled_classmethod(self):
        Mod = make_module()
        await Mod.set_enabled(1, True)
        await Mod.save_setting(1, "channel", 100)
        assert await Mod.is_enabled(1) is True