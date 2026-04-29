"""kennelkit.dashboard — Quart-based dashboard for kennelkit modules."""

from __future__ import annotations

import os
from pathlib import Path

from quart import (
    Quart,
    abort,
    redirect,
    render_template,
    request,
    url_for,
)
from quart_discord import (
    DiscordOAuth2Session,
    Unauthorized,
    requires_authorization,
)

from kennelkit.dashboard.auth import (
    configure_ipc,
    get_manageable_guilds,
    verify_guild_perms,
)
from kennelkit.fields import FieldError
from kennelkit.ipc import Client
from kennelkit.modules import registry
from kennelkit.storage import (
    load_settings,
    save_settings,
    set_enabled as _set_enabled,
)


# Path to kennelkit's bundled templates and static files.
_PACKAGE_DIR = Path(__file__).parent
_TEMPLATE_DIR = _PACKAGE_DIR / "templates"
_STATIC_DIR = _PACKAGE_DIR / "static"


def create_dashboard(
    *,
    secret_key: str,
    discord_client_id: str | int,
    discord_client_secret: str,
    discord_redirect_uri: str,
    ipc_secret: str,
    ipc_host: str = "127.0.0.1",
    ipc_port: int = 8765,
    bot_name: str = "Bot",
    bot_logo_url: str | None = None,
    theme: str = "light",
    insecure_oauth: bool = False,
) -> Quart:
    """
    Build and return a Quart dashboard application.

    Args:
        secret_key: Used to sign session cookies. Generate with secrets.token_urlsafe(32).
        discord_client_id: From the Discord Developer Portal (OAuth2 page).
        discord_client_secret: From the Discord Developer Portal.
        discord_redirect_uri: Must exactly match a registered redirect URI.
        ipc_secret: Shared secret between the bot and dashboard.
        ipc_host: Bot's IPC host (default 127.0.0.1).
        ipc_port: Bot's IPC port (default 8765).
        bot_name: Display name shown in navbar and titles.
        bot_logo_url: URL to a logo shown in the navbar. Optional.
        theme: DaisyUI theme name (e.g. 'light', 'dark', 'valentine', or a custom theme).
        insecure_oauth: If True, sets OAUTHLIB_INSECURE_TRANSPORT=1 for HTTP dev. Don't use in prod.

    Returns:
        A configured Quart app. Run with hypercorn or any ASGI server.
    """
    if insecure_oauth:
        os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

    app = Quart(
        __name__,
        template_folder=str(_TEMPLATE_DIR),
        static_folder=str(_STATIC_DIR),
        static_url_path="/static",
    )
    app.secret_key = secret_key
    app.config["DISCORD_CLIENT_ID"] = int(discord_client_id)
    app.config["DISCORD_CLIENT_SECRET"] = discord_client_secret
    app.config["DISCORD_REDIRECT_URI"] = discord_redirect_uri

    discord = DiscordOAuth2Session(app)

    # Build and register the IPC client used by auth helpers and routes
    ipc_client = Client(host=ipc_host, port=ipc_port, secret_key=ipc_secret)
    configure_ipc(ipc_client)

    # Make branding values available to every template
    @app.context_processor
    async def inject_branding():
        return {
            "bot_name": bot_name,
            "bot_logo_url": bot_logo_url,
            "theme": theme,
        }

    # ------------------------------------------------------------------
    # Public routes
    # ------------------------------------------------------------------

    @app.route("/")
    async def index():
        if await discord.authorized:
            return redirect(url_for("guilds"))
        return await render_template("index.html", user=None)

    @app.route("/login")
    async def login():
        return await discord.create_session(scope=["identify", "guilds"])

    @app.route("/callback")
    async def callback():
        try:
            await discord.callback()
        except Exception as e:
            return f"OAuth error: {e}", 400
        return redirect(url_for("guilds"))

    @app.route("/logout")
    async def logout():
        discord.revoke()
        return redirect(url_for("index"))

    @app.errorhandler(Unauthorized)
    async def unauthorized_handler(e):
        return redirect(url_for("login"))

    # ------------------------------------------------------------------
    # Authenticated routes
    # ------------------------------------------------------------------

    @app.route("/guilds")
    @requires_authorization
    async def guilds():
        user = await discord.fetch_user()
        data = await get_manageable_guilds(discord)
        return await render_template(
            "guilds.html",
            user=user,
            with_bot=data["with_bot"],
            without_bot=data["without_bot"],
            bot_online=data["bot_online"],
            client_id=str(discord_client_id),
        )

    @app.route("/guild/<int:guild_id>/modules", methods=["GET", "POST"])
    @requires_authorization
    async def guild_modules(guild_id: int):
        guild_info = await verify_guild_perms(discord, guild_id)
        if guild_info is None:
            abort(403)

        all_modules = registry.all()

        if request.method == "POST":
            form = await request.form
            submitted = set(form.getlist("module"))
            for module in all_modules:
                should_be_enabled = module.id in submitted
                await _set_enabled(module.id, guild_id, should_be_enabled)
            return redirect(url_for("guild_modules", guild_id=guild_id))

        # Build the per-module enabled state for the template
        module_states = []
        for module in all_modules:
            is_enabled = await module.is_enabled(guild_id)
            module_states.append({
                "module": module,
                "enabled": is_enabled,
            })

        return await render_template(
            "guild_modules.html",
            guild=guild_info,
            module_states=module_states,
        )

    @app.route(
        "/guild/<int:guild_id>/modules/<module_id>/settings",
        methods=["GET", "POST"],
    )
    @requires_authorization
    async def guild_module_settings(guild_id: int, module_id: str):
        guild_info = await verify_guild_perms(discord, guild_id)
        if guild_info is None:
            abort(403)

        module = registry.get(module_id)
        if module is None or not module.__schema__:
            abort(404)

        schema = module.__schema__

        if request.method == "POST":
            form = await request.form
            values: dict = {}
            for key, field in schema.items():
                raw = form.get(key)
                try:
                    values[key] = field.parse(raw)
                except FieldError as e:
                    return f"Invalid input for {key}: {e}", 400

            try:
                await save_settings(module.id, schema, guild_id, values)
            except FieldError as e:
                return f"Invalid setting: {e}", 400

            return redirect(url_for(
                "guild_module_settings",
                guild_id=guild_id,
                module_id=module_id,
            ))

        # GET: load saved values + any external data the form needs
        saved = await load_settings(module.id, schema, guild_id)
        # `saved` is a dataclass; convert to a flat dict for the template
        saved_dict = {f: getattr(saved, f) for f in schema.keys()}

        # If the form has any channel/role/category/etc fields, fetch the lists
        extra_data: dict = {}
        widgets = {f.widget for f in schema.values()}

        if "channel" in widgets:
            extra_data["channels"] = await ipc_client.request(
                "get_guild_channels", guild_id=guild_id,
            ) or []
        if "role" in widgets:
            extra_data["roles"] = await ipc_client.request(
                "get_guild_roles", guild_id=guild_id,
            ) or []
        if "category" in widgets:
            extra_data["categories"] = await ipc_client.request(
                "get_guild_categories", guild_id=guild_id,
            ) or []

        return await render_template(
            "guild_module_settings.html",
            guild=guild_info,
            module=module,
            schema=schema,
            saved=saved_dict,
            **extra_data,
        )

    return app


__all__ = [
    "configure_ipc",
    "create_dashboard",
    "get_manageable_guilds",
    "verify_guild_perms",
]