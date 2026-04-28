"""
Setting fields — typed declarations for module settings.

Each Field type defines:
  - The Python type it produces (int, str, bool, etc.)
  - How to validate values
  - How to parse/serialize for storage

Fields are declared on a Module's nested Settings class:

    class WelcomeModule(Module):
        class Settings:
            channel = ChannelField(label="Welcome channel", required=True)
            message = TextField(label="Message", default="Hi!")
"""

from __future__ import annotations

import json
from typing import Any, ClassVar


class FieldError(Exception):
    """Raised on invalid Field declarations or invalid runtime values."""


class Field:
    """Base class for all field types. Don't instantiate directly."""

    # Subclasses set this to a human-readable name used in error messages.
    type_name: ClassVar[str] = "field"

    def __init__(
        self,
        *,
        label: str,
        default: Any = None,
        help: str | None = None,
        required: bool = False,
    ):
        if required and default is not None:
            raise FieldError(
                f"{type(self).__name__}: cannot have both required=True and a default value."
            )
        self.label = label
        self.default = default
        self.help = help
        self.required = required

        # The Python attribute name this field is bound to. Set later by Module.
        # (e.g., for `channel = ChannelField(...)`, name becomes "channel")
        self.name: str | None = None

    def __set_name__(self, owner, name: str) -> None:
        """Called automatically when assigned as a class attribute."""
        self.name = name

    # ---- Validation ----

    def validate(self, value: Any) -> None:
        """
        Verify a runtime value is acceptable. Subclasses should override.
        Default: accept anything that isn't None, or None if not required.
        """
        if value is None and self.required:
            raise FieldError(f"{self.name!r} is required but no value was provided.")

    # ---- Parsing form input ----

    def parse(self, raw: str | None) -> Any:
        """
        Convert a raw form-submitted string into the Python value to store.
        None or empty string means 'unset'.
        Subclasses override to convert types.
        """
        if raw is None or raw == "":
            return None
        return raw

    # ---- Storage ----

    def serialize(self, value: Any) -> str | None:
        """Encode a Python value to a string for the settings table."""
        if value is None:
            return None
        return json.dumps(value)

    def deserialize(self, raw: str | None) -> Any:
        """Decode a string from the settings table back to a Python value."""
        if raw is None:
            return None
        return json.loads(raw)

    # ---- For dashboard rendering (used later) ----

    @property
    def widget(self) -> str:
        """A short identifier the dashboard uses to pick a renderer."""
        raise NotImplementedError


# ---------- Concrete field types ----------


class TextField(Field):
    """Single-line text input."""

    type_name = "text"

    def __init__(self, *, max_length: int | None = None, **kwargs):
        super().__init__(**kwargs)
        self.max_length = max_length

    def parse(self, raw: str | None) -> str | None:
        value = super().parse(raw)
        if value is None:
            return None
        return str(value)

    def validate(self, value: Any) -> None:
        super().validate(value)
        if value is None:
            return
        if not isinstance(value, str):
            raise FieldError(f"{self.name!r}: expected string, got {type(value).__name__}.")
        if self.max_length is not None and len(value) > self.max_length:
            raise FieldError(
                f"{self.name!r}: longer than max_length={self.max_length}."
            )

    @property
    def widget(self) -> str:
        return "text"


class TextAreaField(TextField):
    """Multi-line text input. Same as TextField, different widget."""

    type_name = "textarea"

    @property
    def widget(self) -> str:
        return "textarea"


class BoolField(Field):
    """Boolean checkbox/toggle."""

    type_name = "bool"

    def parse(self, raw: str | None) -> bool:
        # HTML checkboxes submit "on" when checked, nothing when unchecked.
        return raw == "on"

    def validate(self, value: Any) -> None:
        super().validate(value)
        if value is None:
            return
        if not isinstance(value, bool):
            raise FieldError(f"{self.name!r}: expected bool, got {type(value).__name__}.")

    @property
    def widget(self) -> str:
        return "toggle"


class IntField(Field):
    """Integer input with optional min/max."""

    type_name = "int"

    def __init__(self, *, min: int | None = None, max: int | None = None, **kwargs):
        super().__init__(**kwargs)
        self.min = min
        self.max = max

    def parse(self, raw: str | None) -> int | None:
        if raw is None or raw == "":
            return None
        try:
            return int(raw)
        except ValueError as e:
            raise FieldError(f"{self.name!r}: {raw!r} is not a valid integer.") from e

    def validate(self, value: Any) -> None:
        super().validate(value)
        if value is None:
            return
        if not isinstance(value, int) or isinstance(value, bool):
            # bool is a subclass of int; reject explicitly
            raise FieldError(f"{self.name!r}: expected int, got {type(value).__name__}.")
        if self.min is not None and value < self.min:
            raise FieldError(f"{self.name!r}: value {value} below min={self.min}.")
        if self.max is not None and value > self.max:
            raise FieldError(f"{self.name!r}: value {value} above max={self.max}.")

    @property
    def widget(self) -> str:
        return "number"


class ColorField(Field):
    """Hex color string like '#E984FF'."""

    type_name = "color"

    def parse(self, raw: str | None) -> str | None:
        value = super().parse(raw)
        if value is None:
            return None
        return str(value)

    def validate(self, value: Any) -> None:
        super().validate(value)
        if value is None:
            return
        if not isinstance(value, str):
            raise FieldError(f"{self.name!r}: expected string, got {type(value).__name__}.")
        if not (value.startswith("#") and len(value) == 7):
            raise FieldError(f"{self.name!r}: {value!r} is not a valid hex color (#RRGGBB).")
        try:
            int(value[1:], 16)
        except ValueError as e:
            raise FieldError(f"{self.name!r}: {value!r} contains non-hex characters.") from e

    @property
    def widget(self) -> str:
        return "color"


class ChoiceField(Field):
    """Dropdown with a fixed list of choices."""

    type_name = "choice"

    def __init__(self, *, choices: list[str], **kwargs):
        super().__init__(**kwargs)
        if not choices:
            raise FieldError("ChoiceField requires non-empty choices.")
        self.choices = list(choices)

    def parse(self, raw: str | None) -> str | None:
        value = super().parse(raw)
        if value is None:
            return None
        return str(value)

    def validate(self, value: Any) -> None:
        super().validate(value)
        if value is None:
            return
        if value not in self.choices:
            raise FieldError(
                f"{self.name!r}: {value!r} is not one of {self.choices}."
            )

    @property
    def widget(self) -> str:
        return "choice"


# ---------- Discord-aware fields ----------
# These are conceptually "an integer ID" but with semantic meaning that the
# dashboard uses to pick a different widget (channel dropdown, role dropdown, etc).


class _SnowflakeField(Field):
    """Base for Discord ID fields. Stores a BigInt; renders as a dropdown."""

    def parse(self, raw: str | None) -> int | None:
        if raw is None or raw == "":
            return None
        try:
            return int(raw)
        except ValueError as e:
            raise FieldError(f"{self.name!r}: {raw!r} is not a valid Discord ID.") from e

    def validate(self, value: Any) -> None:
        super().validate(value)
        if value is None:
            return
        if not isinstance(value, int) or isinstance(value, bool):
            raise FieldError(f"{self.name!r}: expected int, got {type(value).__name__}.")
        if value < 0:
            raise FieldError(f"{self.name!r}: Discord IDs are non-negative.")


class ChannelField(_SnowflakeField):
    """Dropdown of guild channels."""
    type_name = "channel"

    @property
    def widget(self) -> str:
        return "channel"


class RoleField(_SnowflakeField):
    """Dropdown of guild roles."""
    type_name = "role"

    @property
    def widget(self) -> str:
        return "role"


class CategoryField(_SnowflakeField):
    """Dropdown of channel categories."""
    type_name = "category"

    @property
    def widget(self) -> str:
        return "category"