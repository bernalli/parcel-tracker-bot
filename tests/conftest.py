"""Shared pytest fixtures for parcel_tracker tests."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from parcel_tracker.i18n import Translator, set_default_translator


@pytest.fixture(scope="session")
def event_loop_policy() -> asyncio.AbstractEventLoopPolicy:
    """Use the default asyncio policy for all tests."""
    return asyncio.DefaultEventLoopPolicy()


@pytest.fixture(autouse=True)
def _init_default_translator() -> None:
    """Set the default Translator to en before every test (gettext fallback to msgid)."""
    locale_root = (
        Path(__file__).resolve().parent.parent / "src" / "parcel_tracker" / "i18n" / "locale"
    )
    set_default_translator(Translator(locale="en", locale_dir=locale_root))


@pytest.fixture
def tmp_db_path(tmp_path: Path) -> Path:
    """Provide a temporary SQLite database path."""
    return tmp_path / "test.db"


@pytest.fixture
def fixtures_dir() -> Path:
    """Path to the test fixtures directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def _reset_cooldowns(monkeypatch: pytest.MonkeyPatch) -> None:
    """Per-user cooldowns are module state; give every test a clean slate."""
    from parcel_tracker.bot import throttle

    monkeypatch.setattr(throttle, "CHECKALL", throttle.Cooldown(throttle.CHECKALL_COOLDOWN_S))
    monkeypatch.setattr(throttle, "REFRESH", throttle.Cooldown(throttle.REFRESH_COOLDOWN_S))
