"""Tests for trackers.sda — SDA scraper."""

from __future__ import annotations

from pathlib import Path

import pytest
import respx

from parcel_tracker.trackers.sda import SdaTracker


def test_detects_sda_patterns() -> None:
    t = SdaTracker()
    assert t.detect("123456789012") is True  # 12-digit
    assert t.detect("1234567890123") is True  # 13-digit
    assert t.detect("AA12345678") is True  # letter-prefix variant
    assert t.detect("XYZ") is False
    assert t.detect("123") is False


@pytest.mark.asyncio
async def test_fetch_no_results(fixtures_dir: Path) -> None:
    t = SdaTracker()
    async with respx.mock(base_url="https://www.sda.it") as mock:
        mock.get(url__regex=r".*").respond(200, text="<html></html>")
        result = await t.fetch("123456789012")
    assert result.found is False
    assert result.carrier_name == "SDA"
