from types import SimpleNamespace

from helpers.views import create_portfolio_image


def test_portfolio_image_convenience_wrapper_returns_png():
    info = SimpleNamespace(game=SimpleNamespace(start_money=10_000, pick_count=10))
    image = create_portfolio_image(
        user_data={"display_name": "Investor", "user_id": 1},
        game_data={"name": "Example", "id": "ABCDE"},
        stock_picks=[],
        info=info,
    )

    assert image.read(8) == b"\x89PNG\r\n\x1a\n"
