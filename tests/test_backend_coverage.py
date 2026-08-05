"""Production-oriented coverage for Backend methods not fully exercised elsewhere."""

import pytest

import helpers.exceptions as bexc
from stocks import Backend


def _owner_game(be: Backend, *, name="CoverGame", start="2099-01-01", **kwargs):
    owner_id = 501
    try:
        be.add_user(owner_id, "testing")
    except bexc.UserExistsError:
        pass
    game_id = be.add_game(user_id=owner_id, name=name, start_date=start, **kwargs)
    return owner_id, be.get_game(game_id)


class TestGenerateAndRepair:
    def test_generate_alnum_id_shape(self, be: Backend):
        ids = {be.generate_alnum_id() for _ in range(20)}
        assert len(ids) == 20
        for gid in ids:
            assert len(gid) == 5
            assert gid.isalnum()

    def test_repair_games_noop_and_with_games(self, be: Backend):
        be.repair_games()  # empty DB
        _owner_game(be, name="RepairMe")
        be.repair_games()  # loads each game via get_game


class TestGetAndUpdateGame:
    def test_get_game_by_id(self, be: Backend):
        _, game = _owner_game(be, name="GetMe")
        fetched = be.get_game(game.id)
        assert fetched.id == game.id
        assert fetched.name == "GetMe"

    def test_get_game_missing(self, be: Backend):
        with pytest.raises(LookupError):
            be.get_game("ZZZZZ")

    def test_get_many_games_filters(self, be: Backend):
        owner_id, public = _owner_game(be, name="PublicOpen", private_game=False)
        be.add_game(
            user_id=owner_id,
            name="PrivateOpen",
            start_date="2099-02-01",
            private_game=True,
        )
        publics = be.get_many_games(include_public=True, include_private=False)
        assert all(not g.private_game for g in publics)
        privates = be.get_many_games(include_public=False, include_private=True)
        assert any(g.private_game for g in privates)
        by_owner = be.get_many_games(owner_id=owner_id, include_private=True)
        assert len(by_owner) == 2

    def test_update_game_metadata_and_clear_dates(self, be: Backend):
        _, game = _owner_game(
            be,
            name="Updatable",
            start="2099-06-01",
            end_date="2099-12-01",
            pick_date="2099-05-01",
        )
        be.update_game(
            game.id,
            name="Renamed",
            private_game=True,
            total_picks=5,
            sell_during_game=True,
            clear_end_date=True,
            clear_pick_date=True,
        )
        updated = be.get_game(game.id)
        assert updated.name == "Renamed"
        assert updated.private_game is True
        assert updated.pick_count == 5
        assert updated.allow_selling is True
        assert updated.end_date is None
        assert updated.pick_date is None

    def test_update_game_rejects_locked_fields_after_start(self, be: Backend):
        _, game = _owner_game(be, name="AlreadyStarted", start="2020-01-01")
        with pytest.raises(ValueError, match="Cannot update"):
            be.update_game(game.id, starting_money=5000)

    def test_update_game_invalid_dates_and_money(self, be: Backend):
        _, game = _owner_game(be, name="BadUpdates", start="2099-01-01")
        with pytest.raises(bexc.InvalidDateFormatError):
            be.update_game(game.id, end_date="not-a-date")
        with pytest.raises(ValueError, match="after `start_date`"):
            be.update_game(game.id, end_date="2098-01-01")
        with pytest.raises(ValueError, match="starting_money"):
            be.update_game(game.id, starting_money=0.5)
        with pytest.raises(ValueError, match="total_picks|pick_count"):
            be.update_game(game.id, total_picks=-1)

    def test_add_game_validation_edges(self, be: Backend):
        be.add_user(502, "testing")
        with pytest.raises(bexc.InvalidDateFormatError):
            be.add_game(user_id=502, name="BadStart", start_date="nope")
        with pytest.raises(ValueError, match="starting_money"):
            be.add_game(user_id=502, name="Cheap", start_date="2099-01-01", starting_money=0)
        with pytest.raises(TypeError, match="pick_date"):
            be.add_game(
                user_id=502,
                name="DraftNoPick",
                start_date="2099-01-01",
                exclusive_picks=True,
            )
        with pytest.raises(ValueError, match="start_date"):
            be.add_game(
                user_id=502,
                name="DraftLatePick",
                start_date="2099-01-01",
                pick_date="2099-02-01",
                exclusive_picks=True,
            )


class TestStocksAndPrices:
    def test_get_many_stocks_and_tickers_only(self, be: Backend):
        be.add_stock("AAA", "NASDAQ", "Alpha")
        be.add_stock("BBB", "NYSE", "Beta")
        all_stocks = be.get_many_stocks()
        assert {s.ticker for s in all_stocks} >= {"AAA", "BBB"}
        nyse = be.get_many_stocks(exchange="NYSE")
        assert {s.ticker for s in nyse} == {"BBB"}
        assert all(s.exchange.lower() == "nyse" for s in nyse)
        tickers = be.get_many_stocks(tickers_only=True)
        assert "AAA" in tickers and "BBB" in tickers

    def test_get_stock_by_id_and_class_share_aliases(self, be: Backend):
        be.add_stock("BRK-B", "NYSE", "Berkshire")
        by_id = be.get_stock(be.get_stock("BRK-B").id)
        assert by_id.ticker == "BRK-B"
        assert be.get_stock("BRK.B").ticker == "BRK-B"

    def test_remove_stock_by_ticker_and_id(self, be: Backend):
        be.add_stock("DEL1", "NASDAQ", "Delete One")
        be.remove_stock("DEL1")
        with pytest.raises(LookupError):
            be.get_stock("DEL1")
        be.add_stock("DEL2", "NASDAQ", "Delete Two")
        stock_id = be.get_stock("DEL2").id
        be.remove_stock(stock_id)
        with pytest.raises(LookupError):
            be.get_stock("DEL2")

    def test_get_many_stock_prices_filters(self, be: Backend):
        be.add_stock("PRC", "NASDAQ", "Price Co")
        stock = be.get_stock("PRC")
        be.add_stock_price(stock.id, 10.0, datetime="2025-05-21 10:00:00")
        be.add_stock_price(stock.id, 11.0, datetime="2025-05-21 11:00:00")
        prices = be.get_many_stock_prices(stock_id=stock.id, datetime="2025-05-21")
        assert len(prices) == 2
        assert prices[0].price >= prices[1].price or prices[0].datetime >= prices[1].datetime


class TestStockPicks:
    def _active_participant(self, be: Backend, *, picks=10):
        owner_id, game = _owner_game(
            be, name=f"PickGame{picks}", start="2099-01-01", total_picks=picks
        )
        be.add_participant(owner_id, game.id)
        participant = be.get_many_participants(game_id=game.id, user_id=owner_id)[0]
        try:
            be.add_stock("PICK", "NASDAQ", "Pick Inc")
        except ValueError:
            pass
        stock = be.get_stock("PICK")
        return owner_id, game, participant, stock

    def test_add_get_update_remove_stock_pick(self, be: Backend):
        _, game, participant, stock = self._active_participant(be)
        be.add_stock_pick(participant.id, stock.id)
        picks = be.get_many_stock_picks(participant_id=participant.id)
        assert len(picks) == 1
        pick = be.get_stock_pick(picks[0].id)
        assert pick.status == "pending_buy"
        be.update_stock_pick(
            pick.id,
            status="owned",
            shares=10.0,
            start_value=100.0,
            current_value=110.0,
            change_dollars=10.0,
            change_percent=10.0,
        )
        owned = be.get_stock_pick(pick.id)
        assert owned.status == "owned"
        assert owned.shares == 10.0
        with_tickers = be.get_many_stock_picks(
            participant_id=participant.id, include_tickers=True
        )
        assert with_tickers[0].stock_ticker == "PICK"
        be.remove_stock_pick(pick.id)
        with pytest.raises(LookupError):
            be.get_many_stock_picks(participant_id=participant.id)

    def test_add_stock_pick_guards(self, be: Backend):
        owner_id, game = _owner_game(
            be,
            name="GuardedPicks",
            start="2099-01-01",
            total_picks=1,
            pick_date="2020-01-01",
        )
        be.add_user(999, "testing")
        be.add_participant(999, game.id)  # pending if private? public -> active
        # Make a pending participant via private game
        be.add_user(503, "testing")
        priv_id = be.add_game(
            user_id=owner_id,
            name="PrivatePending",
            start_date="2099-03-01",
            private_game=True,
        )
        be.add_participant(503, priv_id)
        pending = be.get_many_participants(game_id=priv_id, user_id=503)[0]
        assert pending.status == "pending"
        be.add_stock("GARD", "NASDAQ", "Guard")
        stock = be.get_stock("GARD")
        with pytest.raises(bexc.NotAllowedError) as exc:
            be.add_stock_pick(pending.id, stock.id)
        assert exc.value.reason == "Not active"

        # Max picks
        _, _game2, participant, stock2 = self._active_participant(be, picks=1)
        be.add_stock("MAX2", "NASDAQ", "Max Two")
        stock_b = be.get_stock("MAX2")
        be.add_stock_pick(participant.id, stock2.id)
        with pytest.raises(bexc.NotAllowedError) as max_exc:
            be.add_stock_pick(participant.id, stock_b.id)
        assert max_exc.value.reason == "Maximum picks reached"

        # Duplicate pick (room for another pick, same ticker blocked by unique constraint)
        _, _game3, participant3, stock3 = self._active_participant(be, picks=2)
        be.add_stock_pick(participant3.id, stock3.id)
        with pytest.raises(bexc.AlreadyExistsError):
            be.add_stock_pick(participant3.id, stock3.id)

    def test_get_many_stock_picks_invalid_status(self, be: Backend):
        with pytest.raises(ValueError, match="invalid `status`"):
            be.get_many_stock_picks(status="not_a_status")


class TestParticipants:
    def test_participant_crud_and_filters(self, be: Backend):
        owner_id, game = _owner_game(be, name="PartGame")
        be.add_user(700, "testing", display_name="Joiner")
        be.add_participant(owner_id, game.id)
        be.add_participant(700, game.id)
        parts = be.get_many_participants(game_id=game.id)
        assert len(parts) == 2
        by_user = be.get_many_participants(user_id=700, game_id=game.id)[0]
        fetched = be.get_participant(by_user.id)
        assert fetched.user_id == 700
        be.update_participant(
            by_user.id,
            current_value=1234.5,
            change_dollars=34.5,
            change_percent=2.8,
        )
        updated = be.get_participant(by_user.id)
        assert updated.current_value == 1234.5
        sorted_parts = be.get_many_participants(game_id=game.id, sort_by_value=True)
        assert sorted_parts[0].current_value >= (sorted_parts[1].current_value or 0)
        be.remove_participant(by_user.id)
        with pytest.raises(bexc.DoesntExistError):
            be.get_participant(by_user.id)

    def test_add_participant_duplicate_and_private_pending(self, be: Backend):
        owner_id, game = _owner_game(be, name="DupPart", private_game=True)
        be.add_participant(owner_id, game.id)
        with pytest.raises(ValueError, match="Already in game"):
            be.add_participant(owner_id, game.id)
        be.add_user(701, "testing")
        be.add_participant(701, game.id)
        joiner = be.get_many_participants(game_id=game.id, user_id=701)[0]
        assert joiner.status == "pending"

    def test_add_participant_rejects_after_pick_date(self, be: Backend):
        owner_id, game = _owner_game(
            be,
            name="LateJoin",
            start="2020-01-01",
            pick_date="2020-01-01",
        )
        be.add_user(702, "testing")
        with pytest.raises(ValueError, match="pick_date"):
            be.add_participant(702, game.id)

    def test_get_many_participants_invalid_status(self, be: Backend):
        with pytest.raises(ValueError, match="Invalid status"):
            be.get_many_participants(status="bogus")
