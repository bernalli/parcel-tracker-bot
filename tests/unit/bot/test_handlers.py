"""Smoke tests for handlers.register_handlers — wire-up only, no real Telegram."""

from __future__ import annotations

from unittest.mock import MagicMock

from parcel_tracker.bot.handlers import register_handlers


def test_register_handlers_wires_dependencies() -> None:
    """register_handlers stores deps in app.bot_data and adds handlers."""
    app = MagicMock()
    app.bot_data = {}
    config = MagicMock()
    parcel_repo = MagicMock()
    user_repo = MagicMock()
    registry = MagicMock()

    register_handlers(
        app,
        config=config,
        parcel_repo=parcel_repo,
        user_repo=user_repo,
        registry=registry,
    )

    # Deps stored
    assert app.bot_data["config"] is config
    assert app.bot_data["parcel_repo"] is parcel_repo
    assert app.bot_data["user_repo"] is user_repo
    assert app.bot_data["registry"] is registry

    # Handlers added (>= 19: 18 commands + message + callback)
    assert app.add_handler.call_count >= 19


def test_register_handlers_idempotent_per_call() -> None:
    """Calling register_handlers twice doubles the handler count (no de-dup logic)."""
    app = MagicMock()
    app.bot_data = {}

    register_handlers(
        app,
        config=MagicMock(),
        parcel_repo=MagicMock(),
        user_repo=MagicMock(),
        registry=MagicMock(),
    )
    first_count = app.add_handler.call_count

    register_handlers(
        app,
        config=MagicMock(),
        parcel_repo=MagicMock(),
        user_repo=MagicMock(),
        registry=MagicMock(),
    )
    assert app.add_handler.call_count == first_count * 2
