from stocks import GameLogic


def test_update_all_forwards_target_and_force(be, mocker):
    logic = GameLogic(be.sql.db)
    game_id = "ABCDE"
    update_statuses = mocker.patch.object(logic, "update_game_statuses")
    update_prices = mocker.patch.object(logic, "update_stock_prices")
    update_picks = mocker.patch.object(logic, "update_stock_picks")
    update_totals = mocker.patch.object(logic, "update_participants_and_games")

    logic.update_all(game_id=game_id, force=True)

    update_statuses.assert_called_once_with(game_id=game_id)
    update_prices.assert_called_once_with(game_id=game_id, force=True)
    update_picks.assert_called_once_with(game_id=game_id, force=True)
    update_totals.assert_called_once_with(game_id=game_id)


def test_participant_and_game_totals_include_uninvested_cash(be):
    owner_id = 101
    other_user_id = 102
    be.add_user(owner_id, "testing")
    be.add_user(other_user_id, "testing")
    be.add_game(
        user_id=owner_id,
        name="CashAccounting",
        start_date="2025-01-01",
        starting_money=10_000,
        total_picks=2,
    )
    game = be.get_many_games(name="CashAccounting", owner_id=owner_id)[0]
    be.update_game(game.id, status="active")
    be.add_participant(owner_id, game.id)
    be.add_participant(other_user_id, game.id)
    participants = be.get_many_participants(game_id=game.id)

    be.add_stock("HALF", "NASDAQ", "Half Invested")
    stock = be.get_stock("HALF")
    be.add_stock_pick(participants[0].id, stock.id)
    pick = be.get_many_stock_picks(participant_id=participants[0].id)[0]
    be.update_stock_pick(
        pick_id=pick.id,
        current_value=5_000,
        shares=50,
        start_value=5_000,
        status="owned",
    )

    GameLogic(be.sql.db).update_participants_and_games(game.id)

    first = be.get_participant(participants[0].id)
    second = be.get_participant(participants[1].id)
    updated_game = be.get_game(game.id)
    assert first.current_value == 10_000
    assert first.change_dollars == 0
    assert second.current_value == 10_000
    assert second.change_dollars == 0
    assert updated_game.current_value == 20_000
    assert updated_game.change_dollars == 0
