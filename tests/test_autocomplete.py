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


def test_buy_ticker_autocomplete_includes_typed_ticker_not_in_db():
    fake_frontend = SimpleNamespace(
        be=SimpleNamespace(
            get_many_stocks=lambda: (
                SimpleNamespace(ticker="AAPL", company="Apple Inc."),
                SimpleNamespace(ticker="MSFT", company="Microsoft Corporation"),
            ),
        ),
    )
    autocomplete.init_autocomplete(fake_frontend)

    choices = asyncio.run(autocomplete.buy_ticker_autocomplete(SimpleNamespace(), "nvda"))

    assert choices[0].value == "NVDA"
    assert "NVDA" in choices[0].name
    # Local cache still suggested when it matches the needle
    values = [c.value for c in choices]
    assert "NVDA" in values
    assert "AAPL" not in values
    assert "MSFT" not in values


def test_buy_ticker_autocomplete_prefers_db_label_for_known_ticker():
    fake_frontend = SimpleNamespace(
        be=SimpleNamespace(
            get_many_stocks=lambda: (
                SimpleNamespace(ticker="MSFT", company="Microsoft Corporation"),
            ),
        ),
    )
    autocomplete.init_autocomplete(fake_frontend)

    choices = asyncio.run(autocomplete.buy_ticker_autocomplete(SimpleNamespace(), "msft"))

    assert [(c.name, c.value) for c in choices] == [
        ("MSFT — Microsoft Corporation", "MSFT"),
    ]


def test_buy_ticker_autocomplete_works_when_db_empty():
    fake_frontend = SimpleNamespace(
        be=SimpleNamespace(get_many_stocks=lambda: (_ for _ in ()).throw(LookupError("No items found"))),
    )
    autocomplete.init_autocomplete(fake_frontend)

    choices = asyncio.run(autocomplete.buy_ticker_autocomplete(SimpleNamespace(), "TSLA"))

    assert [(c.name, c.value) for c in choices] == [("TSLA", "TSLA")]


def test_buy_ticker_autocomplete_normalizes_class_share():
    fake_frontend = SimpleNamespace(
        be=SimpleNamespace(get_many_stocks=lambda: ()),
    )
    autocomplete.init_autocomplete(fake_frontend)

    choices = asyncio.run(autocomplete.buy_ticker_autocomplete(SimpleNamespace(), "brk.b"))

    assert choices[0].value == "BRK-B"
