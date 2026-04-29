"""Tests for kennelkit.dashboard.auth."""

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from kennelkit.dashboard import auth


@pytest.fixture(autouse=True)
def reset_ipc_client():
    """Reset the module-level IPC client between tests."""
    auth._ipc_client = None
    yield
    auth._ipc_client = None


class TestConfigureIPC:
    def test_get_ipc_before_configure_raises(self):
        with pytest.raises(RuntimeError, match="not configured"):
            auth._get_ipc()

    def test_configure_sets_client(self):
        client = MagicMock()
        auth.configure_ipc(client)
        assert auth._get_ipc() is client


class TestGuildCache:
    """
    The cache uses Quart's session, which we'd need a request context for.
    These tests use a dict to stand in for `session`.
    """

    @pytest.fixture
    def fake_session(self, monkeypatch):
        store: dict = {}
        monkeypatch.setattr(auth, "session", store)
        return store

    async def test_first_call_fetches_from_discord(self, fake_session):
        discord = MagicMock()
        guild = MagicMock()
        guild.id = 100
        guild.name = "Test Guild"
        guild.icon_url = "http://example.com/icon.png"
        guild.permissions.manage_guild = True
        discord.fetch_guilds = AsyncMock(return_value=[guild])

        result = await auth._get_user_guilds_cached(discord)

        assert len(result) == 1
        assert result[0]["id"] == 100
        assert result[0]["manage_guild"] is True
        discord.fetch_guilds.assert_awaited_once()

    async def test_second_call_within_ttl_uses_cache(self, fake_session):
        discord = MagicMock()
        discord.fetch_guilds = AsyncMock(return_value=[])

        await auth._get_user_guilds_cached(discord)
        await auth._get_user_guilds_cached(discord)

        # Discord was only called once
        assert discord.fetch_guilds.await_count == 1

    async def test_call_after_ttl_refetches(self, fake_session):
        discord = MagicMock()
        discord.fetch_guilds = AsyncMock(return_value=[])

        await auth._get_user_guilds_cached(discord)
        # Manually expire the cache
        fake_session["_kennelkit_user_guilds_at"] = time.time() - auth.GUILD_CACHE_TTL - 1
        await auth._get_user_guilds_cached(discord)

        assert discord.fetch_guilds.await_count == 2


class TestGetManageableGuilds:
    @pytest.fixture
    def fake_session(self, monkeypatch):
        store: dict = {}
        monkeypatch.setattr(auth, "session", store)
        return store

    async def test_bot_offline_returns_empty(self, fake_session):
        client = MagicMock()
        client.request = AsyncMock(return_value=None)
        auth.configure_ipc(client)

        discord = MagicMock()
        discord.fetch_guilds = AsyncMock(return_value=[])

        result = await auth.get_manageable_guilds(discord)

        assert result["bot_online"] is False
        assert result["with_bot"] == []
        assert result["without_bot"] == []

    async def test_splits_guilds_correctly(self, fake_session):
        client = MagicMock()
        client.request = AsyncMock(return_value=["100", "200"])  # bot in 100 and 200
        auth.configure_ipc(client)

        # User can manage 100, 200, and 300
        def make_guild(gid, manageable=True):
            g = MagicMock()
            g.id = gid
            g.name = f"Guild {gid}"
            g.icon_url = None
            g.permissions.manage_guild = manageable
            return g

        discord = MagicMock()
        discord.fetch_guilds = AsyncMock(return_value=[
            make_guild(100),
            make_guild(200),
            make_guild(300),
            make_guild(400, manageable=False),  # not manageable
        ])

        result = await auth.get_manageable_guilds(discord)

        assert result["bot_online"] is True
        assert len(result["with_bot"]) == 2          # 100, 200
        assert len(result["without_bot"]) == 1       # 300
        assert {g["id"] for g in result["with_bot"]} == {"100", "200"}
        assert {g["id"] for g in result["without_bot"]} == {"300"}


class TestVerifyGuildPerms:
    @pytest.fixture
    def fake_session(self, monkeypatch):
        store: dict = {}
        monkeypatch.setattr(auth, "session", store)
        return store

    async def test_unauthorized_returns_none(self, fake_session):
        discord = MagicMock()
        discord.authorized = AsyncMock(return_value=False)
        # `await discord.authorized` — make it awaitable
        discord.authorized = False  # quart_discord returns awaitable that resolves to bool

        # Quart-discord's `authorized` is a property returning awaitable.
        # For test simplicity, we make it directly awaitable.
        async def authorized_coro():
            return False

        type(discord).authorized = property(lambda self: authorized_coro())

        result = await auth.verify_guild_perms(discord, guild_id=100)
        assert result is None

    async def test_user_not_in_guild_returns_none(self, fake_session):
        client = MagicMock()
        auth.configure_ipc(client)

        async def authorized_coro():
            return True

        discord = MagicMock()
        type(discord).authorized = property(lambda self: authorized_coro())
        discord.fetch_guilds = AsyncMock(return_value=[])

        result = await auth.verify_guild_perms(discord, guild_id=100)
        assert result is None

    async def test_user_lacks_perms_returns_none(self, fake_session):
        client = MagicMock()
        auth.configure_ipc(client)

        async def authorized_coro():
            return True

        g = MagicMock()
        g.id = 100
        g.name = "x"
        g.icon_url = None
        g.permissions.manage_guild = False  # <-- no perm

        discord = MagicMock()
        type(discord).authorized = property(lambda self: authorized_coro())
        discord.fetch_guilds = AsyncMock(return_value=[g])

        result = await auth.verify_guild_perms(discord, guild_id=100)
        assert result is None

    async def test_bot_not_in_guild_returns_none(self, fake_session):
        client = MagicMock()
        client.request = AsyncMock(return_value=None)  # bot says: not in this guild
        auth.configure_ipc(client)

        async def authorized_coro():
            return True

        g = MagicMock()
        g.id = 100
        g.name = "x"
        g.icon_url = None
        g.permissions.manage_guild = True

        discord = MagicMock()
        type(discord).authorized = property(lambda self: authorized_coro())
        discord.fetch_guilds = AsyncMock(return_value=[g])

        result = await auth.verify_guild_perms(discord, guild_id=100)
        assert result is None

    async def test_all_checks_pass_returns_guild_info(self, fake_session):
        client = MagicMock()
        client.request = AsyncMock(return_value={"id": "100", "name": "x", "icon_url": None})
        auth.configure_ipc(client)

        async def authorized_coro():
            return True

        g = MagicMock()
        g.id = 100
        g.name = "x"
        g.icon_url = None
        g.permissions.manage_guild = True

        discord = MagicMock()
        type(discord).authorized = property(lambda self: authorized_coro())
        discord.fetch_guilds = AsyncMock(return_value=[g])

        result = await auth.verify_guild_perms(discord, guild_id=100)
        assert result is not None
        assert result["name"] == "x"