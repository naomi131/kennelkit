"""kennelkit — a modular framework for Discord bots with auto-generated dashboards."""

__version__ = "0.0.1"

from kennelkit import db
from kennelkit import ipc
from kennelkit.fields import (
    BoolField,
    CategoryField,
    ChannelField,
    ChoiceField,
    ColorField,
    Field,
    FieldError,
    IntField,
    RoleField,
    TextAreaField,
    TextField,
)
from kennelkit.modules import (
    Module,
    ModuleError,
    registry,
)
from kennelkit.storage import (
    is_enabled,
    load_settings,
    save_setting,
    save_settings,
    set_enabled,
)


__all__ = [
    "__version__",
    "db",
    # Fields
    "Field",
    "FieldError",
    "TextField",
    "TextAreaField",
    "BoolField",
    "IntField",
    "ColorField",
    "ChoiceField",
    "ChannelField",
    "RoleField",
    "CategoryField",
    # Modules
    "Module",
    "ModuleError",
    "registry",
    # Settings
    "is_enabled",
    "load_settings",
    "save_setting",
    "save_settings",
    "set_enabled",
    # IPC
    "__version__",
    "db",
    "ipc",
]