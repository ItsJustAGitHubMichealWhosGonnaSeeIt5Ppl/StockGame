import pytest
from stocks import Frontend, Backend 
from helpers.datatype_validation import GameInfo, GameLeaderboard, GameParticipant
from datetime import datetime
import helpers.exceptions as bexc

MOCK_DATETIME_STR = "2025-05-21 10:00:00" # Fixed timestamp for tests, matches conftest
MOCK_DATE_STR = "2025-05-21" # Fixed date for tests, matches conftest

# Helper function to pre-add stock to avoid yfinance calls
def _add_stock_to_db(be: Backend, ticker: str, exchange: str = "NASDAQ", company_name: str = "Test Inc."):
    try:
        be.add_stock(ticker=ticker, exchange=exchange, company_name=company_name)
    except ValueError as e:
        if "already exists" not in str(e): # Ignore if stock already exists
            raise
    return be.get_stock(ticker_or_id=ticker)


class TestFrontend:
    """Test all (maybe we'll see) frontend methods"""

    # # NEW_GAME # #
    def test_new_game_minimal_success(self, fe: Frontend):
        user_id = 10 # Matches conftest owner_user_id
        game_name = 'TestGameMinimal'
        start_date = '2025-10-10'
        
        fe.new_game(
            user_id=user_id,
            name=game_name,
            start_date=start_date,
        )

        game = fe.be.get_game(game_id=1)
        assert game.id == 1 
        assert game.name == game_name 
        assert game.start_date == datetime.strptime(start_date, "%Y-%m-%d").date() 
        assert game.end_date is None
        assert game.pick_date is None
        assert game.start_money == 10000.00 # Default 
        assert game.pick_count == 10 
        assert game.draft_mode == False 
        assert game.allow_selling == False # Default 
        assert game.update_frequency == 'daily' # Default 
 

        # Check if owner was added as participant
        participants = fe.be.get_many_participants(user_id=user_id, game_id=game.id)
        assert len(participants) == 1
        assert participants[0].user_id == user_id

    def test_new_game_registers_new_user_as_owner(self, fe: Frontend):
        new_user_id = 1001
        game_name = 'NewUserGame'
        start_date = '2025-11-01'

        # User 1001 does not exist yet
        with pytest.raises(LookupError): # Expecting LookupError for user not found from get_user
            fe.be.get_user(user_id=new_user_id)

        fe.new_game(user_id=new_user_id, name=game_name, start_date=start_date)

        # Check if user was created
        created_user = fe.be.get_user(user_id=new_user_id)
        assert created_user.id == new_user_id
        assert created_user.source == 'testing' # Default source from fe fixture
        assert created_user.permissions == fe.default_perms # Default permissions

        games_found = fe.be.get_many_games(name=game_name, owner_id=new_user_id, include_private=True)
        assert len(games_found) == 1
        game = games_found[0]
        assert game.owner_id == new_user_id

        # Check if new user (owner) was added as participant
        participants = fe.be.get_many_participants(user_id=new_user_id, game_id=game.id)
        assert len(participants) == 1

    def test_new_game_all_params_success(self, fe: Frontend):
        user_id = 10 # Matches conftest
        game_name = 'TestGameFull'
        start_date = '2025-10-10'
        end_date = '2025-10-11'
        starting_money = 1.0
        pick_date = '2025-10-10' # Same as start_date for exclusive_picks=True
        private_game = True
        total_picks = 40
        exclusive_picks = True # if True, pick_date must be on or before start_date
        sell_during_game = True
        update_frequency = 'hourly'

        fe.new_game(
            user_id=user_id,
            name=game_name,
            start_date=start_date,
            end_date=end_date,
            starting_money=starting_money,
            pick_date=pick_date,
            private_game=private_game,
            total_picks=total_picks,
            exclusive_picks=exclusive_picks,
            sell_during_game=sell_during_game,
            update_frequency=update_frequency
        )
        games_found = fe.be.get_many_games(name=game_name, owner_id=user_id, include_private=True)
        assert len(games_found) == 1
        game = games_found[0]

        assert game.id == 1 
        assert game.name == game_name 
        assert game.start_date == datetime.strptime(start_date, "%Y-%m-%d").date() 
        assert game.end_date == datetime.strptime(end_date, "%Y-%m-%d").date() 
        assert game.pick_date == datetime.strptime(pick_date, "%Y-%m-%d").date() 
        assert game.start_money == starting_money 
        assert game.pick_count == total_picks 
        assert game.draft_mode == exclusive_picks 
        assert game.allow_selling == sell_during_game 
        assert game.update_frequency == update_frequency 

    # # LIST_GAMES # #
    def test_list_public_games(self, fe: Frontend):
        user_id = 10 # Matches conftest
        start_date = '2025-10-10'

        fe.new_game( # Create a public game
            user_id=user_id,
            name='PublicGame',
            start_date=start_date,
            private_game=False
        )
        fe.new_game( # Create a private game
            user_id=user_id,
            name='PrivateGame',
            start_date=start_date,
            private_game=True
        )

        games = fe.list_games(include_private=False)
        assert len(games) == 1
        assert games[0].name == 'PublicGame'
        assert games[0].private_game == False

    def test_list_all_games(self, fe: Frontend): # Include private ones this time
        user_id = 10
        start_date = '2025-10-10'

        fe.new_game(user_id=user_id, name='PublicGameList', start_date=start_date, private_game=False)
        fe.new_game(user_id=user_id, name='PrivateGameList', start_date=start_date, private_game=True)

        games = fe.list_games(include_private=True)
        assert len(games) == 2
        game_names = {g.name for g in games}
        assert 'PublicGameList' in game_names
        assert 'PrivateGameList' in game_names

    def test_list_no_games_when_only_private_exists_and_not_included(self, fe: Frontend):
        user_id = 10
        start_date = '2025-10-10'

        fe.new_game(
            user_id=user_id,
            name='OnlyPrivateGame',
            start_date=start_date,
            private_game=True
        )
        with pytest.raises(LookupError, match='No items found'):
            games = fe.list_games(include_private=False)
       

    def test_list_no_games_when_db_is_empty(self, fe: Frontend):
        with pytest.raises(LookupError, match='No items found'):
            games = fe.list_games(include_private=False)


    # # GAME_INFO # #
    def test_game_info_success_no_leaderboard(self, fe: Frontend):
        user_id = 10
        game_name = "GameInfoTest1"
        fe.new_game(user_id=user_id, name=game_name, start_date="2025-10-01", starting_money=5000)
        game_db = fe.be.get_many_games(name=game_name, owner_id=user_id, include_private=True)[0]

        info = fe.game_info(game_id=game_db.id, show_leaderboard=False)

        assert isinstance(info, GameInfo)
        assert info.leaderboard == None
        assert info.game.name== game_name
        assert info.game.id== game_db.id



    def test_game_info_success_with_leaderboard(self, fe: Frontend):
        owner_id = 10
        user2_id = 20
        fe.register(user_id=user2_id, username="UserTwo")

        game_name = "GameInfoTest2"
        fe.new_game(user_id=owner_id, name=game_name, start_date="2025-10-01", starting_money=1000)
        game_db = fe.be.get_many_games(name=game_name, owner_id=owner_id, include_private=True)[0]

        # Owner is auto-added. Add another user.
        fe.join_game(user_id=user2_id, game_id=game_db.id)

        # Manually update participant values for testing leaderboard formatting
        # Participant ID for owner (user_id=10)
        p1_id = fe._participant_id(user_id=owner_id, game_id=game_db.id)
        fe.be.update_participant(participant_id=p1_id, current_value=1234.567)

        # Participant ID for user2_id (user_id=20)
        p2_id = fe._participant_id(user_id=user2_id, game_id=game_db.id)
        fe.be.update_participant(participant_id=p2_id, current_value=987.654)
        
        # Manually update game aggregate value
        fe.be.update_game(game_id=game_db.id, aggregate_value=1234.567 + 987.654)


        info = fe.game_info(game_id=game_db.id, show_leaderboard=True)

        assert isinstance(info, GameInfo)
        assert isinstance(info.leaderboard, list)
        assert info.game.name== game_name
        assert info.game.id== game_db.id
        assert info.game.current_value == 2222.22 


        assert len(info.leaderboard) == 2
        leaderboard_user_ids = {item.user_id for item in info.leaderboard}
        assert owner_id in leaderboard_user_ids
        assert user2_id in leaderboard_user_ids

        for item in info.leaderboard:
            if item.user_id == owner_id:
                assert item.current_value == 1234.57
            elif item.user_id == user2_id:
                assert item.current_value == 987.65


    def test_game_info_non_existent_game(self, fe: Frontend):
        with pytest.raises(LookupError): # Backend.get_game raises LookupError
            fe.game_info(game_id=999)

    # # REGISTER # #
    def test_register_id_only(self, fe: Frontend):
        user_id = 11
        # fe fixture has source 'testing'
        status_msg = fe.register(user_id=user_id)
        assert status_msg == "Registered"

        user = fe.be.get_user(user_id=11)
        assert user.id == user_id
        assert user.source == 'testing' # Source from Frontend instance
        assert user.datetime_created == datetime.strptime(MOCK_DATETIME_STR, "%Y-%m-%d %H:%M:%S") # From conftest mock

    def test_register_full_with_username_and_source_override(self, fe: Frontend):
        user_id = 12
        source_override = 'manual_source'
        username = 'TestUser12'

        status_msg = fe.register(user_id=user_id, source=source_override, username=username)
        assert status_msg == "Registered"

        user = fe.be.get_user(user_id=12)
        assert user.id == user_id
        assert user.source == source_override
        assert user.display_name == username
        assert user.datetime_created == datetime.strptime(MOCK_DATETIME_STR, "%Y-%m-%d %H:%M:%S")

    def test_register_duplicate_user(self, fe: Frontend):
        user_id = 11
        fe.register(user_id=user_id) # First registration

        status_msg = fe.register(user_id=user_id, username="NewNameAttempt") # Attempt duplicate
        assert status_msg == "User already registered"

        # Verify original details are preserved (or updated if that's the design, though add_user fails on PK constraint)
        user = fe.be.get_user(user_id=11)
        assert user.display_name is None # Original registration had no username

    # # CHANGE_NAME # #
    def test_change_name_success(self, fe: Frontend):
        user_id = 10 # Owner user from fixture
        new_name = "NewDisplayName"

        fe.change_name(user_id=user_id, name=new_name)

        user = fe.be.get_user(user_id=user_id)
        assert user.display_name == new_name

    def test_change_name_non_existent_user(self, fe: Frontend):
        with pytest.raises(bexc.DoesntExistError):
            fe.change_name(user_id=9999, name="GhostName")


    # # JOIN_GAME # #
    def test_join_game_success(self, fe: Frontend):
        owner_id = 10
        user_to_join_id = 25
        game_name = "JoinGameTest"
        team_name = "TheWinners"

        fe.register(user_id=user_to_join_id, username="Joiner")
        fe.new_game(user_id=owner_id, name=game_name, start_date="2025-12-01", private_game=False)
        game_db = fe.be.get_many_games(name=game_name, owner_id=owner_id, include_private=True)[0]

        fe.join_game(user_id=user_to_join_id, game_id=game_db.id, name=team_name)

        participants = fe.be.get_many_participants(user_id=user_to_join_id, game_id=game_db.id)
        assert len(participants) == 1
        participant = participants[0]
        assert participant.user_id == user_to_join_id
        assert participant.game_id == game_db.id
        assert participant.name == team_name # Team name for the game
        assert participant.status == 'active' # Default status for new participant

    def test_join_game_user_not_registered(self, fe: Frontend):
        # Frontend.join_game does not register the user, relies on Backend.add_participant
        # Backend.add_participant inserts into game_participants which has a user_id FK.
        # This should fail at the SQL level if user_id doesn't exist in users table.
        owner_id = 10
        non_existent_user_id = 900
        game_name = "JoinGameFail"
        fe.new_game(user_id=owner_id, name=game_name, start_date="2025-12-01")
        game_db = fe.be.get_many_games(name=game_name, owner_id=owner_id, include_private=True)[0]

        with pytest.raises(Exception) as excinfo: # SqlHelper wraps SQL errors
            fe.join_game(user_id=non_existent_user_id, game_id=game_db.id)
        assert "FOREIGN KEY constraint failed" in str(excinfo.value) # Check for SQLite error

    def test_join_game_non_existent_game(self, fe: Frontend):
        user_id = 10 # Registered user
        with pytest.raises(LookupError) as excinfo: # SqlHelper wraps SQL errors
             fe.join_game(user_id=user_id, game_id=999) # Game 999 does not exist
        assert "Game not found." in str(excinfo)
        
    def test_join_game_game_pick_date_passed(self, fe: Frontend):
        user_id = 10 # Registered user
        game_name = "JoinGameFail"
        
        fe.new_game(user_id=user_id, name=game_name, start_date="2025-02-01", pick_date="2025-02-01")
        with pytest.raises(ValueError) as excinfo: # SqlHelper wraps SQL errors
             fe.join_game(user_id=user_id, game_id=1) # Game 999 does not exist
        assert "`pick_date` has passed." in str(excinfo)


    def test_join_game_twice_by_same_user(self, fe: Frontend):
        owner_id = 10
        game_name = "JoinTwiceTest"
        fe.new_game(user_id=owner_id, name=game_name, start_date="2025-12-01")
        game_db = fe.be.get_many_games(name=game_name, owner_id=owner_id, include_private=True)[0]
        # Owner is already a participant. Let's try to add them again.

        with pytest.raises(ValueError) as excinfo:
            fe.join_game(user_id=owner_id, game_id=game_db.id)
        
        assert "Already in game." in str(excinfo)


    # # MY_GAMES # #
    def test_my_games_no_games(self, fe: Frontend):
        user_id = 30
        fe.register(user_id=user_id, username="GameLessUser")
        
        with pytest.raises(LookupError) as exc:
            result = fe.my_games(user_id=user_id)
        assert 'Player is not in any games.' in str(exc)

    def test_my_games_one_game(self, fe: Frontend):
        user_id = 10 # Owner
        game_name = "MyOnlyGame"
        fe.new_game(user_id=user_id, name=game_name, start_date="2025-07-01")
        game_db = fe.be.get_many_games(name=game_name, owner_id=user_id, include_private=True)[0]

        result = fe.my_games(user_id=user_id)

        assert result.user.id == user_id
        assert len(result.games) == 1
        assert result.games[0].id == game_db.id
        assert result.games[0].name == game_name

    def test_my_games_multiple_games(self, fe: Frontend):
        user_id = 10
        game1_name = "MyFirstGame"
        game2_name = "MySecondGame"
        fe.new_game(user_id=user_id, name=game1_name, start_date="2025-07-01")
        game1_db = fe.be.get_many_games(name=game1_name, owner_id=user_id, include_private=True)[0]

        # Create another game and have the user join it (owner is auto-joined)
        other_owner_id = 35
        fe.register(user_id=other_owner_id)
        fe.new_game(user_id=other_owner_id, name=game2_name, start_date="2025-08-01")
        game2_db = fe.be.get_many_games(name=game2_name, owner_id=other_owner_id, include_private=True)[0]
        fe.join_game(user_id=user_id, game_id=game2_db.id) # User 10 joins game 2

        result = fe.my_games(user_id=user_id)

        assert result.user.id == user_id
        assert len(result.games) == 2
        game_ids_in_result = {g.id for g in result.games}
        assert game1_db.id in game_ids_in_result
        assert game2_db.id in game_ids_in_result
        
    def test_my_games_user_not_found(self, fe: Frontend):
        with pytest.raises(LookupError): # From be.get_user
            fe.my_games(user_id=999)


    # # MY_STOCKS # #
    def test_my_stocks_success(self, fe: Frontend):
        owner_id = 10
        game_name = "MyStocksGame"
        fe.new_game(user_id=owner_id, name=game_name, start_date="2025-06-01")
        fe.be.add_stock(ticker='TEST', exchange='pytest', company_name='PyTesting')
        game = fe.be.get_many_games(name=game_name, owner_id=owner_id, include_private=True)[0]
        player_id = fe._participant_id(game_id=game.id, user_id=owner_id)
        
        fe.buy_stock(game_id=game.id, user_id=owner_id, ticker='TEST')  # There is only

        stock = fe.my_stocks(user_id=owner_id, game_id=game.id)
        assert len(stock) == 1

    def test_my_stocks_participant_not_found(self, fe: Frontend):
        owner_id = 10
        other_user_id = 77
        fe.register(user_id=other_user_id)
        game_name = "MyStocksGameNoPart"
        fe.new_game(user_id=owner_id, name=game_name, start_date="2025-06-01")
        game_db = fe.be.get_many_games(name=game_name, owner_id=owner_id, include_private=True)[0]

        # user 77 is not part of game_db.id
        with pytest.raises(LookupError) as excinfo:
            fe.my_stocks(user_id=other_user_id, game_id=game_db.id)
        assert "No items found" in str(excinfo.value)


    # # BUY_STOCK # #
    def test_buy_stock_success_new_stock(self, fe: Frontend):
        owner_id = 10
        game_name = "BuyStockGame"
        start_date = "2025-06-01"
        fe.new_game(user_id=owner_id, name=game_name, start_date=start_date)
        game_db = fe.be.get_many_games(name=game_name, owner_id=owner_id, include_private=True)[0]

        ticker_to_buy = "NEWCO"
        # Ensure stock is NOT in DB first to test gl.find_stock's yf.Ticker path.
        # For testing without network, we assume yf.Ticker is mocked or this path is avoided.
        # As per plan, we will add stock to DB first to avoid yfinance call.
        _add_stock_to_db(fe.be, ticker=ticker_to_buy, company_name="New Company")
        stock_in_db = fe.be.get_stock(ticker_to_buy)
        
        # Participant needs to be active for add_stock_pick. Owner is 'pending' by default.
        participant_obj = fe._participant_id(user_id=owner_id, game_id=game_db.id)
        fe.be.update_participant(participant_id=participant_obj, status='active')


        fe.buy_stock(user_id=owner_id, game_id=game_db.id, ticker=ticker_to_buy)

        participant_info = fe._participant_id(user_id=owner_id, game_id=game_db.id)
        picks = fe.be.get_many_stock_picks(participant_id=participant_info, stock_id=stock_in_db.id)
        assert len(picks) == 1
        assert picks[0].stock_id == stock_in_db.id
        assert picks[0].status == 'pending_buy'

    def test_buy_stock_already_known_stock(self, fe: Frontend):
        owner_id = 10
        game_name = "BuyKnownStockGame"
        fe.new_game(user_id=owner_id, name=game_name, start_date="2025-06-01")
        game_db = fe.be.get_many_games(name=game_name, owner_id=owner_id, include_private=True)[0]

        ticker_known = "KNOWNCO"
        _add_stock_to_db(fe.be, ticker=ticker_known, company_name="Known Company") # Add to DB
        stock_in_db = fe.be.get_stock(ticker_known)

        participant_obj = fe._participant_id(user_id=owner_id, game_id=game_db.id)
        fe.be.update_participant(participant_id=participant_obj, status='active')

        fe.buy_stock(user_id=owner_id, game_id=game_db.id, ticker=ticker_known)

        participant_info = fe._participant_id(user_id=owner_id, game_id=game_db.id)
        picks = fe.be.get_many_stock_picks(participant_id=participant_info, stock_id=stock_in_db.id)
        assert len(picks) == 1
        assert picks[0].status == 'pending_buy'

    def test_buy_stock_at_max_picks(self, fe: Frontend):
        owner_id = 10
        game_name = "MaxPicksGame"
        # Game with 1 total pick
        fe.new_game(user_id=owner_id, name=game_name, start_date="2025-06-01", total_picks=1)
        game_db = fe.be.get_many_games(name=game_name, owner_id=owner_id, include_private=True)[0]
        
        participant_obj = fe._participant_id(user_id=owner_id, game_id=game_db.id)
        fe.be.update_participant(participant_id=participant_obj, status='active')

        ticker1 = "TICK1"
        _add_stock_to_db(fe.be, ticker1)
        fe.buy_stock(user_id=owner_id, game_id=game_db.id, ticker=ticker1) # First pick

        ticker2 = "TICK2"
        _add_stock_to_db(fe.be, ticker2)
        with pytest.raises(bexc.NotAllowedError) as excinfo:
            fe.buy_stock(user_id=owner_id, game_id=game_db.id, ticker=ticker2) # Second pick
        assert "Maximum picks reached" in str(excinfo.value.reason)

    def test_buy_stock_after_pick_date_passed(self, fe: Frontend, mocker):
        owner_id = 10
        game_name = "PickDatePassedGame"
        # Pick date is in the past relative to MOCK_DATE_STR ('2025-05-21')
        pick_date_past = "2025-05-20"
        # We need to mock datetime.today() for Backend.add_stock_pick's check
        mock_datetime = mocker.patch('stocks.datetime')
        mock_datetime.today.return_value = datetime.strptime(MOCK_DATE_STR, '%Y-%m-%d')
        mock_datetime.strptime = datetime.strptime # Keep strptime working

        fe.new_game(user_id=owner_id, name=game_name, start_date="2025-06-01", pick_date=pick_date_past)
        game_db = fe.be.get_many_games(name=game_name, owner_id=owner_id, include_private=True)[0]
        
        participant_obj = fe._participant_id(user_id=owner_id, game_id=game_db.id)
        fe.be.update_participant(participant_id=participant_obj, status='active')

        ticker = "LATEPICK"
        _add_stock_to_db(fe.be, ticker)
        with pytest.raises(bexc.NotAllowedError) as excinfo:
            fe.buy_stock(user_id=owner_id, game_id=game_db.id, ticker=ticker)
        assert "Past pick_date" in str(excinfo.value.reason)

    def test_buy_stock_participant_not_active(self, fe: Frontend):
        owner_id = 10
        pending_id = 11
        game_name = "BuyStockNotActiveGame"
        fe.new_game(user_id=owner_id, name=game_name, start_date="2025-06-01",private_game=True)
        game_db = fe.be.get_many_games(name=game_name, owner_id=owner_id, include_private=True)[0]
        
        fe.register(user_id=pending_id) # Pending user
        fe.join_game(user_id=pending_id, game_id=game_db.id)
        ticker = "INACTIVEBUY"
        _add_stock_to_db(fe.be, ticker)

        with pytest.raises(bexc.NotAllowedError) as excinfo:
            fe.buy_stock(user_id=pending_id, game_id=game_db.id, ticker=ticker)
        assert "Not active" in str(excinfo.value.reason)


    # # SELL_STOCK # #
    def test_sell_stock_not_implemented(self, fe: Frontend):
        # This method is currently `pass` in stocks.py
        # Test that it doesn't raise an error and returns None (default for pass)
        assert fe.sell_stock(user_id=10, game_id=1, ticker="ANY") is None


    # # REMOVE_PICK # #
    def test_remove_pick_success(self, fe: Frontend):
        owner_id = 10
        game_name = "RemovePickGame"
        fe.new_game(user_id=owner_id, name=game_name, start_date="2025-06-01")
        game_db = fe.be.get_many_games(name=game_name, owner_id=owner_id, include_private=True)[0]

        ticker_to_remove = "REMOVEIT"
        _add_stock_to_db(fe.be, ticker_to_remove)
        stock_in_db = fe.be.get_stock(ticker_to_remove)
        
        participant_obj = fe._participant_id(user_id=owner_id, game_id=game_db.id)
        fe.be.update_participant(participant_id=participant_obj, status='active')


        # Add a pick to remove
        fe.be.add_stock_pick(participant_id=participant_obj, stock_id=stock_in_db.id)
        picks_before = fe.be.get_many_stock_picks(participant_id=participant_obj, stock_id=stock_in_db.id, status='pending_buy')
        assert len(picks_before) == 1

        result = fe.remove_pick(user_id=owner_id, game_id=game_db.id, ticker=ticker_to_remove)
        assert result is None # Backend.remove_stock_pick returns None on success
        with pytest.raises(LookupError) as exc:
            fe.be.get_many_stock_picks(participant_id=participant_obj, stock_id=stock_in_db.id, status='pending_buy')
        assert 'No items found' in str(exc)
        

    def test_remove_pick_no_matching_pending_pick(self, fe: Frontend):
        owner_id = 10
        game_name = "RemoveNoPickGame"
        fe.new_game(user_id=owner_id, name=game_name, start_date="2025-06-01")
        game_db = fe.be.get_many_games(name=game_name, owner_id=owner_id, include_private=True)[0]
        
        participant_obj = fe._participant_id(user_id=owner_id, game_id=game_db.id)
        fe.be.update_participant(participant_id=participant_obj, status='active')


        ticker_no_pick = "NOPICKTOREM"
        _add_stock_to_db(fe.be, ticker_no_pick)

        with pytest.raises(LookupError) as excinfo:
            fe.remove_pick(user_id=owner_id, game_id=game_db.id, ticker=ticker_no_pick)
        assert 'No picks found' in str(excinfo.value) # The second arg to ValueError is buggy in source

    def test_remove_pick_stock_not_found_in_db(self, fe: Frontend):
        owner_id = 10
        game_name = "RemoveNonStockGame"
        fe.new_game(user_id=owner_id, name=game_name, start_date="2025-06-01")
        game_db = fe.be.get_many_games(name=game_name, owner_id=owner_id, include_private=True)[0]
        
        participant_obj = fe._participant_id(user_id=owner_id, game_id=game_db.id)
        fe.be.update_participant(participant_id=participant_obj, status='active')


        with pytest.raises(LookupError): # From be.get_stock
            fe.remove_pick(user_id=owner_id, game_id=game_db.id, ticker="NONEXISTENTSTOCK")

    def test_remove_pick_owned_stock_not_pending(self, fe: Frontend):
        owner_id = 10
        game_name = "RemoveOwnedStockGame"
        fe.new_game(user_id=owner_id, name=game_name, start_date="2025-06-01")
        game_db = fe.be.get_many_games(name=game_name, owner_id=owner_id, include_private=True)[0]

        ticker_owned = "OWNEDIT"
        _add_stock_to_db(fe.be, ticker_owned)
        stock_in_db = fe.be.get_stock(ticker_owned)
        
        participant_obj = fe._participant_id(user_id=owner_id, game_id=game_db.id)
        fe.be.update_participant(participant_id=participant_obj, status='active')


        # Add a pick and update its status to 'owned'
        fe.be.add_stock_pick(participant_id=participant_obj, stock_id=stock_in_db.id)
        pick_to_update = fe.be.get_many_stock_picks(participant_id=participant_obj, stock_id=stock_in_db.id)[0]
        fe.be.update_stock_pick(pick_id=pick_to_update.id, current_value=100, status='owned')

        # remove_pick specifically looks for 'pending_buy' status
        with pytest.raises(ValueError) as excinfo:
            fe.remove_pick(user_id=owner_id, game_id=game_db.id, ticker=ticker_owned)
        assert 'Pick status is `owned`.  Only `pending_buy` picks can be removed.' in str(excinfo)

    # # START_DRAFT # #
    def test_start_draft_not_implemented(self, fe: Frontend):
        # This method is currently `pass` in stocks.py
        assert fe.start_draft(user_id=10, game_id=1) is None

    # # FORCE_UPDATE # #
    def test_force_update_by_owner_success(self, fe: Frontend, mocker):
        owner_id = 10 # This is fe.owner_id from conftest
        mock_update_all = mocker.patch.object(fe.gl, 'update_all')

        fe.force_update(user_id=owner_id, game_id=1)
        mock_update_all.assert_called_once_with(game_id=1, force=True)

    def test_force_update_by_owner_all_games(self, fe: Frontend, mocker):
        owner_id = 10
        mock_update_all = mocker.patch.object(fe.gl, 'update_all')

        fe.force_update(user_id=owner_id, game_id=None) # All games
        mock_update_all.assert_called_once_with(game_id=None, force=True)

    def test_force_update_by_non_owner_raises_error(self, fe: Frontend, mocker):
        non_owner_id = 99
        fe.register(user_id=non_owner_id) # Register non-owner
        mock_update_all = mocker.patch.object(fe.gl, 'update_all')

        with pytest.raises(PermissionError) as excinfo:
            fe.force_update(user_id=non_owner_id, game_id=1)
        mock_update_all.assert_not_called()


    # # MANAGE_GAME # #
    def test_manage_game_by_owner_success(self, fe: Frontend):
        owner_id = 10
        game_name_orig = "ManageGameOrig"
        fe.new_game(user_id=owner_id, name=game_name_orig, start_date="2025-07-01")
        game_db = fe.be.get_many_games(name=game_name_orig, owner_id=owner_id, include_private=True)[0]

        new_game_name = "ManageGameNewName"
        new_end_date = "2025-08-01"
        fe.manage_game(user_id=owner_id, game_id=game_db.id, name=new_game_name, end_date=new_end_date)

        updated_game = fe.be.get_game(game_id=game_db.id)
        assert updated_game.name == new_game_name
        #assert updated_game.end_date == new_end_date #TODO are these needed ? the game name changed
        #assert updated_game.last_updated == MOCK_DATETIME_STR # Check if updated

    def test_manage_game_by_non_owner_returns_permission_string(self, fe: Frontend):
        owner_id = 10
        non_owner_id = 88
        fe.register(user_id=non_owner_id)
        game_name = "NonOwnerManageGame"
        fe.new_game(user_id=owner_id, name=game_name, start_date="2025-07-01")
        game_db = fe.be.get_many_games(name=game_name, owner_id=owner_id, include_private=True)[0]
        with pytest.raises(PermissionError):
            result = fe.manage_game(user_id=non_owner_id, game_id=game_db.id, name="AttemptChange")

        # Verify game was not changed
        game_after = fe.be.get_game(game_id=game_db.id)
        assert game_after.name == game_name


    # # PENDING_GAME_USERS # #
    def test_pending_game_users_by_owner_success(self, fe: Frontend):
        owner_id = 10
        user1_pending_id = 41
        user2_approved_id = 42
        fe.register(user_id=user1_pending_id)
        fe.register(user_id=user2_approved_id)

        game_name = "PendingUsersGame"
        # Private game so users go to pending
        fe.new_game(user_id=owner_id, name=game_name, start_date="2025-07-01", private_game=True)
        game_db = fe.be.get_many_games(name=game_name, owner_id=owner_id, include_private=True)[0]

        # user1 joins, should be pending
        fe.join_game(user_id=user1_pending_id, game_id=game_db.id)
        # user2 joins and gets approved by owner (owner needs to be the one calling approve)
        fe.join_game(user_id=user2_approved_id, game_id=game_db.id)
        pending_users_before = fe.pending_game_users(user_id=owner_id, game_id=game_db.id)
        fe.approve_game_users(user_id=owner_id, game_id=game_db.id, approved_user_id=user2_approved_id)


        pending_users: tuple[GameParticipant] | tuple[()] = fe.pending_game_users(user_id=owner_id, game_id=game_db.id)
        assert len(pending_users) == 1 # Only user1 should be pending (owner is also active)
        assert pending_users[0].user_id == user1_pending_id
        assert pending_users[0].status == 'pending'

    def test_pending_game_users_by_non_owner(self, fe: Frontend):
        owner_id = 10
        non_owner_id = 43
        fe.register(user_id=non_owner_id)
        game_name = "PendingUsersNonOwner"
        fe.new_game(user_id=owner_id, name=game_name, start_date="2025-07-01", private_game=True)
        game_db = fe.be.get_many_games(name=game_name, owner_id=owner_id, include_private=True)[0]
        with pytest.raises(PermissionError):
            result = fe.pending_game_users(user_id=non_owner_id, game_id=game_db.id)

    def test_pending_game_users_no_pending_users(self, fe: Frontend):
        owner_id = 10
        game_name = "NoPendingGame"
        fe.new_game(user_id=owner_id, name=game_name, start_date="2025-07-01", private_game=True)
        game_db = fe.be.get_many_games(name=game_name, owner_id=owner_id, include_private=True)[0]
        # Owner is auto-added and approved by default for their own game in this setup.
        # Let's approve the owner first.
        #owner_participant = fe._participant_id(user_id=owner_id, game_id=game_db.id)
        with pytest.raises(LookupError, match='No items found'):
            pending_users = fe.pending_game_users(user_id=owner_id, game_id=game_db.id)


    # # APPROVE_GAME_USERS # #
    def test_approve_game_users_by_owner_success(self, fe: Frontend):
        owner_id = 10
        user_to_approve_id = 51
        fe.register(user_id=user_to_approve_id)

        game_name = "ApproveUserGame"
        fe.new_game(user_id=owner_id, name=game_name, start_date="2025-07-01", private_game=True)
        game_db = fe.be.get_many_games(name=game_name, owner_id=owner_id, include_private=True)[0]

        fe.join_game(user_id=user_to_approve_id, game_id=game_db.id)
        participant_to_approve = fe.be.get_participant(participant_id=fe._participant_id(user_id=user_to_approve_id, game_id=game_db.id))
        assert participant_to_approve.status == 'pending' # Should be pending

        fe.approve_game_users(user_id=owner_id, game_id=game_db.id, approved_user_id=user_to_approve_id )

        approved_user_participant = fe.be.get_participant(participant_id=participant_to_approve.id)
        assert approved_user_participant.status == 'active'

    def test_approve_game_users_by_non_owner(self, fe: Frontend):
        owner_id = 10
        non_owner_id = 52
        user_to_approve_id = 53
        fe.register(user_id=non_owner_id)
        fe.register(user_id=user_to_approve_id)

        game_name = "ApproveUserNonOwner"
        fe.new_game(user_id=owner_id, name=game_name, start_date="2025-07-01", private_game=True)
        game_db = fe.be.get_many_games(name=game_name, owner_id=owner_id, include_private=True)[0]

        fe.join_game(user_id=user_to_approve_id, game_id=game_db.id)
        participant_to_approve = fe._participant_id(user_id=user_to_approve_id, game_id=game_db.id)
        with pytest.raises(PermissionError):
            result = fe.approve_game_users(user_id=non_owner_id, game_id=game_db.id, approved_user_id=user_to_approve_id)

        # Verify user is still pending
        still_pending_participant = fe.be.get_participant(participant_id=participant_to_approve)
        assert still_pending_participant.status == 'pending'


    # # GET_ALL_PARTICIPANTS # #
    def test_get_all_participants_success(self, fe: Frontend):
        owner_id = 10
        user2_id = 61
        user3_id = 62
        fe.register(user_id=user2_id)
        fe.register(user_id=user3_id)

        game_name = "AllPartsGame"
        fe.new_game(user_id=owner_id, name=game_name, start_date="2025-07-01")
        game_db = fe.be.get_many_games(name=game_name, owner_id=owner_id, include_private=True)[0]

        fe.join_game(user_id=user2_id, game_id=game_db.id)
        fe.join_game(user_id=user3_id, game_id=game_db.id)
        # Owner is also a participant

        all_participants = fe.get_all_participants(game_id=game_db.id)
        assert len(all_participants) == 3
        participant_user_ids = {p.user_id for p in all_participants}
        assert owner_id in participant_user_ids
        assert user2_id in participant_user_ids
        assert user3_id in participant_user_ids

    def test_get_all_participants_no_participants_other_than_owner_initially(self, fe: Frontend):
        owner_id = 10
        game_name = "OnlyOwnerGame"
        fe.new_game(user_id=owner_id, name=game_name, start_date="2025-07-01")
        game_db = fe.be.get_many_games(name=game_name, owner_id=owner_id, include_private=True)[0]
        # Owner is automatically added as a participant

        all_participants = fe.get_all_participants(game_id=game_db.id)
        assert len(all_participants) == 1
        assert all_participants[0].user_id == owner_id
        
    def test_get_all_participants_for_non_existent_game(self, fe: Frontend):
        # Backend.get_many_participants with a non-existent game_id will return an empty tuple
        # So this should not raise an error, but return an empty list/tuple.
        with pytest.raises(LookupError, match='No items found'):
            participants = fe.get_all_participants(game_id=999)
