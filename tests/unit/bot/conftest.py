"""Fixtures for tests/unit/bot/."""

from __future__ import annotations

from pathlib import Path

import pytest

from parcel_tracker.db.migrations import init_schema
from parcel_tracker.db.repository import UserRepository


@pytest.fixture
async def tmp_user_repo(tmp_path: Path) -> UserRepository:
    db_path = tmp_path / "test.db"
    await init_schema(str(db_path))
    repo = UserRepository(str(db_path))
    # Pre-populate allowed_users so set_language UPDATE has a row to hit
    await repo.add_user(user_id=123, added_by=999)
    return repo
