"""
Framework-owned database models.

These tables are managed by kennelkit and exist in every bot using the framework:

  module_states   — which modules are enabled per guild
  module_settings — per-module setting values per guild

Modules can declare additional tables in their own models.py, but these two
are reserved for the framework.
"""

from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from kennelkit.db.core import Base


class ModuleState(Base):
    """Whether a given module is enabled in a given guild."""
    __tablename__ = "kennelkit_module_states"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    module_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class ModuleSetting(Base):
    """Stored setting values for modules. JSON-encoded values."""
    __tablename__ = "kennelkit_module_settings"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    module_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    setting_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    setting_value: Mapped[str | None] = mapped_column(Text, nullable=True)