"""The package version, pyproject and CHANGELOG agree."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import parcel_tracker
from parcel_tracker.config import DEFAULT_MAP_USER_AGENT

ROOT = Path(__file__).resolve().parents[2]


def test_versions_agree() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["project"]["version"] == parcel_tracker.__version__


def test_changelog_has_an_entry_for_the_version() -> None:
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    pattern = rf"^## \[{re.escape(parcel_tracker.__version__)}\]"
    assert re.search(pattern, changelog, flags=re.M), "add a CHANGELOG section for this version"


def test_map_user_agent_follows_the_version() -> None:
    assert f"/{parcel_tracker.__version__} " in DEFAULT_MAP_USER_AGENT
