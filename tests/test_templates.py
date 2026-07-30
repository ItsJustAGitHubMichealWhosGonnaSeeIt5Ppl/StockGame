def test_game_template_round_trip_allows_no_pick_deadline(be):
    owner_id = 501
    be.add_user(owner_id, "testing")

    be.add_game_template(
        user_id=owner_id,
        name="Monthly Game",
        start_date="2099-08-01",
        recurring_period=2,
        pick_date=None,
    )

    templates = be.get_many_game_templates(status="enabled")
    assert len(templates) == 1
    template = be.get_game_template(templates[0].id)
    assert template.name == "Monthly Game"
    assert template.owner_id == owner_id
    assert template.recurring_period == 2
    assert template.pick_date is None


def test_recurring_games_create_due_template_once(be, mocker):
    from datetime import datetime
    from stocks import GameLogic

    owner_id = 502
    be.add_user(owner_id, "testing")
    be.add_game_template(
        user_id=owner_id,
        name="BiMonthly {date}",
        start_date="2025-01-01",
        create_days_in_advance=7,
        recurring_period=2,
        pick_date=None,
    )
    logic = GameLogic(be.sql.db)
    real_datetime = datetime
    mocked_datetime = mocker.patch("stocks.datetime")
    mocked_datetime.today.return_value = real_datetime(2025, 2, 25)
    mocked_datetime.strptime = real_datetime.strptime
    mocked_datetime.strftime = real_datetime.strftime

    logic.recurring_games()
    logic.recurring_games()

    games = be.get_many_games(owner_id=owner_id, include_private=True)
    assert len(games) == 1
    assert games[0].template_id is not None
    assert games[0].start_date == real_datetime(2025, 3, 1).date()
