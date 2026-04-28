"""Tests for kennelkit.ipc."""

import pytest

from kennelkit.ipc import (
    _pending_routes,
    collect_routes_from_cog,
    route,
)


@pytest.fixture(autouse=True)
def clean_pending_routes():
    """Clear pending routes between tests to prevent cross-contamination."""
    _pending_routes.clear()
    yield
    _pending_routes.clear()


# ---------- @route decorator ----------


class TestRouteDecorator:
    def test_marks_function(self):
        @route()
        async def my_route(self, data):
            return "ok"

        assert my_route.__kennelkit_ipc_route__ == "my_route"

    def test_custom_name(self):
        @route("custom_name")
        async def my_route(self, data):
            return "ok"

        assert my_route.__kennelkit_ipc_route__ == "custom_name"

    def test_duplicate_name_raises(self):
        @route()
        async def foo(self, data):
            pass

        with pytest.raises(ValueError, match="Duplicate IPC route"):
            @route()
            async def foo(self, data):  # noqa: F811
                pass

    def test_pending_routes_collected(self):
        @route()
        async def alpha(self, data):
            pass

        @route()
        async def beta(self, data):
            pass

        assert "alpha" in _pending_routes
        assert "beta" in _pending_routes


# ---------- collect_routes_from_cog ----------


class TestCollectRoutes:
    def test_finds_decorated_methods(self):
        class FakeCog:
            @route()
            async def open_ticket(self, data):
                return {"id": 1}

            async def not_a_route(self, data):
                return None

        cog = FakeCog()
        found = collect_routes_from_cog(cog)
        names = [name for name, _ in found]
        assert "open_ticket" in names
        assert "not_a_route" not in names

    def test_returns_empty_when_no_routes(self):
        class FakeCog:
            async def hello(self):
                return "hi"

        cog = FakeCog()
        assert collect_routes_from_cog(cog) == []

    def test_skips_underscored_attrs(self):
        class FakeCog:
            @route()
            async def public(self, data):
                pass

            _private_attr = "x"

        cog = FakeCog()
        found = collect_routes_from_cog(cog)
        names = [name for name, _ in found]
        assert "public" in names
        assert "_private_attr" not in names