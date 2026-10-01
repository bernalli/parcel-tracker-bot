"""Policy checks on the container build files (Dockerfile, .dockerignore, compose)."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = (ROOT / "Dockerfile").read_text(encoding="utf-8")
COMPOSE = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")


def _dockerignore_patterns() -> set[str]:
    lines = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
    return {ln.strip() for ln in lines if ln.strip() and not ln.lstrip().startswith("#")}


def _healthcheck_snippets() -> list[str]:
    """The inline Python of every healthcheck (Dockerfile HEALTHCHECK + compose)."""
    joined = DOCKERFILE.replace("\\\n", " ")
    snippets = re.findall(r'HEALTHCHECK[^\n]*CMD python -c "([^"]+)"', joined)
    snippets += re.findall(r'"python", "-c", "([^"]+)"', COMPOSE)
    return snippets


def test_base_images_are_pinned_by_digest() -> None:
    images = re.findall(r"^FROM\s+(\S+)", DOCKERFILE, flags=re.MULTILINE)
    assert images, "no FROM line found"
    for image in images:
        assert re.search(r"@sha256:[0-9a-f]{64}$", image), f"{image} is not pinned by digest"


def test_runtime_user_is_unprivileged_without_login_shell() -> None:
    runtime = DOCKERFILE.split("AS runtime", 1)[1]
    assert re.search(r"^USER\s+botuser\s*$", runtime, flags=re.MULTILINE)
    assert "--shell /usr/sbin/nologin" in runtime


def test_no_secret_like_build_args_or_env() -> None:
    names = re.findall(r"^(?:ARG|ENV)\s+([A-Z_]+)", DOCKERFILE, flags=re.MULTILINE)
    names += re.findall(r"^\s+([A-Z_]+)=", DOCKERFILE, flags=re.MULTILINE)
    leaky = [n for n in names if re.search(r"TOKEN|SECRET|PASSWORD|API_KEY", n)]
    assert leaky == []


@pytest.mark.parametrize(
    "pattern",
    [
        ".env",
        ".env.*",
        "*.db",
        "*.sqlite",
        "*.sqlite3",
        ".git/",
        "tests/",
        ".coverage",
        ".coverage.*",
        "coverage.xml",
        "htmlcov/",
        "*.egg-info/",
        "build/",
        "dist/",
        ".venv/",
        "__pycache__/",
    ],
)
def test_dockerignore_excludes_local_artifacts(pattern: str) -> None:
    assert pattern in _dockerignore_patterns()


def test_both_healthchecks_are_present_and_identical() -> None:
    snippets = _healthcheck_snippets()
    assert len(snippets) == 2
    assert snippets[0] == snippets[1]


@pytest.mark.parametrize("snippet", _healthcheck_snippets())
def test_healthcheck_fails_on_missing_db_without_creating_it(snippet: str, tmp_path: Path) -> None:
    db = tmp_path / "data" / "bot.db"
    db.parent.mkdir()
    proc = subprocess.run(  # noqa: S603 — fixed interpreter, snippet comes from the repo
        [sys.executable, "-c", snippet],
        env={"DATABASE_PATH": str(db)},
        capture_output=True,
        check=False,
    )
    assert proc.returncode != 0
    assert not db.exists()


@pytest.mark.parametrize("snippet", _healthcheck_snippets())
def test_healthcheck_passes_on_existing_db(snippet: str, tmp_path: Path) -> None:
    import sqlite3

    db = tmp_path / "bot.db"
    sqlite3.connect(db).close()
    proc = subprocess.run(  # noqa: S603 — fixed interpreter, snippet comes from the repo
        [sys.executable, "-c", snippet],
        env={"DATABASE_PATH": str(db)},
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
