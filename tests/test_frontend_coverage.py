"""Frontend coverage for methods/branches not fully covered elsewhere."""

import pytest

from stocks import Backend, Frontend


def _add_stock(be: Backend, ticker: str = "FECOV"):
    try:
        be.add_stock(ticker, "NASDAQ", f"{ticker} Inc")
    except ValueError:
        pass
    return be.get_stock(ticker)


class TestCleanTextAndRemoveGame:
    def test_clean_text_strips_embed_breakers(self, fe: Frontend):
        cleaned = fe.clean_text("Hello (world) [link] `code` {brace}/slash\\")
        assert "(" not in cleaned
        assert ")" not in cleaned
        assert "[" not in cleaned
        assert "`" not in cleaned
        assert "{" not in cleaned
        assert "Hello" in cleaned
        assert "world" in cleaned

    def test_new_game_rejects_non_alphanumeric_name(self, fe: Frontend):
        with pytest.raises(ValueError, match="alphanumeric"):
            fe.new_game(user_id=10, name="Bad-Name!", start_date="2099-01-01")

    def test_remove_game_by_owner(self, fe: Frontend):
        game_id = fe.new_game(user_id=10, name="DeleteMe", start_date="2099-01-01")
        fe.remove_game(user_id=10, game_id=game_id)
        with pytest.raises(LookupError):
            fe.be.get_game(game_id)

    def test_remove_game_by_non_owner_denied(self, fe: Frontend):
        game_id = fe.new_game(user_id=10, name="KeepMe", start_date="2099-01-01")
        fe.register(20)
        with pytest.raises(PermissionError):
            fe.remove_game(user_id=20, game_id=game_id)
        assert fe.be.get_game(game_id).name == "KeepMe"

    def test_remove_game_bypass_permissions(self, fe: Frontend):
        game_id = fe.new_game(user_id=10, name="ForceDelete", start_date="2099-01-01")
        fe.register(20)
        fe.remove_game(user_id=20, game_id=game_id, enforce_permissions=False)
        with pytest.raises(LookupError):
            fe.be.get_game(game_id)


class TestMyGamesMyStocksSell:
    def test_my_games_include_ended(self, fe: Frontend):
        game_id = fe.new_game(user_id=10, name="EndedGame", start_date="2020-01-01")
        fe.be.update_game(game_id, status="ended")
        without = fe.my_games(user_id=10, include_ended=False)
        assert all(g.status != "ended" for g in without.games)
        with_ended = fe.my_games(user_id=10, include_ended=True)
        assert any(g.id == game_id for g in with_ended.games)

    def test_my_stocks_filters_pending_and_sold(self, fe: Frontend):
        game_id = fe.new_game(
            user_id=10,
            name="StockFilters",
            start_date="2099-01-01",
            total_picks=5,
            sell_during_game=True,
        )
        stock_a = _add_stock(fe.be, "FILA")
        stock_b = _add_stock(fe.be, "FILB")
        stock_c = _add_stock(fe.be, "FILC")
        participant_id = fe._participant_id(10, game_id)
        fe.be.add_stock_pick(participant_id, stock_a.id)
        fe.be.add_stock_pick(participant_id, stock_b.id)
        fe.be.add_stock_pick(participant_id, stock_c.id)
        picks = fe.be.get_many_stock_picks(participant_id=participant_id)
        by_stock = {p.stock_id: p for p in picks}
        fe.be.update_stock_pick(
            by_stock[stock_b.id].id,
            status="owned",
            shares=1.0,
            start_value=100.0,
            current_value=100.0,
        )
        fe.be.update_stock_pick(
            by_stock[stock_c.id].id,
            status="sold",
            shares=1.0,
            start_value=100.0,
            current_value=90.0,
            change_dollars=-10.0,
            change_percent=-10.0,
        )

        owned_only = fe.my_stocks(user_id=10, game_id=game_id, show_pending=False, show_sold=False)
        statuses = {p.status for p in owned_only}
        assert "pending_buy" not in statuses
        assert "sold" not in statuses
        assert "owned" in statuses

        with_pending = fe.my_stocks(user_id=10, game_id=game_id, show_pending=True, show_sold=False)
        assert any(p.status == "pending_buy" for p in with_pending)

        with_sold = fe.my_stocks(user_id=10, game_id=game_id, show_pending=False, show_sold=True)
        assert any(p.status == "sold" for p in with_sold)

    def test_sell_stock_already_pending(self, fe: Frontend):
        game_id = fe.new_game(
            user_id=10,
            name="AlreadySell",
            start_date="2099-01-01",
            sell_during_game=True,
        )
        stock = _add_stock(fe.be, "ALRD")
        participant_id = fe._participant_id(10, game_id)
        fe.be.add_stock_pick(participant_id, stock.id)
        pick = fe.be.get_many_stock_picks(participant_id=participant_id)[0]
        fe.be.update_stock_pick(
            pick.id,
            status="pending_sell",
            shares=1.0,
            start_value=50.0,
            current_value=50.0,
        )
        assert fe.sell_stock(user_id=10, game_id=game_id, ticker="ALRD") == "already_pending"

    def test_sell_stock_no_matching_pick(self, fe: Frontend):
        game_id = fe.new_game(user_id=10, name="NoSellPick", start_date="2099-01-01")
        _add_stock(fe.be, "NONE")
        with pytest.raises(LookupError):
            fe.sell_stock(user_id=10, game_id=game_id, ticker="NONE")


class TestManageJoinAndCapacity:
    def test_manage_game_bot_owner_can_edit_others_game(self, fe: Frontend):
        # fe.owner_user_id is 10; create game as another user then edit as bot owner
        fe.register(30)
        game_id = fe.new_game(user_id=30, name="OthersGame", start_date="2099-01-01")
        fe.manage_game(user_id=10, game_id=game_id, name="EditedByBotOwner")
        assert fe.be.get_game(game_id).name == "EditedByBotOwner"

    def test_manage_game_blocks_locked_fields_after_start(self, fe: Frontend):
        game_id = fe.new_game(user_id=10, name="StartedLock", start_date="2020-01-01")
        with pytest.raises(ValueError, match="Cannot update"):
            fe.manage_game(user_id=10, game_id=game_id, starting_money=1)

    def test_join_private_game_leaves_pending(self, fe: Frontend):
        game_id = fe.new_game(
            user_id=10,
            name="PrivateJoin",
            start_date="2099-01-01",
            private_game=True,
        )
        fe.join_game(user_id=40, game_id=game_id)
        participant = fe.be.get_many_participants(game_id=game_id, user_id=40)[0]
        assert participant.status == "pending"

    def test_buy_stock_rejects_long_ticker(self, fe: Frontend):
        game_id = fe.new_game(user_id=10, name="LongTicker", start_date="2099-01-01")
        with pytest.raises(ValueError, match="too long"):
            fe.buy_stock(user_id=10, game_id=game_id, ticker="TOOLONG")

    def test_force_update_bypass_permissions(self, fe: Frontend, mocker):
        mock_update = mocker.patch.object(fe.gl, "update_all")
        fe.register(55)
        fe.force_update(user_id=55, game_id=None, enforce_permissions=False)
        mock_update.assert_called_once_with(game_id=None, force=True)

    def test_list_games_include_ended(self, fe: Frontend):
        open_id = fe.new_game(user_id=10, name="ListOpen", start_date="2099-01-01")
        ended_id = fe.new_game(user_id=10, name="ListEnded", start_date="2020-01-01")
        fe.be.update_game(ended_id, status="ended")
        hidden = fe.list_games(include_ended=False, include_open=True, include_active=True)
        ids = {g.id for g in hidden}
        assert open_id in ids
        assert ended_id not in ids
        shown = fe.list_games(include_ended=True, include_open=False, include_active=False)
        assert any(g.id == ended_id for g in shown)
