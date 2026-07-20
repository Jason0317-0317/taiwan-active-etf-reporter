from bs4 import BeautifulSoup

from reporter import FALLBACK_TICKERS, Holding, diff, discover_active_etfs, parse_holdings


def test_discover_active_etfs():
    soup = BeautifulSoup('<select><option value="00981A">00981A · 主動統一</option><option value="0050">0050</option></select>', "html.parser")
    assert discover_active_etfs(soup) == {"00981A": "主動統一"}


def test_discovery_falls_back_when_landing_page_is_empty():
    soup = BeautifulSoup("<html></html>", "html.parser")
    assert tuple(discover_active_etfs(soup)) == FALLBACK_TICKERS


def test_parse_and_diff():
    soup = BeautifulSoup('<table><tr><th>代號</th><th>名稱</th><th>股數</th><th>權重(%)</th><th>市值(億)</th></tr><tr><td>2330</td><td>台積電</td><td>1,200</td><td>10.50</td><td>12.3</td></tr></table>', "html.parser")
    current = parse_holdings(soup)
    assert current == [Holding("2330", "台積電", 1200, 10.5, 12.3)]
    changes = diff([Holding("2330", "台積電", 1000, 9.0)], current)
    assert changes[0]["kind"] == "增持"
