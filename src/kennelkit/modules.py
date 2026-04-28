"""
Module — the base class users subclass to declare a feature.

Each Module subclass:
  - Has an id, name, description, icon
  - Optionally declares a nested Settings class with Field declarations
  - Is auto-registered when the class is defined
"""

from __future__ import annotations

from typing import ClassVar

from kennelkit.fields import Field


class ModuleError(Exception):
    """Raised on invalid Module declarations."""


class _Registry:
    """Holds all registered Module subclasses, keyed by id."""

    def __init__(self) -> None:
        self._modules: dict[str, type[Module]] = {}

    def register(self, module: type[Module]) -> None:
        if module.id in self._modules and self._modules[module.id] is not module:
            raise ModuleError(
                f"Duplicate module id: {module.id!r} "
                f"(already registered: {self._modules[module.id].__name__})"
            )
        self._modules[module.id] = module

    def unregister(self, module_id: str) -> None:
        """Used by tests to clean up between cases."""
        self._modules.pop(module_id, None)

    def get(self, module_id: str) -> type[Module] | None:
        return self._modules.get(module_id)

    def all(self) -> list[type[Module]]:
        return list(self._modules.values())

    def _clear(self) -> None:
        """Wipe all registrations. Test-only — not part of the public API."""
        self._modules.clear()


# Global registry. Importable as kennelkit.registry.
registry = _Registry()


# Required class attributes on every Module subclass.
_REQUIRED_ATTRS = ("id", "name", "description")


class Module:
    """
    Base class for kennelkit modules.

    Subclasses declare metadata as class attributes and (optionally) a nested
    `Settings` class with Field instances:

        class WelcomeModule(Module):
            id = "welcome"
            name = "Welcome"
            description = "Greet new members."
            icon = "👋"

            class Settings:
                channel = ChannelField(label="Channel", required=True)
                message = TextField(label="Message", default="Hi!")

    On class definition, kennelkit:
      - Validates the metadata
      - Builds a schema from the Settings class
      - Registers the module so the framework can find it
    """

    # Override these in subclasses.
    id: ClassVar[str]
    name: ClassVar[str]
    description: ClassVar[str]
    icon: ClassVar[str | None] = None # Icon is reccomended for better aesthatics and organisation.

    # Set automatically by __init_subclass__.
    __schema__: ClassVar[dict[str, Field]]

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)

        # Validate required attributes.
        for attr in _REQUIRED_ATTRS:
            if not hasattr(cls, attr) or getattr(cls, attr) is None:
                raise ModuleError(
                    f"{cls.__name__}: missing required class attribute {attr!r}."
                )

        if not isinstance(cls.id, str) or not cls.id:
            raise ModuleError(f"{cls.__name__}: 'id' must be a non-empty string.")
        if not isinstance(cls.name, str) or not cls.name:
            raise ModuleError(f"{cls.__name__}: 'name' must be a non-empty string.")

        # Discover fields from nested Settings class, if present.
        cls.__schema__ = _build_schema(cls)

        # Register.
        registry.register(cls)


def _build_schema(cls: type[Module]) -> dict[str, Field]:
    """Walk cls.Settings (if any) and collect Field instances."""
    settings_cls = cls.__dict__.get("Settings")
    if settings_cls is None:
        return {}

    schema: dict[str, Field] = {}
    for attr_name, value in settings_cls.__dict__.items():
        if attr_name.startswith("_"):
            continue
        if isinstance(value, Field):
            # __set_name__ has already set value.name; double-check.
            if value.name is None:
                value.name = attr_name
            schema[attr_name] = value
    return schema