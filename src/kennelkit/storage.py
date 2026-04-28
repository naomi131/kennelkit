"""
Storage layer — bridges Module schemas to the database.

Reads:  await module_class.settings_for(guild_id) -> typed settings object
Writes: await module_class.save_settings(guild_id, **values)
Enabled: await module_class.is_enabled(guild_id) (combines toggle + required-fields)
"""

from __future__ import annotations

from dataclasses import make_dataclass
from typing import Any

from sqlalchemy import select

from kennelkit.db import session
from kennelkit.db.models import ModuleSetting, ModuleState
from kennelkit.fields import Field, FieldError


def _build_settings_dataclass(module_id: str, schema: dict[str, Field]) -> type:
    """
    Build a dataclass type whose fields match the module's schema.
    Each attribute defaults to None (we apply Field defaults at instantiation time).
    """
    if not schema:
        # Empty settings dataclass — useful even if no fields, to keep the API uniform.
        return make_dataclass(f"{module_id.capitalize()}Settings", [])

    attrs = []
    for name, field in schema.items():
        # All settings nullable in the dataclass; we apply defaults explicitly when reading.
        attrs.append((name, "Any", None))

    return make_dataclass(
        f"{module_id.capitalize()}Settings",
        attrs,
        # Make the resulting class repr-friendly
        repr=True,
    )


async def load_settings(module_id: str, schema: dict[str, Field], guild_id: int) -> Any:
    """
    Load all settings for one module in one guild.

    Returns a dataclass-like object with attributes matching the schema.
    Missing values fall back to schema defaults, then to None.
    """
    SettingsCls = _build_settings_dataclass(module_id, schema)

    # Pull every saved value for this guild + module in one query
    async with session() as s:
        result = await s.execute(
            select(ModuleSetting.setting_key, ModuleSetting.setting_value).where(
                ModuleSetting.guild_id == guild_id,
                ModuleSetting.module_id == module_id,
            )
        )
        saved = {key: value for key, value in result.all()}

    # Build the values dict, applying field deserialization + defaults
    values: dict[str, Any] = {}
    for name, field in schema.items():
        raw = saved.get(name)
        if raw is None:
            # No saved value — use field default
            values[name] = field.default
        else:
            # Deserialize the stored JSON
            try:
                values[name] = field.deserialize(raw)
            except Exception:
                # Corrupt value in DB — fall back to default
                values[name] = field.default

    return SettingsCls(**values)


async def save_setting(
    module_id: str,
    schema: dict[str, Field],
    guild_id: int,
    key: str,
    value: Any,
) -> None:
    """Validate and store a single setting."""
    if key not in schema:
        raise FieldError(f"Unknown setting {key!r} for module {module_id!r}.")

    field = schema[key]
    field.validate(value)
    encoded = field.serialize(value)

    async with session() as s:
        existing = await s.execute(
            select(ModuleSetting).where(
                ModuleSetting.guild_id == guild_id,
                ModuleSetting.module_id == module_id,
                ModuleSetting.setting_key == key,
            )
        )
        row = existing.scalar_one_or_none()
        if row is not None:
            row.setting_value = encoded
        else:
            s.add(ModuleSetting(
                guild_id=guild_id,
                module_id=module_id,
                setting_key=key,
                setting_value=encoded,
            ))
        await s.commit()


async def save_settings(
    module_id: str,
    schema: dict[str, Field],
    guild_id: int,
    values: dict[str, Any],
) -> None:
    """Validate and store multiple settings in one transaction."""
    # Validate everything first; only commit if all pass
    for key, value in values.items():
        if key not in schema:
            raise FieldError(f"Unknown setting {key!r} for module {module_id!r}.")
        schema[key].validate(value)

    async with session() as s:
        for key, value in values.items():
            field = schema[key]
            encoded = field.serialize(value)

            existing = await s.execute(
                select(ModuleSetting).where(
                    ModuleSetting.guild_id == guild_id,
                    ModuleSetting.module_id == module_id,
                    ModuleSetting.setting_key == key,
                )
            )
            row = existing.scalar_one_or_none()
            if row is not None:
                row.setting_value = encoded
            else:
                s.add(ModuleSetting(
                    guild_id=guild_id,
                    module_id=module_id,
                    setting_key=key,
                    setting_value=encoded,
                ))
        await s.commit()


async def is_enabled(module_id: str, schema: dict[str, Field], guild_id: int) -> bool:
    """
    A module is considered enabled iff:
      1. The user toggled it on (module_states.enabled = True)
      2. All required fields have non-None values
    """
    async with session() as s:
        # Check the toggle
        result = await s.execute(
            select(ModuleState.enabled).where(
                ModuleState.guild_id == guild_id,
                ModuleState.module_id == module_id,
            )
        )
        toggle = result.scalar_one_or_none()

    if not toggle:
        return False

    # Check required fields
    required_keys = [name for name, field in schema.items() if field.required]
    if not required_keys:
        return True  # nothing else to check

    settings = await load_settings(module_id, schema, guild_id)
    for key in required_keys:
        if getattr(settings, key) is None:
            return False
    return True


async def set_enabled(module_id: str, guild_id: int, enabled: bool) -> None:
    """Toggle a module's enabled state for a guild."""
    async with session() as s:
        existing = await s.get(ModuleState, (guild_id, module_id))
        if existing:
            existing.enabled = enabled
        else:
            s.add(ModuleState(
                guild_id=guild_id,
                module_id=module_id,
                enabled=enabled,
            ))
        await s.commit()