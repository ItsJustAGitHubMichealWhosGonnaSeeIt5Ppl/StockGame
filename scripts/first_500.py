"""Pull S&P 500 constituents and preload them into the database (Alpaca).

Prefer importing ``helpers.sp500.ensure_sp500_seeded`` from the bot. This script
is the CLI entry point for manual runs.
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv

current_script_dir = os.path.dirname(os.path.abspath(__file__))
project_root_dir = os.path.dirname(current_script_dir)
if project_root_dir not in sys.path:
    sys.path.insert(0, project_root_dir)

from helpers.alpaca_client import AlpacaMarketData
from helpers.sp500 import ensure_sp500_seeded
from stocks import Backend


def insert_into_db(tickers: list[str], be: Backend, alpaca: AlpacaMarketData) -> None:
    """Legacy helper: seed whatever is missing from the full S&P list.

    ``tickers`` is accepted for backward compatibility but the canonical list is
    always re-fetched so company names stay available.
    """
    _ = tickers
    ensure_sp500_seeded(be, alpaca)


if __name__ == "__main__":
    load_dotenv()
    db_name = os.getenv("DB_NAME")
    if not db_name:
        raise SystemExit("Set DB_NAME in .env before running.")

    alpaca = AlpacaMarketData()
    if not alpaca.configured:
        raise SystemExit("Set ALPACA_API_KEY and ALPACA_SECRET_KEY in .env before running.")

    be = Backend(db_name=db_name)
    stats = ensure_sp500_seeded(be, alpaca)
    print(
        "Done: "
        f"listed={stats['listed']} existing={stats['existing']} "
        f"added={stats['added']} priced={stats['priced']} failed={stats['failed']}"
    )
