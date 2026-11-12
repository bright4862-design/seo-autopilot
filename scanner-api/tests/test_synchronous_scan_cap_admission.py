"""Only the entitlement-owned staged path may admit Standard 500 scans."""
import pytest
from fastapi import HTTPException

from app import main
from tests import fixtures as fx


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["standard_500", "STANDARD_500"])
async def test_synchronous_500_is_rejected_before_any_network_work(mode, mock_network, monkeypatch):
    origin = "https://synchronous-cap.example"
    requests = mock_network({origin + "/": fx._html(fx._page("Home"))})
    monkeypatch.setattr(main, "SCANNER_API_KEY", "test-key")

    with pytest.raises(HTTPException) as error:
        await main.scan(main.ScanRequest(website_url=origin + "/", scan_mode=mode), x_scanner_key="test-key")

    assert error.value.status_code == 400
    assert requests == []


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["advanced", "standard_150"])
async def test_synchronous_150_modes_still_scan_fixture_pages(mode, mock_network, monkeypatch):
    origin = "https://synchronous-standard.example"
    mock_network({origin + "/": fx._html(fx._page("Home"))})
    monkeypatch.setattr(main, "SCANNER_API_KEY", "test-key")

    result = await main.scan(main.ScanRequest(website_url=origin + "/", scan_mode=mode), x_scanner_key="test-key")

    assert result["success"] is True
    assert result["pages_crawled"] == 1
    assert len(result["pages"]) == 1
