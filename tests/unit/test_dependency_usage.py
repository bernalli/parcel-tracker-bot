"""Every declared dependency is used by the code (no dead installs)."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
SOURCE = "\n".join(p.read_text(encoding="utf-8") for p in (ROOT / "src").rglob("*.py"))

# Distribution name → how the code refers to it (import name or parser string).
_USAGE = {
    "python-telegram-bot": r"^\s*(from|import) telegram\b",
    "httpx": r"^\s*(from|import) httpx\b",
    "aiosqlite": r"^\s*(from|import) aiosqlite\b",
    "python-dotenv": r"^\s*(from|import) dotenv\b",
    "beautifulsoup4": r"^\s*(from|import) bs4\b",
    "lxml": r"BeautifulSoup\([^)]*\"lxml\"",
    "Pillow": r"^\s*(from|import) PIL\b",
    "staticmap": r"^\s*(from|import) staticmap\b",
    "tenacity": r"^\s*(from|import) tenacity\b",
    "structlog": r"^\s*(from|import) structlog\b",
    "prometheus-client": r"^\s*(from|import) prometheus_client\b",
    "python-json-logger": r"^\s*(from|import) pythonjsonlogger\b",
    "aiohttp": r"^\s*(from|import) aiohttp\b",
    "jinja2": r"^\s*(from|import) jinja2\b",
}


def _name(requirement: str) -> str:
    return re.split(r"[\[<>=!~ ;]", requirement, maxsplit=1)[0]


RUNTIME = [_name(r) for r in PYPROJECT["project"]["dependencies"]]
EXTRAS = {
    extra: [_name(r) for r in reqs]
    for extra, reqs in PYPROJECT["project"].get("optional-dependencies", {}).items()
    if extra != "dev"
}


@pytest.mark.parametrize("dist", RUNTIME)
def test_runtime_dependency_is_used(dist: str) -> None:
    assert dist in _USAGE, f"add a usage pattern for {dist}"
    assert re.search(_USAGE[dist], SOURCE, flags=re.MULTILINE), f"{dist} is never used"


def test_optional_extras_are_used_and_not_duplicated() -> None:
    for extra, dists in EXTRAS.items():
        for dist in dists:
            assert dist not in RUNTIME, f"[{extra}] repeats core dependency {dist}"
            assert re.search(_USAGE.get(dist, r"(?!)"), SOURCE, flags=re.MULTILINE), (
                f"[{extra}] installs {dist}, which the code never uses"
            )
