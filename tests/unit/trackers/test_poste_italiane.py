"""Tests for trackers.poste_italiane — Poste Italiane scraper."""

from __future__ import annotations

from pathlib import Path

import pytest
import respx

from parcel_tracker.trackers.poste_italiane import PosteItalianeTracker


def test_detects_poste_italiane_patterns() -> None:
    t = PosteItalianeTracker()
    assert t.detect("AA123456789IT") is True  # CC+9digits+IT (international)
    assert t.detect("12345678901234567890123") is True  # 23-digit
    assert t.detect("ABCD123456789") is True  # 13-char alphanumeric
    assert t.detect("XYZ") is False
    assert t.detect("123") is False


@pytest.mark.asyncio
async def test_fetch_no_results(fixtures_dir: Path) -> None:
    t = PosteItalianeTracker()
    async with respx.mock(base_url="https://www.poste.it") as mock:
        mock.get(url__regex=r".*").respond(200, text="<html></html>")
        result = await t.fetch("AA123456789IT")
    assert result.found is False
    assert result.carrier_name == "Poste Italiane"
