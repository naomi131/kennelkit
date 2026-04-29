"""
Authorization helpers for kennelkit dashboard routes.

Two main exports:
  - get_manageable_guilds(discord)
      For the /guilds page. Returns user's manageable guilds split by
      whether the bot is in them or not.

  - verify_guild_perms(discord, guild_id)
      For per-guild routes (settings pages, etc). Confirms the user has
      Manage Server in the guild AND the bot is present. Returns the
      guild info dict, or None if any check fails.

Both internally cache the user's guild list in their session for 60s
to avoid Discord rate limits on /users/@me/guilds.
"""

from __future__ import annotations

import time
from typing import Any

from quart import session

from kennelkit.ipc import Client


GUILD_CACHE_TTL = 60  # seconds


# The IPC client is shared across requests. It's set once when
# create_dashboard() runs (so the dashboard knows the IPC secret/host/port).
_ipc_client: Client | None = None


def configure_ipc(client: Client) -> None:
    """Set the IPC client used by auth helpers. Called by create_dashboard()."""
    global _ipc_client
    _ipc_client = client


def _get_ipc() -> Client:
    if _ipc_client is None:
        raise RuntimeError(
            "kennelkit.dashboard.auth: IPC client not configured. "
            "Did you call create_dashboard()?"
        )
    return _ipc_client


async def _get_user_guilds_cached(discord) -> list[dict[str, Any]]:
    """
    Fetch user's guilds from Discord, with a session-scoped cache to avoid
    rate-limit issues from repeated /users/@me/guilds calls.
    """
    cached = session.get("_kennelkit_user_guilds")
    cached_at = session.get("_kennelkit_user_guilds_at", 0)

    if cached is not None and time.time() - cached_at < GUILD_CACHE_TTL:
        return cached

    fresh = await discord.fetch_guilds()
    session["_kennelkit_user_guilds"] = [
        {
            "id": g.id,
            "name": g.name,
            "icon_url": g.icon_url,
            "manage_guild": g.permissions.manage_guild,
        }
        for g in fresh
    ]
    session["_kennelkit_user_guilds_at"] = time.time()
    return session["_kennelkit_user_guilds"]


async def get_manageable_guilds(discord) -> dict:
    """
    Return user's guilds, split into:
      - 'with_bot':    bot is in this guild AND user has Manage Server (configurable)
      - 'without_bot': user has Manage Server but bot isn't there (invite target)
      - 'bot_online':  whether the bot's IPC is reachable

    If the bot is offline, both lists are empty and bot_online is False.
    """
    user_guilds = await _get_user_guilds_cached(discord)
    manageable = [g for g in user_guilds if g["manage_guild"]]

    bot_guild_ids = await _get_ipc().request("get_bot_guild_ids")
    if bot_guild_ids is None:
        return {"with_bot": [], "without_bot": [], "bot_online": False}

    bot_guild_ids = set(bot_guild_ids)
    with_bot = []
    without_bot = []
    for g in manageable:
        entry = {
            "id": str(g["id"]),
            "name": g["name"],
            "icon_url": g["icon_url"],
        }
        if str(g["id"]) in bot_guild_ids:
            with_bot.append(entry)
        else:
            without_bot.append(entry)

    return {"with_bot": with_bot, "without_bot": without_bot, "bot_online": True}


async def verify_guild_perms(discord, guild_id: int) -> dict | None:
    """
    Verify the logged-in user can manage this guild AND the bot is in it.

    Returns:
        guild info dict (id, name, icon_url) on success
        None if user lacks perms, bot is offline, or bot isn't in this guild
    """
    if not await discord.authorized:
        return None

    user_guilds = await _get_user_guilds_cached(discord)
    target = next((g for g in user_guilds if g["id"] == guild_id), None)
    if target is None or not target["manage_guild"]:
        return None

    guild_info = await _get_ipc().request("get_guild_info", guild_id=guild_id)
    if guild_info is None:
        return None

    return guild_info