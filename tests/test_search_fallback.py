"""Serper primary + SerpApi fallback in EvidenceCoordinator."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.core.coordinator import EvidenceCoordinator, _normalize_serpapi_organic


def test_normalize_serpapi_organic_maps_rows():
    raw = [{"title": "A", "link": "https://a.example", "snippet": "x"}, {"title": "skip"}]
    assert _normalize_serpapi_organic(raw) == [{"title": "A", "link": "https://a.example", "snippet": "x"}]


@pytest.mark.asyncio
async def test_serpapi_only_when_no_serper_key():
    c = EvidenceCoordinator("", serpapi_api_key="k")
    mock_get = AsyncMock(
        return_value=MagicMock(
            status_code=200,
            json=lambda: {"organic_results": [{"title": "T", "link": "https://x.example", "snippet": "S"}]},
        )
    )
    with patch.object(c.client, "post", new_callable=AsyncMock) as post_m:
        with patch.object(c.client, "get", mock_get):
            rows = await c.search("q", num=3)
    post_m.assert_not_called()
    mock_get.assert_called_once()
    assert rows == [{"title": "T", "link": "https://x.example", "snippet": "S"}]
    await c.close()


@pytest.mark.asyncio
async def test_serpapi_fallback_after_serper_http_error():
    c = EvidenceCoordinator("bad-serper", serpapi_api_key="good-serpapi")
    bad = MagicMock(status_code=400)
    ok_serpapi = MagicMock(
        status_code=200,
        json=lambda: {"organic_results": [{"title": "T", "link": "https://z.example", "snippet": ""}]},
    )
    with patch.object(c.client, "post", new_callable=AsyncMock, return_value=bad):
        with patch.object(c.client, "get", new_callable=AsyncMock, return_value=ok_serpapi) as get_m:
            rows = await c.search("query here", num=5)
    get_m.assert_called_once()
    assert rows == [{"title": "T", "link": "https://z.example", "snippet": ""}]
    await c.close()
