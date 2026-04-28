"""Tests for kennelkit.modules."""

import pytest

from kennelkit.fields import ChannelField, TextField
from kennelkit.modules import Module, ModuleError, registry

@pytest.fixture(autouse=True)
def clean_registry():
    """Clear the registry before each test to prevent cross-test pollution."""
    registry._clear()
    yield
    registry._clear()

# ---------- Required attributes ----------


class TestRequiredAttrs:
    def test_missing_id_raises(self):
        with pytest.raises(ModuleError, match="'id'"):
            class Bad(Module):
                name = "Bad"
                description = "x"

    def test_missing_name_raises(self):
        with pytest.raises(ModuleError, match="'name'"):
            class Bad(Module):
                id = "bad"
                description = "x"

    def test_missing_description_raises(self):
        with pytest.raises(ModuleError, match="'description'"):
            class Bad(Module):
                id = "bad"
                name = "Bad"

    def test_empty_id_raises(self):
        with pytest.raises(ModuleError, match="non-empty"):
            class Bad(Module):
                id = ""
                name = "Bad"
                description = "x"

    def test_id_must_be_string(self):
        with pytest.raises(ModuleError, match="non-empty string"):
            class Bad(Module):
                id = 42  # type: ignore
                name = "Bad"
                description = "x"

    def test_minimum_valid_module(self):
        class M(Module):
            id = "m"
            name = "M"
            description = "x"
        assert M.id == "m"
        assert M.name == "M"
        assert M.icon is None 

    def test_custom_icon(self):
        class M(Module):
            id = "m"
            name = "M"
            description = "x"
            icon = "🎉"
        assert M.icon == "🎉"


# ---------- Schema discovery ----------


class TestSchemaDiscovery:
    def test_no_settings_class_means_empty_schema(self):
        class M(Module):
            id = "m"
            name = "M"
            description = "x"
        assert M.__schema__ == {}

    def test_empty_settings_class_means_empty_schema(self):
        class M(Module):
            id = "m"
            name = "M"
            description = "x"
            class Settings:
                pass
        assert M.__schema__ == {}

    def test_fields_in_settings_become_schema(self):
        class M(Module):
            id = "m"
            name = "M"
            description = "x"
            class Settings:
                channel = ChannelField(label="Channel", required=True)
                message = TextField(label="Message", default="hi")

        assert set(M.__schema__.keys()) == {"channel", "message"}
        assert isinstance(M.__schema__["channel"], ChannelField)
        assert isinstance(M.__schema__["message"], TextField)

    def test_field_names_set_correctly(self):
        class M(Module):
            id = "m"
            name = "M"
            description = "x"
            class Settings:
                my_channel = ChannelField(label="Channel")

        assert M.__schema__["my_channel"].name == "my_channel"

    def test_non_field_attrs_excluded(self):
        class M(Module):
            id = "m"
            name = "M"
            description = "x"
            class Settings:
                channel = ChannelField(label="Channel")
                CONSTANT = 42  # not a field
                helper = "not a field"

        assert "channel" in M.__schema__
        assert "CONSTANT" not in M.__schema__
        assert "helper" not in M.__schema__

    def test_underscored_attrs_excluded(self):
        class M(Module):
            id = "m"
            name = "M"
            description = "x"
            class Settings:
                _private = TextField(label="Private")
                public = TextField(label="Public")

        assert "_private" not in M.__schema__
        assert "public" in M.__schema__

    def test_parent_settings_not_inherited(self):
        """Subclass without its own Settings shouldn't pick up parent's."""
        class Parent(Module):
            id = "parent"
            name = "Parent"
            description = "x"
            class Settings:
                field = TextField(label="x")

        class Child(Parent):
            id = "child"
            name = "Child"
            description = "x"
            # no Settings class

        assert Parent.__schema__ != {}
        assert Child.__schema__ == {}


# ---------- Registry ----------


class TestRegistry:
    def test_module_auto_registered(self):
        class M(Module):
            id = "m"
            name = "M"
            description = "x"

        assert registry.get("m") is M
        assert M in registry.all()

    def test_duplicate_id_raises(self):
        class A(Module):
            id = "shared"
            name = "A"
            description = "x"

        with pytest.raises(ModuleError, match="Duplicate module id"):
            class B(Module):
                id = "shared"
                name = "B"
                description = "x"

    def test_unregister(self):
        class M(Module):
            id = "m"
            name = "M"
            description = "x"

        registry.unregister("m")
        assert registry.get("m") is None

    def test_clear(self):
        class A(Module):
            id = "a"
            name = "A"
            description = "x"

        class B(Module):
            id = "b"
            name = "B"
            description = "x"

        assert len(registry.all()) == 2
        registry._clear()
    assert len(registry.all()) == 0

    def test_redefining_same_class_does_not_raise(self):
        """Re-importing the same module shouldn't raise, just re-register."""
        class M(Module):
            id = "m"
            name = "M"
            description = "x"

        # Simulate re-registration of the same class.
        registry.register(M)  # no raise