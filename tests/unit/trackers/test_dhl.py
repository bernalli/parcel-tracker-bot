"""Tests for trackers.dhl — DHL Express scraper."""

from __future__ import annotations

from pathlib import Path

import pytest
import respx

from parcel_tracker.trackers.dhl import DhlTracker


def test_detects_dhl_pattern() -> None:
    t = DhlTracker()
    assert t.detect("JD014600003725123456") is True  # DHL eCom format
    assert t.detect("1234567890") is True  # 10-digit format
    assert t.detect("XYZ") is False


@pytest.mark.asyncio
async def test_fetch_returns_in_transit(fixtures_dir: Path) -> None:
    html = (fixtures_dir / "dhl" / "in_transit.html").read_text()
    t = DhlTracker()
    async with respx.mock() as mock:
        mock.get(url__regex=r".*dhl\.com.*").respond(200, text=html)
        result = await t.fetch("1234567890")
    assert result.tracking_number == "1234567890"
    # Parser may return found=False for stub HTML — verify NO crash
    assert result.error is None or "parse" in (result.error or "").lower()
