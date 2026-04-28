"""Tests for kennelkit.fields."""

import pytest

from kennelkit.fields import (
    BoolField,
    CategoryField,
    ChannelField,
    ChoiceField,
    ColorField,
    FieldError,
    IntField,
    RoleField,
    TextAreaField,
    TextField,
)


# ---------- Field declaration validation ----------


class TestFieldDeclaration:
    def test_required_with_default_raises(self):
        with pytest.raises(FieldError, match="required=True and a default"):
            TextField(label="x", default="hello", required=True)

    def test_required_no_default_ok(self):
        f = TextField(label="x", required=True)
        assert f.required is True
        assert f.default is None

    def test_default_no_required_ok(self):
        f = TextField(label="x", default="hi")
        assert f.required is False
        assert f.default == "hi"

    def test_choice_field_requires_choices(self):
        with pytest.raises(FieldError, match="non-empty"):
            ChoiceField(label="x", choices=[])


# ---------- __set_name__ binding ----------


class TestFieldNameBinding:
    def test_name_set_when_assigned_to_class(self):
        class FakeSettings:
            my_field = TextField(label="x")

        assert FakeSettings.my_field.name == "my_field"


# ---------- TextField ----------
# For short response text


class TestTextField:
    def test_parse_string(self):
        f = TextField(label="x")
        assert f.parse("hello") == "hello"

    def test_parse_empty_returns_none(self):
        f = TextField(label="x")
        assert f.parse("") is None
        assert f.parse(None) is None

    def test_validate_accepts_string(self):
        f = TextField(label="x")
        f.validate("hello")  # no raise

    def test_validate_rejects_non_string(self):
        f = TextField(label="x")
        f.name = "x"
        with pytest.raises(FieldError, match="expected string"):
            f.validate(42)

    def test_validate_required_rejects_none(self):
        f = TextField(label="x", required=True)
        f.name = "x"
        with pytest.raises(FieldError, match="required"):
            f.validate(None)

    def test_max_length_enforced(self):
        f = TextField(label="x", max_length=5)
        f.name = "x"
        f.validate("abcde")  # ok
        with pytest.raises(FieldError, match="max_length"):
            f.validate("abcdef")

# ---------- TextAreaField ----------
# For long response text

class TestTextAreaField:
    def test_inherits_text_behavior(self):
        f = TextAreaField(label="x")
        assert f.parse("hello") == "hello"
        f.validate("hello")

    def test_widget_is_textarea(self):
        assert TextAreaField(label="x").widget == "textarea"


# ---------- BoolField ----------


class TestBoolField:
    def test_parse_on_is_true(self):
        f = BoolField(label="x")
        assert f.parse("on") is True

    def test_parse_anything_else_is_false(self):
        f = BoolField(label="x")
        assert f.parse(None) is False
        assert f.parse("") is False
        assert f.parse("false") is False

    def test_validate_bool(self):
        f = BoolField(label="x")
        f.validate(True)
        f.validate(False)

    def test_validate_rejects_non_bool(self):
        f = BoolField(label="x")
        f.name = "x"
        with pytest.raises(FieldError, match="expected bool"):
            f.validate("true")


# ---------- IntField ----------


class TestIntField:
    def test_parse_int(self):
        f = IntField(label="x")
        assert f.parse("42") == 42

    def test_parse_invalid_raises(self):
        f = IntField(label="x")
        f.name = "x"
        with pytest.raises(FieldError, match="not a valid integer"):
            f.parse("hello")

    def test_min_max_enforced(self):
        f = IntField(label="x", min=0, max=100)
        f.name = "x"
        f.validate(50)
        with pytest.raises(FieldError, match="below min"):
            f.validate(-1)
        with pytest.raises(FieldError, match="above max"):
            f.validate(101)

    def test_bool_rejected(self):
        f = IntField(label="x")
        f.name = "x"
        with pytest.raises(FieldError, match="expected int"):
            f.validate(True)


# ---------- ColorField ----------


class TestColorField:
    def test_valid_hex(self):
        f = ColorField(label="x")
        f.validate("#E984FF")
        f.validate("#000000")

    def test_invalid_format(self):
        f = ColorField(label="x")
        f.name = "x"
        with pytest.raises(FieldError):
            f.validate("E984FF")  # missing #
        with pytest.raises(FieldError):
            f.validate("#FFF")  # too short
        with pytest.raises(FieldError):
            f.validate("#GGGGGG")  # invalid hex


# ---------- ChoiceField ----------


class TestChoiceField:
    def test_validate_in_choices(self):
        f = ChoiceField(label="x", choices=["a", "b", "c"])
        f.validate("b")

    def test_validate_not_in_choices(self):
        f = ChoiceField(label="x", choices=["a", "b"])
        f.name = "x"
        with pytest.raises(FieldError, match="not one of"):
            f.validate("c")


# ---------- Snowflake fields ----------


class TestChannelField:
    def test_parse_int_string(self):
        f = ChannelField(label="x")
        assert f.parse("123456789012345678") == 123456789012345678

    def test_parse_invalid_raises(self):
        f = ChannelField(label="x")
        f.name = "x"
        with pytest.raises(FieldError, match="not a valid Discord ID"):
            f.parse("abc")

    def test_widget_is_channel(self):
        assert ChannelField(label="x").widget == "channel"


class TestRoleField:
    def test_widget_is_role(self):
        assert RoleField(label="x").widget == "role"


class TestCategoryField:
    def test_widget_is_category(self):
        assert CategoryField(label="x").widget == "category"


# ---------- Serialization ----------


class TestSerialization:
    def test_int_round_trip(self):
        f = IntField(label="x")
        encoded = f.serialize(42)
        assert f.deserialize(encoded) == 42

    def test_bool_round_trip(self):
        f = BoolField(label="x")
        encoded = f.serialize(True)
        assert f.deserialize(encoded) is True

    def test_string_round_trip(self):
        f = TextField(label="x")
        encoded = f.serialize("hello")
        assert f.deserialize(encoded) == "hello"

    def test_none_serializes_to_none(self):
        f = TextField(label="x")
        assert f.serialize(None) is None
        assert f.deserialize(None) is None