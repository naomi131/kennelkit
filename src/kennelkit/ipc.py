"""
IPC layer — communication between the bot process and the dashboard process.

The bot runs an IPC server on localhost. The dashboard talks to it for
real-time data (guild presence, channel lists) and live actions (sending
messages, performing moderation).

Modules can register their own routes via the @route decorator on cog methods.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from discord.ext import ipcx
from discord.ext.commands import Bot

log = logging.getLogger("kennelkit.ipc")


# ---------- Module-defined routes ----------

# Routes registered by modules via @route. Collected at import time; bound
# to the IPC server when Server.start() runs.
_pending_routes: dict[str, Callable] = {}


def route(name: str | None = None):
    """
    Decorator to mark a method as an IPC route.

    Usage in a cog:

        class TicketCog(KennelCog, module=TicketsModule):
            @kennelkit.ipc.route()
            async def open_ticket(self, data):
                ...

    The route is registered with the IPC server when the bot starts.
    Route names default to the method name; pass a name to override.
    """
    def decorator(fn: Callable) -> Callable:
        route_name = name or fn.__name__
        if route_name in _pending_routes:
            raise ValueError(
                f"Duplicate IPC route name: {route_name!r}. "
                f"Use a different name or rename the method."
            )
        # Mark the function; the bot's setup_hook will pick this up
        fn.__kennelkit_ipc_route__ = route_name  # type: ignore[attr-defined]
        _pending_routes[route_name] = fn
        return fn
    return decorator


def collect_routes_from_cog(cog) -> list[tuple[str, Callable]]:
    """Walk a cog instance and return any methods marked as IPC routes."""
    found = []
    for attr_name in dir(cog):
        if attr_name.startswith("_"):
            continue
        attr = getattr(cog, attr_name, None)
        if attr is None or not callable(attr):
            continue
        route_name = getattr(attr, "__kennelkit_ipc_route__", None)
        if route_name is not None:
            found.append((route_name, attr))
    return found


# ---------- Server ----------


class Server:
    """
    Wrapper around discord-ext-ipcx's Server with kennelkit's built-in routes
    pre-registered.

    The bot creates one of these and calls await server.start() in setup_hook.
    """

    def __init__(
        self,
        bot: Bot,
        *,
        host: str = "127.0.0.1",
        port: int = 8765,
        secret_key: str,
    ):
        self.bot = bot
        self._server = ipcx.Server(
            bot,
            host=host,
            port=port,
            secret_key=secret_key,
        )
        self._register_builtin_routes()

    def _register_builtin_routes(self) -> None:
        """Register the framework's standard IPC routes."""

        @self._server.route()
        async def get_bot_guild_ids(data):
            """Return guild IDs the bot is currently in (as strings)."""
            return [str(g.id) for g in self.bot.guilds]

        @self._server.route()
        async def get_guild_info(data):
            """Return basic info for one guild, or None if the bot isn't in it."""
            guild = self.bot.get_guild(int(data.guild_id))
            if guild is None:
                return None
            return {
                "id": str(guild.id),
                "name": guild.name,
                "icon_url": guild.icon.url if guild.icon else None,
            }

        @self._server.route()
        async def get_guild_channels(data):
            """Return text channels in a guild for settings dropdowns."""
            guild = self.bot.get_guild(int(data.guild_id))
            if guild is None:
                return None
            return [
                {"id": str(c.id), "name": c.name}
                for c in guild.text_channels
            ]

        @self._server.route()
        async def get_guild_roles(data):
            """Return roles in a guild for settings dropdowns."""
            guild = self.bot.get_guild(int(data.guild_id))
            if guild is None:
                return None
            return [
                {"id": str(r.id), "name": r.name}
                for r in guild.roles
                if r.name != "@everyone"
            ]

        @self._server.route()
        async def get_guild_categories(data):
            """Return channel categories in a guild for settings dropdowns."""
            guild = self.bot.get_guild(int(data.guild_id))
            if guild is None:
                return None
            return [
                {"id": str(c.id), "name": c.name}
                for c in guild.categories
            ]

    def register_module_routes(self) -> None:
        """
        Walk all cogs on the bot and register any methods decorated with @route.

        Called automatically by KennelBot.setup_hook after cogs are loaded.
        """
        for cog in self.bot.cogs.values():
            for route_name, method in collect_routes_from_cog(cog):
                # Skip if already registered (e.g., on a bot reload)
                if route_name in self._server.endpoints:
                    log.debug("IPC route %s already registered, skipping", route_name)
                    continue
                self._server.endpoints[route_name] = method
                log.info("Registered module IPC route: %s", route_name)

    async def start(self) -> None:
        """Start the IPC server. Call in setup_hook after cogs are loaded."""
        self.register_module_routes()
        await self._server.start()


# ---------- Client ----------


class Client:
    """
    IPC client with graceful error handling.

    Used by the dashboard to talk to the bot. If the bot is unreachable
    (offline, network issue), request() returns None instead of raising,
    so the dashboard can show a "bot offline" UI instead of crashing.
    """

    def __init__(
        self,
        *,
        host: str = "127.0.0.1",
        port: int = 8765,
        secret_key: str,
    ):
        self._client = ipcx.Client(
            host=host,
            port=port,
            secret_key=secret_key,
        )

    async def request(self, endpoint: str, **kwargs) -> Any:
        """
        Call an IPC endpoint. Returns the response data, or None on error.

        Errors are logged but never raised — callers always need to handle
        the None case anyway (bot might be offline), so we don't make them
        also handle exceptions.
        """
        try:
            return await self._client.request(endpoint, **kwargs)
        except Exception as e:
            log.warning("IPC request to %r failed: %s", endpoint, e)
            return None

    async def is_bot_online(self) -> bool:
        """Quick health check."""
        result = await self.request("get_bot_guild_ids")
        return result is not None