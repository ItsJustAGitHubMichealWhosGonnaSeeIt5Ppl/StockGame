"""Alpaca market-data helpers (stocks only — no crypto)."""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Optional
from urllib.parse import quote

import requests

logger = logging.getLogger("AlpacaMarketData")

DATA_BASE = "https://data.alpaca.markets/v2"
DEFAULT_TRADING_BASE = "https://paper-api.alpaca.markets"
BATCH_SIZE = 100
SLEEP_BETWEEN_BATCHES = 0.35  # ~170 req/min max, under free-tier 200/min


def to_alpaca_symbol(ticker: str) -> str:
    """Map DB tickers (BRK-B) to Alpaca symbols (BRK.B)."""
    return ticker.strip().upper().replace("-", ".")


def to_db_ticker(ticker: str) -> str:
    """Normalize a ticker for DB storage (Alpaca BRK.B → BRK-B)."""
    return ticker.strip().upper().replace(".", "-")


def price_from_snapshot(snap: dict[str, Any]) -> Optional[float]:
    trade = snap.get("latestTrade") or {}
    if trade.get("p") is not None:
        return float(trade["p"])
    quote = snap.get("latestQuote") or {}
    ap, bp = quote.get("ap"), quote.get("bp")
    if ap is not None and bp is not None and float(ap) > 0 and float(bp) > 0:
        return (float(ap) + float(bp)) / 2
    if ap is not None and float(ap) > 0:
        return float(ap)
    if bp is not None and float(bp) > 0:
        return float(bp)
    bar = snap.get("dailyBar") or snap.get("prevDailyBar") or {}
    if bar.get("c") is not None:
        return float(bar["c"])
    return None


class AlpacaMarketData:
    """Synchronous Alpaca client for equity assets, snapshots, and market clock."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        trading_base: Optional[str] = None,
    ):
        self.api_key = (api_key if api_key is not None else os.getenv("ALPACA_API_KEY", "")).strip()
        self.secret_key = (
            secret_key if secret_key is not None else os.getenv("ALPACA_SECRET_KEY", "")
        ).strip()
        base = (
            trading_base
            if trading_base is not None
            else os.getenv("ALPACA_BASE_URL", DEFAULT_TRADING_BASE)
        )
        self.trading_base = (base or DEFAULT_TRADING_BASE).rstrip("/")
        self._session = requests.Session()
        self._session.headers.update(
            {
                "APCA-API-KEY-ID": self.api_key,
                "APCA-API-SECRET-KEY": self.secret_key,
                "Accept": "application/json",
            }
        )
        if not self.configured:
            logger.error(
                "Alpaca credentials missing (ALPACA_API_KEY / ALPACA_SECRET_KEY). "
                "Price updates and stock lookups will fail until configured."
            )
        else:
            logger.debug(
                "Alpaca client configured (trading_base=%s, key_prefix=%s)",
                self.trading_base,
                self.api_key[:4],
            )

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.secret_key)

    def _require_configured(self) -> None:
        if not self.configured:
            logger.critical("Alpaca API call attempted without credentials.")
            raise RuntimeError("Alpaca credentials missing (ALPACA_API_KEY / ALPACA_SECRET_KEY)")

    def _classify_http_error(self, response: requests.Response, context: str) -> None:
        """Log auth / rate-limit failures at CRITICAL; other HTTP errors at ERROR."""
        code = response.status_code
        body = (response.text or "")[:300]
        if code in (401, 403):
            logger.critical(
                "Alpaca auth failure (%s) status=%s body=%s",
                context,
                code,
                body,
            )
        elif code == 429:
            logger.critical(
                "Alpaca rate limit exceeded (%s) status=429 Retry-After=%s body=%s",
                context,
                response.headers.get("Retry-After"),
                body,
            )
        else:
            logger.error(
                "Alpaca HTTP error (%s) status=%s body=%s",
                context,
                code,
                body,
            )

    def _get(self, url: str, params: Optional[dict] = None) -> requests.Response:
        logger.debug("Alpaca GET %s params=%s", url, params)
        try:
            r = self._session.get(url, params=params, timeout=30)
        except requests.Timeout:
            logger.error("Alpaca request timed out: %s", url)
            raise
        except requests.RequestException:
            logger.exception("Alpaca request failed: %s", url)
            raise

        if r.status_code == 429:
            retry = float(r.headers.get("Retry-After", "5"))
            logger.critical(
                "Alpaca rate limited on %s; sleeping %.0fs then retrying once.",
                url,
                retry,
            )
            time.sleep(retry)
            r = self._session.get(url, params=params, timeout=30)
            if r.status_code == 429:
                self._classify_http_error(r, f"retry still limited: {url}")
        return r

    def is_market_open(self) -> Optional[bool]:
        """Return True/False from Alpaca clock, or None if the call fails."""
        if not self.configured:
            logger.debug("Market clock skipped: Alpaca not configured.")
            return None
        try:
            r = self._get(f"{self.trading_base}/v2/clock")
            if not r.ok:
                self._classify_http_error(r, "market clock")
                return None
            is_open = bool(r.json().get("is_open"))
            logger.debug("Alpaca market clock is_open=%s", is_open)
            return is_open
        except Exception:
            logger.exception("Failed to read Alpaca market clock")
            return None

    def get_us_equity(self, ticker: str) -> dict[str, Any]:
        """
        Look up a US equity asset on Alpaca.

        Raises:
            LookupError: Symbol not found.
            ValueError: Not an active tradable US equity (e.g. crypto).
            RuntimeError: Missing credentials.
        """
        self._require_configured()
        symbol = to_alpaca_symbol(ticker)
        r = self._get(f"{self.trading_base}/v2/assets/{quote(symbol, safe='')}")
        if r.status_code == 404:
            logger.info("Alpaca asset not found: input=%s symbol=%s", ticker, symbol)
            raise LookupError(f"Unable to find stock: {ticker}")
        if not r.ok:
            self._classify_http_error(r, f"get_us_equity:{symbol}")
            r.raise_for_status()
        asset = r.json()
        if not isinstance(asset, dict):
            logger.error("Alpaca asset response was not an object for %s: %r", symbol, asset)
            raise LookupError(f"Unable to find stock: {ticker}")

        asset_class = str(asset.get("class") or "")
        if asset_class != "us_equity":
            logger.info(
                "Alpaca asset rejected (not us_equity): %s class=%s",
                symbol,
                asset_class,
            )
            raise ValueError("Stock is not tradeable")
        if asset.get("status") != "active" or not asset.get("tradable"):
            logger.info(
                "Alpaca asset rejected (inactive/untradable): %s status=%s tradable=%s",
                symbol,
                asset.get("status"),
                asset.get("tradable"),
            )
            raise ValueError("Stock is not tradeable")

        logger.debug("Alpaca asset ok: %s exchange=%s", symbol, asset.get("exchange"))
        return asset

    def fetch_snapshots(self, symbols: list[str]) -> dict[str, Any]:
        """Fetch IEX snapshots for a batch of Alpaca symbols."""
        if not symbols:
            return {}
        params = {"symbols": ",".join(symbols), "feed": "iex"}
        r = self._get(f"{DATA_BASE}/stocks/snapshots", params=params)
        if not r.ok:
            self._classify_http_error(r, f"snapshots batch size={len(symbols)}")
            r.raise_for_status()
        data = r.json()
        return data if isinstance(data, dict) else {}

    def get_latest_prices(self, tickers: list[str]) -> dict[str, float]:
        """
        Return {db_ticker: price} for as many symbols as Alpaca provides.

        Respects free-tier limits by batching and sleeping between requests.
        """
        self._require_configured()
        if not tickers:
            logger.debug("get_latest_prices called with empty ticker list.")
            return {}

        # Preserve original DB ticker spelling while querying Alpaca form.
        alpaca_to_db: dict[str, str] = {}
        ordered_alpaca: list[str] = []
        for ticker in tickers:
            alpaca = to_alpaca_symbol(ticker)
            if alpaca in alpaca_to_db:
                continue
            alpaca_to_db[alpaca] = ticker
            ordered_alpaca.append(alpaca)

        prices: dict[str, float] = {}
        failures = 0
        for i in range(0, len(ordered_alpaca), BATCH_SIZE):
            batch = ordered_alpaca[i : i + BATCH_SIZE]
            try:
                data = self.fetch_snapshots(batch)
            except Exception:
                failures += 1
                logger.exception(
                    "Alpaca snapshot batch failed (offset=%s size=%s)",
                    i,
                    len(batch),
                )
                time.sleep(SLEEP_BETWEEN_BATCHES)
                continue

            for alpaca_sym in batch:
                snap = data.get(alpaca_sym)
                if not snap:
                    logger.debug("No snapshot returned for %s", alpaca_sym)
                    continue
                price = price_from_snapshot(snap)
                if price is None:
                    logger.debug("Snapshot for %s had no usable price fields", alpaca_sym)
                    continue
                prices[alpaca_to_db[alpaca_sym]] = price

            if i + BATCH_SIZE < len(ordered_alpaca):
                time.sleep(SLEEP_BETWEEN_BATCHES)

        logger.info(
            "Alpaca prices fetched: %s/%s symbols (%s batch failures)",
            len(prices),
            len(ordered_alpaca),
            failures,
        )
        if failures and not prices:
            logger.critical(
                "Alpaca price fetch produced zero prices after %s batch failure(s). "
                "Check API keys, rate limits, and network.",
                failures,
            )
        return prices
