"""
Standalone Alpaca smoke test: fetch S&P 500 tickers and poll latest prices.

Does not touch the database or other project modules.
Requires ALPACA_API_KEY and ALPACA_SECRET_KEY in .env

Usage:
  python scripts/test_alpaca_prices.py
"""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Market data lives on data.alpaca.markets — NOT paper-api.alpaca.markets
DATA_BASE = "https://data.alpaca.markets/v2"
BATCH_SIZE = 100          # symbols per request
SLEEP_BETWEEN_BATCHES = 0.35  # stay well under 200 req/min
PRINT_EVERY_N = 25        # print a price line every N symbols (reduces spam)


def load_credentials() -> tuple[str, str]:
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_dotenv(os.path.join(project_root, ".env"))

    key = os.getenv("ALPACA_API_KEY", "").strip()
    secret = os.getenv("ALPACA_SECRET_KEY", "").strip()
    if not key or not secret:
        print(
            "Missing ALPACA_API_KEY / ALPACA_SECRET_KEY in .env\n"
            "Add them, then re-run this script."
        )
        sys.exit(1)
    return key, secret


def get_sp500_tickers() -> list[str]:
    """Pull current S&P 500 symbols from Wikipedia (Alpaca keeps dots, e.g. BRK.B)."""
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    response = requests.get(url, timeout=30, headers={"User-Agent": "StockGame-alpaca-test/1.0"})
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    table = soup.find("table", {"id": "constituents"})
    if table is None:
        raise ValueError("Could not find S&P 500 constituents table on Wikipedia.")

    tickers: list[str] = []
    for row in table.find_all("tr")[1:]:
        cells = row.find_all("td")
        if not cells:
            continue
        symbol = cells[0].get_text(strip=True)
        if symbol:
            tickers.append(symbol)
    if not tickers:
        raise ValueError("Parsed zero S&P 500 tickers from Wikipedia.")
    return tickers


def fetch_snapshots(session: requests.Session, symbols: list[str]) -> dict:
    params = {"symbols": ",".join(symbols), "feed": "iex"}
    r = session.get(f"{DATA_BASE}/stocks/snapshots", params=params, timeout=30)
    if r.status_code == 429:
        retry = float(r.headers.get("Retry-After", "5"))
        print(f"  rate limited — sleeping {retry:.0f}s")
        time.sleep(retry)
        r = session.get(f"{DATA_BASE}/stocks/snapshots", params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def price_from_snapshot(snap: dict) -> float | None:
    trade = snap.get("latestTrade") or {}
    if trade.get("p") is not None:
        return float(trade["p"])
    quote = snap.get("latestQuote") or {}
    ap, bp = quote.get("ap"), quote.get("bp")
    if ap is not None and bp is not None and ap > 0 and bp > 0:
        return (float(ap) + float(bp)) / 2
    if ap is not None and ap > 0:
        return float(ap)
    if bp is not None and bp > 0:
        return float(bp)
    bar = snap.get("dailyBar") or snap.get("prevDailyBar") or {}
    if bar.get("c") is not None:
        return float(bar["c"])
    return None


def main() -> None:
    key, secret = load_credentials()
    print("Fetching S&P 500 ticker list from Wikipedia...")
    tickers = get_sp500_tickers()
    print(f"Got {len(tickers)} tickers. Polling Alpaca IEX snapshots (Ctrl+C to stop).\n")
    print("Note: paper-api.alpaca.markets is trading only;")
    print("      market data uses https://data.alpaca.markets/v2\n")

    session = requests.Session()
    session.headers.update(
        {
            "APCA-API-KEY-ID": key,
            "APCA-API-SECRET-KEY": secret,
            "Accept": "application/json",
        }
    )

    # Quick auth/data sanity check
    probe = fetch_snapshots(session, ["AAPL", "MSFT", "SPY"])
    if not probe:
        print("Empty response from Alpaca — check keys / plan.")
        sys.exit(1)
    print("Auth OK. Sample:")
    for sym, snap in probe.items():
        p = price_from_snapshot(snap)
        print(f"  {sym:6}  {p if p is not None else 'n/a'}")
    print()

    prices: dict[str, float] = {}
    cycle = 0

    while True:
        cycle += 1
        started = time.perf_counter()
        updated = 0
        missing = 0
        stamp = datetime.now(timezone.utc).strftime("%H:%M:%S")

        for i in range(0, len(tickers), BATCH_SIZE):
            batch = tickers[i : i + BATCH_SIZE]
            try:
                data = fetch_snapshots(session, batch)
            except requests.HTTPError as e:
                print(f"[{stamp}] HTTP error on batch {i // BATCH_SIZE + 1}: {e}")
                time.sleep(2)
                continue

            for sym in batch:
                snap = data.get(sym)
                if not snap:
                    missing += 1
                    continue
                price = price_from_snapshot(snap)
                if price is None:
                    missing += 1
                    continue

                prev = prices.get(sym)
                prices[sym] = price
                updated += 1

                # Print changes, plus a sparse sample of unchanged prices
                if prev is None or prev != price:
                    delta = "" if prev is None else f"  ({price - prev:+.2f})"
                    print(f"[{stamp}] {sym:6}  ${price:,.2f}{delta}")
                elif updated % PRINT_EVERY_N == 0:
                    print(f"[{stamp}] {sym:6}  ${price:,.2f}")

            time.sleep(SLEEP_BETWEEN_BATCHES)

        elapsed = time.perf_counter() - started
        print(
            f"--- cycle {cycle} done in {elapsed:.1f}s | "
            f"{updated} priced, {missing} missing, {len(prices)} tracked ---\n"
        )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
