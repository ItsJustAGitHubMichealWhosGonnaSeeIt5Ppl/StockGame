import pytest
from stocks import Frontend # Your Backend class
from datetime import datetime
MOCK_DATETIME_STR = "2025-05-21 10:00:00" # Fixed timestamp for tests


class TestFrontend:
    """Test all (maybe we'll see) frontend methods"""
    
    
    # # NEW_GAME # #
    def test_new_game_minimal_success(self, fe: Frontend):
        user_id = 10 # Matches conftest
        game_name = 'TestGame'
        start_date = '2025-10-10'

        fe.new_game(
            user_id=user_id,
            name=game_name,
            start_date=start_date,
        )
        game = fe.be.get_game(game_id=1)
        assert game.id == 1 # First game should be one
        assert game.owner_id == user_id # First game should be one
        assert game.name == game_name 
        assert game.start_date == datetime.strptime(start_date, "%Y-%m-%d").date() 
        assert game.end_date == None 
    
    def test_new_game_success(self, fe: Frontend):
        user_id = 10 # Matches conftest
        game_name = 'TestGame'
        start_date = '2025-10-10'
        end_date ='2025-10-11'
        starting_money = 1
        pick_date = '2025-10-10'
        total_picks = 40
        draft_mode = False
        sell_during_game = False
        update_frequency = 'hourly'
        
        fe.new_game(
            user_id=user_id,
            name=game_name,
            start_date=start_date,
            end_date=end_date,
            starting_money=starting_money,
            pick_date=pick_date,
            total_picks=total_picks,
            exclusive_picks=draft_mode,
            sell_during_game=sell_during_game,
            update_frequency=update_frequency
        )
        game = fe.be.get_game(game_id=1)
        assert game.id == 1 
        assert game.name == game_name 
        assert game.start_date == datetime.strptime(start_date, "%Y-%m-%d").date() 
        assert game.end_date == datetime.strptime(end_date, "%Y-%m-%d").date() 
        assert game.pick_date == datetime.strptime(pick_date, "%Y-%m-%d").date() 
        assert game.start_money == starting_money 
        assert game.pick_count == total_picks 
        assert game.draft_mode == draft_mode 
        assert game.allow_selling == sell_during_game 
        assert game.update_frequency == update_frequency 
    
    
    # # LIST_GAMES # #    
    def test_list_public_games(self, fe: Frontend):
        user_id = 10 # Matches conftest
        start_date = '2025-10-10'

        fe.new_game( # Create a public game
            user_id=user_id,
            name='PublicGame',
            start_date=start_date,
        )
        fe.new_game( # Create a private game
            user_id=user_id,
            name='PrivateGame',
            start_date=start_date,
            private_game=True
        )
        
        games = fe.list_games(include_private=False)
        assert len(games) == 1 # Only 1 game should be returned
        assert games[0].name == 'PublicGame'
        
    def test_list_all_games(self, fe: Frontend): # Include private ones this time
        user_id = 10 # Matches conftest
        start_date = '2025-10-10'

        fe.new_game( # Create a public game
            user_id=user_id,
            name='PublicGame',
            start_date=start_date,
        )
        fe.new_game( # Create a private game
            user_id=user_id,
            name='PrivateGame',
            start_date=start_date,
            private_game=True
        )
        
        games = fe.list_games(include_private=True)
        assert len(games) == 2 # 2 games should be returned
        assert games[1].name == 'PrivateGame'
        assert games[0].name == 'PublicGame'
        
    def test_list_no_games(self, fe: Frontend): # Include private ones this time
        user_id = 10 # Matches conftest
        start_date = '2025-10-10'
        

        with pytest.raises(LookupError):
            games = fe.list_games(include_private=False)

    
    # # GAME_INFO # #
    
    
    # # REGISTER # #
    def test_register_id_only(self, fe: Frontend):
        user_id = 11
        source = 'testing' # Should be set by class
        fe.register(
            user_id=user_id,
        )
        
        user = fe.be.get_user(user_id=11)
        assert user.id == user_id
        assert user.source == source
        assert user.datetime_created == datetime.strptime(MOCK_DATETIME_STR, "%Y-%m-%d %H:%M:%S"), "Creation date should match the mocked timestamp."    
        
    def test_register_full(self, fe: Frontend):
        user_id = 11
        source = 'manual' # Should be set by class
        fe.register(
            user_id=user_id,
            source=source
        )
        
        user = fe.be.get_user(user_id=11)
        assert user.id == user_id
        assert user.source == source
        assert user.datetime_created == datetime.strptime(MOCK_DATETIME_STR, "%Y-%m-%d %H:%M:%S"), "Creation date should match the mocked timestamp."   
        
    def test_register_duplicate(self, fe: Frontend):
        user_id = 11
        source = 'testing' # Should be set by class
        fe.register(
            user_id=user_id,
            source=source
        )
        
        a = fe.register(
            user_id=user_id,
            source='manual'
        )
        assert a == 'User already registered'

    