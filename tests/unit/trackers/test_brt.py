"""Tests for trackers.brt — BRT (Bartolini) scraper."""

from __future__ import annotations

from pathlib import Path

import pytest
import respx

from parcel_tracker.trackers.brt import BrtTracker


def test_detects_brt_patterns() -> None:
    t = BrtTracker()
    assert t.detect("123456789012") is True  # 12-digit
    assert t.detect("12345678901234") is True  # 14-digit
    assert t.detect("1234567890123456789") is True  # 19-digit
    assert t.detect("BRT123456789") is True  # BRT prefix
    assert t.detect("XYZ") is False


@pytest.mark.asyncio
async def test_fetch_no_results(fixtures_dir: Path) -> None:
    t = BrtTracker()
    async with respx.mock(base_url="https://vas.brt.it") as mock:
        mock.get(url__regex=r".*").respond(200, text="<html></html>")
        result = await t.fetch("123456789012")
    assert result.found is False
    assert result.carrier_name == "BRT"
