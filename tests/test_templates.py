from datetime import date


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


def test_next_recurring_start_uses_anchor_and_clamps_february(be):
    from stocks import GameLogic

    logic = GameLogic(be.sql.db)
    anchor = date(2026, 7, 30)

    assert logic._next_recurring_start(anchor, 1) == date(2026, 7, 30)
    assert logic._next_recurring_start(anchor, 1, after=date(2026, 7, 30)) == date(2026, 8, 30)
    assert logic._next_recurring_start(anchor, 1, after=date(2027, 1, 30)) == date(2027, 2, 28)
    assert logic._next_recurring_start(anchor, 1, after=date(2027, 2, 28)) == date(2027, 3, 30)

    leap_anchor = date(2024, 1, 31)
    assert logic._next_recurring_start(leap_anchor, 1, after=date(2024, 1, 31)) == date(2024, 2, 29)
    assert logic._next_recurring_start(leap_anchor, 1, after=date(2024, 2, 29)) == date(2024, 3, 31)


def test_recurring_games_create_due_template_once(be, mocker):
    from datetime import datetime
    from stocks import GameLogic

    owner_id = 502
    be.add_user(owner_id, "testing")
    be.add_game_template(
        user_id=owner_id,
        name="BiMonthly {date}",
        start_date="2025-03-01",
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


def test_recurring_games_first_start_is_template_start_date(be, mocker):
    from datetime import datetime
    from stocks import GameLogic

    owner_id = 503
    be.add_user(owner_id, "testing")
    be.add_game_template(
        user_id=owner_id,
        name="monthly1",
        start_date="2026-07-31",
        create_days_in_advance=1,
        recurring_period=1,
        pick_date=None,
    )
    logic = GameLogic(be.sql.db)
    real_datetime = datetime
    mocked_datetime = mocker.patch("stocks.datetime")
    mocked_datetime.today.return_value = real_datetime(2026, 7, 30)
    mocked_datetime.strptime = real_datetime.strptime
    mocked_datetime.strftime = real_datetime.strftime

    logic.recurring_games()

    games = be.get_many_games(owner_id=owner_id, include_private=True)
    assert len(games) == 1
    assert games[0].start_date == date(2026, 7, 31)
