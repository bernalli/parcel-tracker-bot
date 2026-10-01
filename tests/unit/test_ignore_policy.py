"""Policy checks on the ignore rules (.gitignore, .dockerignore).

gitleaks scans what gets committed; these tests make sure secrets, env files and
local data never reach `git add` or the Docker build context in the first place.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

# Paths that must never be committed nor sent to the Docker daemon. Nested
# variants matter: a stray `.env` or database under src/ is still a leak.
SENSITIVE_PATHS = [
    # env files
    ".env",
    ".env.local",
    ".env.production",
    ".envrc",
    "src/parcel_tracker/.env",
    "src/parcel_tracker/.env.local",
    # local databases and dumps (chat ids + tracking numbers are personal data)
    "bot.db",
    "bot.db-wal",
    "bot.sqlite",
    "bot.sqlite3",
    "data/bot.db",
    "src/parcel_tracker/bot.db",
    "src/parcel_tracker/cache.sqlite3",
    "backup.sql",
    "bot.dump",
    # keys and credentials
    "server.pem",
    "server.key",
    "client.p12",
    "client.pfx",
    "id_rsa",
    "id_ed25519",
    ".netrc",
    ".pypirc",
    "secrets/telegram_token",
    "src/parcel_tracker/server.key",
    # local overrides and logs
    "docker-compose.override.yml",
    "docker-compose.override.yaml",
    "logs/bot.log",
]


def _git(*args: str, stdin: str | None = None) -> str:
    git = shutil.which("git")
    assert git is not None
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        [git, *args], cwd=ROOT, input=stdin, capture_output=True, text=True, check=True
    ).stdout


def _in_git_checkout() -> bool:
    return shutil.which("git") is not None and (ROOT / ".git").exists()


requires_git = pytest.mark.skipif(not _in_git_checkout(), reason="needs a git checkout")


def _git_ignored(paths: list[str]) -> dict[str, bool]:
    """Ask git itself whether each path would be ignored (tracked or not)."""
    out = _git(
        "check-ignore",
        "--no-index",
        "--verbose",
        "--non-matching",
        "--stdin",
        stdin="\n".join(paths) + "\n",
    )
    result: dict[str, bool] = {}
    for line in out.splitlines():
        source, path = line.split("\t", 1)
        pattern = source.split(":", 2)[2]
        result[path] = bool(pattern) and not pattern.startswith("!")
    return result


def _docker_pattern_regex(pattern: str) -> re.Pattern[str]:
    """Translate a .dockerignore pattern the way moby/patternmatcher reads it.

    Patterns are anchored at the context root, `*` stays within one path segment
    and `**` spans any number of segments (including none).
    """
    pattern = pattern.strip("/")
    out = ""
    i = 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out += "(?:.*/)?"
            i += 3
        elif pattern.startswith("**", i):
            out += ".*"
            i += 2
        elif pattern[i] == "*":
            out += "[^/]*"
            i += 1
        elif pattern[i] == "?":
            out += "[^/]"
            i += 1
        else:
            out += re.escape(pattern[i])
            i += 1
    return re.compile(out)


def _docker_excluded(path: str) -> bool:
    """True if `path` is left out of the build context (last matching rule wins)."""
    lines = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
    rules = [ln.strip() for ln in lines if ln.strip() and not ln.lstrip().startswith("#")]
    parts = path.split("/")
    candidates = ["/".join(parts[: i + 1]) for i in range(len(parts))]
    excluded = False
    for rule in rules:
        negated = rule.startswith("!")
        regex = _docker_pattern_regex(rule.lstrip("!"))
        if any(regex.fullmatch(c) for c in candidates):
            excluded = not negated
    return excluded


@requires_git
def test_gitignore_covers_sensitive_paths() -> None:
    ignored = _git_ignored(SENSITIVE_PATHS)
    assert [p for p in SENSITIVE_PATHS if not ignored[p]] == []


@requires_git
def test_gitignore_keeps_the_env_template() -> None:
    assert _git_ignored([".env.example"]) == {".env.example": False}


@requires_git
def test_no_tracked_file_matches_an_ignore_rule() -> None:
    # A tracked file that an ignore rule matches means the rule is too broad
    # (or the file slipped in before the rule existed).
    assert _git("ls-files", "--cached", "--ignored", "--exclude-standard").split() == []


def test_dockerignore_covers_sensitive_paths() -> None:
    assert [p for p in SENSITIVE_PATHS if not _docker_excluded(p)] == []


@requires_git
def test_dockerignore_keeps_build_inputs() -> None:
    # The Dockerfile copies pyproject.toml, README.md and src/ (map data included).
    inputs = ["pyproject.toml", "README.md", *_git("ls-files", "src").split()]
    assert [p for p in inputs if _docker_excluded(p)] == []
