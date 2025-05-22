import pytest
from stocks import Frontend # Your Backend class

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
        assert game['id'] == 1 # First game should be one
        assert game['owner'] == user_id # First game should be one
        assert game['name'] == game_name 
        assert game['start_date'] == start_date 
        assert game['end_date'] == None 
    
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
        assert game['id'] == 1 # First game should get ID 1
        assert game['name'] == game_name # First game should get ID 1
        assert game['start_date'] == start_date # First game should get ID 1
        assert game['end_date'] == end_date # First game should get ID 1
        assert game['starting_money'] == starting_money # First game should get ID 1
        assert game['pick_date'] == pick_date # First game should get ID 1
        assert game['total_picks'] == total_picks # First game should get ID 1
        assert game['exclusive_picks'] == draft_mode # First game should get ID 1
        assert game['sell_during_game'] == sell_during_game # First game should get ID 1
        assert game['update_frequency'] == update_frequency # First game should get ID 1
    
    
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
        assert games[0]['name'] == 'PublicGame'
        
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
        assert games[1]['name'] == 'PrivateGame'
        assert games[0]['name'] == 'PublicGame'
        
    def test_list_no_games(self, fe: Frontend): # Include private ones this time
        user_id = 10 # Matches conftest
        start_date = '2025-10-10'
        
        fe.new_game( # Create a private game
            user_id=user_id,
            name='PrivateGame',
            start_date=start_date,
            private_game=True
        )
        
        games = fe.list_games(include_private=False)
        assert len(games) == 0 # no games should be returned

    
    # # GAME_INFO # #
    
    
    # # REGISTER # #