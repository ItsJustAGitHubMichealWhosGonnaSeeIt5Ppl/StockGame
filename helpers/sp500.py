"""Fetch S&P 500 constituents and seed them into the local stock DB.

Parsing is intentionally multi-strategy so minor Wikipedia HTML changes do not
break startup. A public CSV mirror is used as a last-resort fallback.
"""

from __future__ import annotations

import csv
import io
import logging
import re
from dataclasses import dataclass
from typing import Any, Optional, Protocol

import requests
from bs4 import BeautifulSoup, Tag

from helpers.alpaca_client import AlpacaMarketData, to_db_ticker
from helpers.sqlhelper import _iso8601

logger = logging.getLogger("Sp500Seed")

WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
# Community mirror maintained independently of Wikipedia markup.
CSV_FALLBACK_URL = (
    "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/master/data/constituents.csv"
)
USER_AGENT = "StockGame-sp500/1.0 (+https://github.com/)"
REQUEST_TIMEOUT = 30
# Index membership fluctuates around ~500; keep a wide acceptance band.
MIN_EXPECTED = 400
MAX_EXPECTED = 600

# AAPL, BRK.B, BRK-B, BF.B, etc.
_TICKER_RE = re.compile(r"^[A-Z]{1,5}(?:[.\-][A-Z]{1,2})?$")


@dataclass(frozen=True)
class Sp500Constituent:
    ticker: str  # DB form (e.g. BRK-B)
    company_name: str


class _BackendLike(Protocol):
    def get_many_stocks(self, *, tickers_only: bool = False) -> Any: ...
    def add_stock(self, ticker: str, exchange: str, company_name: str) -> Any: ...
    def add_stock_price(
        self, ticker_or_id: str | int, price: float, datetime: Optional[str] = None
    ) -> Any: ...


def _normalize_header(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _looks_like_ticker(raw: str) -> bool:
    return bool(_TICKER_RE.match(raw.strip().upper().replace(" ", "")))


def _clean_ticker(raw: str) -> Optional[str]:
    symbol = raw.strip().upper().replace(" ", "")
    if not _looks_like_ticker(symbol):
        return None
    return to_db_ticker(symbol)


def _header_cells(table: Tag) -> list[str]:
    header_row = table.find("tr")
    if header_row is None:
        return []
    cells = header_row.find_all(["th", "td"])
    return [_normalize_header(c.get_text(" ", strip=True)) for c in cells]


def _symbol_and_name_indexes(headers: list[str]) -> tuple[Optional[int], Optional[int]]:
    symbol_idx: Optional[int] = None
    name_idx: Optional[int] = None
    for i, header in enumerate(headers):
        if symbol_idx is None and ("symbol" in header or header in {"ticker", "tickers"}):
            symbol_idx = i
        if name_idx is None and header in {"security", "company", "company name", "name"}:
            name_idx = i
    return symbol_idx, name_idx


def _constituents_from_table(table: Tag) -> list[Sp500Constituent]:
    headers = _header_cells(table)
    symbol_idx, name_idx = _symbol_and_name_indexes(headers)
    if symbol_idx is None:
        # Historical layout: first data column is the symbol.
        symbol_idx = 0
        name_idx = 1 if len(headers) > 1 else None

    found: list[Sp500Constituent] = []
    seen: set[str] = set()
    rows = table.find_all("tr")
    # First row is almost always headers (th) or a non-ticker label row.
    start = 1 if rows else 0

    for row in rows[start:]:
        cells = row.find_all("td")
        if not cells or symbol_idx >= len(cells):
            continue
        ticker = _clean_ticker(cells[symbol_idx].get_text(" ", strip=True))
        if ticker is None or ticker in seen:
            continue
        if name_idx is not None and name_idx < len(cells):
            company = cells[name_idx].get_text(" ", strip=True) or ticker
        else:
            company = ticker
        seen.add(ticker)
        found.append(Sp500Constituent(ticker=ticker, company_name=company))
    return found


def _parse_wikipedia_html(html: str) -> list[Sp500Constituent]:
    soup = BeautifulSoup(html, "html.parser")
    candidates: list[Tag] = []

    by_id = soup.find("table", id="constituents")
    if isinstance(by_id, Tag):
        candidates.append(by_id)

    for table in soup.find_all("table"):
        if not isinstance(table, Tag) or table in candidates:
            continue
        classes = table.get("class") or []
        class_text = " ".join(classes) if isinstance(classes, list) else str(classes)
        headers = _header_cells(table)
        symbol_idx, _ = _symbol_and_name_indexes(headers)
        if symbol_idx is not None or "wikitable" in class_text:
            candidates.append(table)

    best: list[Sp500Constituent] = []
    for table in candidates:
        parsed = _constituents_from_table(table)
        if len(parsed) > len(best):
            best = parsed
    return best


def _parse_constituents_csv(text: str) -> list[Sp500Constituent]:
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return []

    field_map = {_normalize_header(name): name for name in reader.fieldnames if name}
    symbol_key = next(
        (field_map[k] for k in ("symbol", "ticker", "tickers") if k in field_map),
        None,
    )
    name_key = next(
        (
            field_map[k]
            for k in ("security", "company", "company name", "name")
            if k in field_map
        ),
        None,
    )
    if symbol_key is None:
        return []

    found: list[Sp500Constituent] = []
    seen: set[str] = set()
    for row in reader:
        ticker = _clean_ticker(str(row.get(symbol_key) or ""))
        if ticker is None or ticker in seen:
            continue
        company = str(row.get(name_key) or ticker).strip() if name_key else ticker
        seen.add(ticker)
        found.append(Sp500Constituent(ticker=ticker, company_name=company or ticker))
    return found


def _validate_count(constituents: list[Sp500Constituent], source: str) -> list[Sp500Constituent]:
    count = len(constituents)
    if count < MIN_EXPECTED or count > MAX_EXPECTED:
        raise ValueError(
            f"{source} returned {count} tickers; expected between {MIN_EXPECTED} and {MAX_EXPECTED}."
        )
    return constituents


def _http_get(url: str) -> str:
    response = requests.get(
        url,
        timeout=REQUEST_TIMEOUT,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,text/csv,*/*"},
    )
    response.raise_for_status()
    return response.text


def get_sp500_constituents(*, session_get=_http_get) -> list[Sp500Constituent]:
    """
    Return current S&P 500 constituents.

    Tries Wikipedia HTML with several table-discovery strategies, then falls
    back to a public CSV mirror if markup changes break HTML parsing.
    """
    errors: list[str] = []

    try:
        html = session_get(WIKI_URL)
        parsed = _parse_wikipedia_html(html)
        if parsed:
            return _validate_count(parsed, "Wikipedia HTML")
        errors.append("Wikipedia HTML parsed zero valid tickers")
    except Exception as exc:
        errors.append(f"Wikipedia HTML failed: {exc}")
        logger.warning("Wikipedia S&P 500 fetch/parse failed: %s", exc)

    try:
        csv_text = session_get(CSV_FALLBACK_URL)
        parsed = _parse_constituents_csv(csv_text)
        if parsed:
            logger.warning(
                "Using CSV fallback for S&P 500 list after Wikipedia parse issues: %s",
                "; ".join(errors) or "unknown",
            )
            return _validate_count(parsed, "CSV fallback")
        errors.append("CSV fallback parsed zero valid tickers")
    except Exception as exc:
        errors.append(f"CSV fallback failed: {exc}")
        logger.warning("S&P 500 CSV fallback failed: %s", exc)

    raise RuntimeError(
        "Unable to load S&P 500 constituents from Wikipedia or CSV fallback. "
        + " | ".join(errors)
    )


def get_sp500_tickers(*, session_get=_http_get) -> list[str]:
    """Compatibility helper: ticker symbols only (DB form)."""
    return [c.ticker for c in get_sp500_constituents(session_get=session_get)]


def ensure_sp500_seeded(
    be: _BackendLike,
    alpaca: Optional[AlpacaMarketData] = None,
    *,
    log: Optional[logging.Logger] = None,
) -> dict[str, int]:
    """
    Ensure S&P 500 tickers exist in the DB. Idempotent: skips stocks already present.

    Returns counts: listed, existing, added, priced, failed.
    """
    log = log or logger
    alpaca = alpaca or AlpacaMarketData()
    if not alpaca.configured:
        raise RuntimeError("Alpaca is not configured (ALPACA_API_KEY / ALPACA_SECRET_KEY).")

    constituents = get_sp500_constituents()
    existing_raw = be.get_many_stocks(tickers_only=True)
    existing = {to_db_ticker(str(t)) for t in existing_raw}
    missing = [c for c in constituents if c.ticker not in existing]

    stats = {
        "listed": len(constituents),
        "existing": len(constituents) - len(missing),
        "added": 0,
        "priced": 0,
        "failed": 0,
    }
    if not missing:
        log.info(
            "S&P 500 seed: nothing to add (%s/%s already present)",
            stats["existing"],
            stats["listed"],
        )
        return stats

    log.info(
        "S&P 500 seed: adding %s missing ticker(s) (%s already present of %s listed)",
        len(missing),
        stats["existing"],
        stats["listed"],
    )
    prices = alpaca.get_latest_prices([c.ticker for c in missing])
    price_dt = _iso8601()

    for constituent in missing:
        try:
            be.add_stock(
                ticker=constituent.ticker,
                exchange="UNKNOWN",
                company_name=constituent.company_name or constituent.ticker,
            )
            stats["added"] += 1
            price = prices.get(constituent.ticker)
            if price is not None:
                be.add_stock_price(
                    ticker_or_id=constituent.ticker,
                    price=price,
                    datetime=price_dt,
                )
                stats["priced"] += 1
        except ValueError as exc:
            # Race / already inserted — treat as success for idempotency.
            if "already exists" in str(exc).lower():
                stats["existing"] += 1
            else:
                stats["failed"] += 1
                log.warning("Failed to seed %s: %s", constituent.ticker, exc)
        except Exception as exc:
            stats["failed"] += 1
            log.warning("Failed to seed %s: %s", constituent.ticker, exc)

    log.info(
        "S&P 500 seed complete: listed=%s existing=%s added=%s priced=%s failed=%s",
        stats["listed"],
        stats["existing"],
        stats["added"],
        stats["priced"],
        stats["failed"],
    )
    return stats
