# Script to pull all stocks of the S&P 500 and preload them into the database (Alpaca).
import os
import sys

from dotenv import load_dotenv
import requests
from bs4 import BeautifulSoup

current_script_dir = os.path.dirname(os.path.abspath(__file__))
project_root_dir = os.path.dirname(current_script_dir)
sys.path.append(project_root_dir)

from helpers.alpaca_client import AlpacaMarketData, to_db_ticker
from helpers.sqlhelper import _iso8601
from stocks import Backend


def get_sp500_tickers() -> list[str]:
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    response = requests.get(url, timeout=30, headers={"User-Agent": "StockGame-first500/1.0"})
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    table = soup.find("table", {"id": "constituents"})
    if table is None:
        raise ValueError("Could not find the S&P 500 constituents table on the Wikipedia page.")

    tickers: list[str] = []
    for row in table.find_all("tr")[1:]:
        cells = row.find_all("td")
        if not cells:
            continue
        symbol = cells[0].get_text(strip=True)
        if symbol:
            tickers.append(to_db_ticker(symbol))
    if not tickers:
        raise ValueError("Parsed zero S&P 500 tickers from Wikipedia.")
    return tickers


def insert_into_db(tickers: list[str], be: Backend, alpaca: AlpacaMarketData) -> None:
    prices = alpaca.get_latest_prices(tickers)
    price_dt = _iso8601()

    for ticker in tickers:
        try:
            asset = alpaca.get_us_equity(ticker)
            be.add_stock(
                ticker=ticker,
                exchange=str(asset.get("exchange") or "UNKNOWN"),
                company_name=str(asset.get("name") or ticker),
            )
            if ticker in prices:
                be.add_stock_price(
                    ticker_or_id=ticker,
                    price=prices[ticker],
                    datetime=price_dt,
                )
            print(f"Successfully added {ticker} to the db")
        except Exception as e:
            print(f"There was an error adding {ticker}: {e}")


if __name__ == "__main__":
    load_dotenv()
    DB_NAME = str(os.getenv("DB_NAME"))
    alpaca = AlpacaMarketData()
    if not alpaca.configured:
        raise SystemExit("Set ALPACA_API_KEY and ALPACA_SECRET_KEY in .env before running.")

    be = Backend(db_name=DB_NAME)
    ticker_list = get_sp500_tickers()
    insert_into_db(tickers=ticker_list, be=be, alpaca=alpaca)
