"""Tests for trackers.gls_italy — GLS Italy scraper."""

from __future__ import annotations

from pathlib import Path

import pytest
import respx

from parcel_tracker.trackers.gls_italy import GlsItalyTracker


def test_detects_gls_italy_patterns() -> None:
    t = GlsItalyTracker()
    assert t.detect("12345678901") is True  # 11-digit
    assert t.detect("123456789012") is True  # 12-digit
    assert t.detect("XYZ") is False
    assert t.detect("123") is False


@pytest.mark.asyncio
async def test_fetch_no_results(fixtures_dir: Path) -> None:
    t = GlsItalyTracker()
    async with respx.mock(base_url="https://www.gls-italy.com") as mock:
        mock.post(url__regex=r".*").respond(200, text="<html></html>")
        result = await t.fetch("12345678901")
    assert result.found is False
    assert result.carrier_name == "GLS Italy"
