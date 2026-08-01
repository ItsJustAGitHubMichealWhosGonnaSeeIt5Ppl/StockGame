"""Tests for resilient S&P 500 constituent parsing / seeding."""

from __future__ import annotations

from unittest.mock import MagicMock

from helpers.sp500 import (
    CSV_FALLBACK_URL,
    WIKI_URL,
    Sp500Constituent,
    _parse_constituents_csv,
    _parse_wikipedia_html,
    ensure_sp500_seeded,
    get_sp500_constituents,
)


WIKI_WITH_ID = """
<html><body>
<table id="constituents" class="wikitable">
<tr><th>Symbol</th><th>Security</th></tr>
<tr><td>AAPL</td><td>Apple Inc.</td></tr>
<tr><td>BRK.B</td><td>Berkshire Hathaway</td></tr>
<tr><td>MSFT</td><td>Microsoft</td></tr>
</table>
</body></html>
"""

WIKI_NO_ID = """
<html><body>
<table class="wikitable sortable">
<tr><th>Ticker</th><th>Company</th></tr>
<tr><td>AAPL</td><td>Apple Inc.</td></tr>
<tr><td>MSFT</td><td>Microsoft</td></tr>
<tr><td>GOOGL</td><td>Alphabet</td></tr>
</table>
</body></html>
"""

WIKI_MULTIPLE = """
<html><body>
<table class="wikitable"><tr><th>Foo</th></tr><tr><td>Bar</td></tr></table>
<table class="wikitable">
<tr><th>Symbol</th><th>Security</th></tr>
<tr><td>XOM</td><td>Exxon</td></tr>
<tr><td>CVX</td><td>Chevron</td></tr>
</table>
</body></html>
"""

CSV_SAMPLE = """Symbol,Security,GICS Sector
AAPL,Apple Inc.,Information Technology
BRK.B,Berkshire Hathaway,Financials
MSFT,Microsoft,Information Technology
"""


def _fake_symbols(count: int) -> list[str]:
    symbols: list[str] = []
    for i in range(count):
        n = i
        sym = ""
        for _ in range(3):
            sym = chr(ord("A") + (n % 26)) + sym
            n //= 26
        symbols.append(sym)
    return symbols


def test_parse_wikipedia_with_constituents_id():
    parsed = _parse_wikipedia_html(WIKI_WITH_ID)
    tickers = [c.ticker for c in parsed]
    assert tickers == ["AAPL", "BRK-B", "MSFT"]
    assert parsed[1].company_name == "Berkshire Hathaway"


def test_parse_wikipedia_without_id_uses_header():
    parsed = _parse_wikipedia_html(WIKI_NO_ID)
    assert [c.ticker for c in parsed] == ["AAPL", "MSFT", "GOOGL"]


def test_parse_wikipedia_picks_best_table_among_many():
    parsed = _parse_wikipedia_html(WIKI_MULTIPLE)
    assert [c.ticker for c in parsed] == ["XOM", "CVX"]


def test_parse_csv_fallback_normalizes_class_shares():
    parsed = _parse_constituents_csv(CSV_SAMPLE)
    assert [c.ticker for c in parsed] == ["AAPL", "BRK-B", "MSFT"]


def test_get_sp500_falls_back_to_csv_when_html_empty():
    symbols = _fake_symbols(450)

    def fake_get(url: str) -> str:
        if url == WIKI_URL:
            return "<html><body><p>No tables here</p></body></html>"
        if url == CSV_FALLBACK_URL:
            rows = ["Symbol,Security"] + [f"{sym},Company {i}" for i, sym in enumerate(symbols)]
            return "\n".join(rows)
        raise AssertionError(url)

    constituents = get_sp500_constituents(session_get=fake_get)
    assert len(constituents) == 450


def test_get_sp500_uses_wikipedia_when_valid():
    symbols = _fake_symbols(450)
    rows = ["<tr><th>Symbol</th><th>Security</th></tr>"]
    rows.extend(f"<tr><td>{sym}</td><td>Co {i}</td></tr>" for i, sym in enumerate(symbols))
    html = (
        '<html><body><table id="constituents" class="wikitable">'
        + "".join(rows)
        + "</table></body></html>"
    )

    def fake_get(url: str) -> str:
        assert url == WIKI_URL
        return html

    constituents = get_sp500_constituents(session_get=fake_get)
    assert len(constituents) == 450


def test_ensure_sp500_seeded_skips_existing_and_adds_missing():
    be = MagicMock()
    be.get_many_stocks.return_value = ("AAPL",)
    alpaca = MagicMock()
    alpaca.configured = True
    alpaca.get_latest_prices.return_value = {"MSFT": 100.0, "GOOGL": 50.0}

    import helpers.sp500 as sp500

    monkey_list = [
        Sp500Constituent("AAPL", "Apple"),
        Sp500Constituent("MSFT", "Microsoft"),
        Sp500Constituent("GOOGL", "Alphabet"),
    ]
    original = sp500.get_sp500_constituents
    sp500.get_sp500_constituents = lambda **_: monkey_list
    try:
        stats = ensure_sp500_seeded(be, alpaca)
    finally:
        sp500.get_sp500_constituents = original

    assert stats["listed"] == 3
    assert stats["existing"] == 1
    assert stats["added"] == 2
    assert stats["priced"] == 2
    assert be.add_stock.call_count == 2


def test_ensure_sp500_seeded_handles_empty_stocks_table():
    be = MagicMock()
    be.get_many_stocks.side_effect = LookupError("No items found")
    alpaca = MagicMock()
    alpaca.configured = True
    alpaca.get_latest_prices.return_value = {"AAPL": 1.0, "MSFT": 2.0}

    import helpers.sp500 as sp500

    monkey_list = [
        Sp500Constituent("AAPL", "Apple"),
        Sp500Constituent("MSFT", "Microsoft"),
    ]
    original = sp500.get_sp500_constituents
    sp500.get_sp500_constituents = lambda **_: monkey_list
    try:
        stats = ensure_sp500_seeded(be, alpaca)
    finally:
        sp500.get_sp500_constituents = original

    assert stats["existing"] == 0
    assert stats["added"] == 2
    assert stats["priced"] == 2
