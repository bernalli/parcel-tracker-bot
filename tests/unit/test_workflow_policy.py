"""Policy checks on the GitHub Actions workflows."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

WORKFLOWS = sorted((Path(__file__).resolve().parents[2] / ".github" / "workflows").glob("*.yml"))

# Expressions an outside contributor (or a dispatch caller) controls. They must
# reach a shell through `env:`, never be spliced into a `run:` script.
_UNTRUSTED = re.compile(
    r"\$\{\{\s*(inputs\.|github\.event\.|github\.head_ref|github\.ref_name|steps\.[^}]*outputs)"
)


def _run_blocks(text: str) -> list[str]:
    """Return the body of every `run:` step (inline or block scalar)."""
    blocks: list[str] = []
    lines = text.splitlines()
    for i, line in enumerate(lines):
        m = re.match(r"^(\s*)(?:- )?run:\s*(.*)$", line)
        if not m:
            continue
        indent, rest = len(m.group(1)), m.group(2)
        if rest and rest[0] not in "|>":
            blocks.append(rest)
            continue
        body = []
        for nxt in lines[i + 1 :]:
            if nxt.strip() and len(nxt) - len(nxt.lstrip()) <= indent:
                break
            body.append(nxt)
        blocks.append("\n".join(body))
    return blocks


def test_workflows_found() -> None:
    assert len(WORKFLOWS) >= 5


@pytest.mark.parametrize("wf", WORKFLOWS, ids=lambda p: p.name)
def test_actions_pinned_to_commit_sha(wf: Path) -> None:
    for ref in re.findall(r"^\s*(?:- )?uses:\s*(\S+)", wf.read_text(), flags=re.MULTILINE):
        if ref.startswith("./"):
            continue
        assert re.fullmatch(r"[\w.-]+/[\w./-]+@[0-9a-f]{40}", ref), f"{wf.name}: {ref}"


@pytest.mark.parametrize("wf", WORKFLOWS, ids=lambda p: p.name)
def test_top_level_permissions_are_read_only(wf: Path) -> None:
    text = wf.read_text()
    m = re.search(r"^permissions:\s*\n((?:[ ]+.*\n)+)", text, flags=re.MULTILINE)
    assert m, f"{wf.name}: missing top-level permissions block"
    assert "write" not in m.group(1), f"{wf.name}: top-level permissions grant write"


@pytest.mark.parametrize("wf", WORKFLOWS, ids=lambda p: p.name)
def test_no_untrusted_expressions_in_run_scripts(wf: Path) -> None:
    for body in _run_blocks(wf.read_text()):
        assert not _UNTRUSTED.search(body), f"{wf.name}: untrusted expression in run: {body!r}"


@pytest.mark.parametrize("wf", WORKFLOWS, ids=lambda p: p.name)
def test_no_pull_request_target(wf: Path) -> None:
    assert not re.search(r"^\s*pull_request_target\s*:", wf.read_text(), flags=re.MULTILINE)


def test_release_tag_input_is_validated_before_use() -> None:
    text = next(p for p in WORKFLOWS if p.name == "release.yml").read_text()
    validate = text.index("Validate tag")
    assert validate < text.index("actions/checkout")
    assert "RELEASE_TAG: ${{ inputs.tag }}" in text
