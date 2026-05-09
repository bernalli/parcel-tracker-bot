"""Shared pytest fixtures for parcel_tracker tests."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def event_loop_policy() -> asyncio.AbstractEventLoopPolicy:
    """Use the default asyncio policy for all tests."""
    return asyncio.DefaultEventLoopPolicy()


@pytest.fixture
def tmp_db_path(tmp_path: Path) -> Path:
    """Provide a temporary SQLite database path."""
    return tmp_path / "test.db"


@pytest.fixture
def fixtures_dir() -> Path:
    """Path to the test fixtures directory."""
    return Path(__file__).parent / "fixtures"
