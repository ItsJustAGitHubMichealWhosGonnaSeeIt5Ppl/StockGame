import asyncio
from types import SimpleNamespace

import helpers.autocomplete as autocomplete


def test_sell_ticker_autocomplete_accepts_string_game_ids():
    calls = []
    fake_frontend = SimpleNamespace(
        my_stocks=lambda **kwargs: calls.append(kwargs) or (
            SimpleNamespace(stock_ticker="AAPL", status="owned"),
        )
    )
    autocomplete.init_autocomplete(fake_frontend)
    interaction = SimpleNamespace(
        data={"options": [{"name": "game_id", "value": "ABCDE"}]},
        user=SimpleNamespace(id=42),
    )

    choices = asyncio.run(autocomplete.sell_ticker_autocomplete(interaction, "AAP"))

    assert calls == [{
        "user_id": 42,
        "game_id": "ABCDE",
        "show_pending": True,
        "show_sold": False,
    }]
    assert [(choice.name, choice.value) for choice in choices] == [("AAPL", "AAPL")]


def test_buy_ticker_autocomplete_uses_only_local_cached_stocks():
    fake_frontend = SimpleNamespace(
        be=SimpleNamespace(
            get_many_stocks=lambda: (
                SimpleNamespace(ticker="AAPL", company="Apple Inc."),
                SimpleNamespace(ticker="MSFT", company="Microsoft Corporation"),
            ),
        ),
    )
    autocomplete.init_autocomplete(fake_frontend)

    choices = asyncio.run(autocomplete.buy_ticker_autocomplete(SimpleNamespace(), "micro"))

    assert [(choice.name, choice.value) for choice in choices] == [
        ("MSFT — Microsoft Corporation", "MSFT"),
    ]
