import pytest
from stocks import Backend 

# This will be the fixed timestamp used by the mocked _iso8601
MOCK_DATETIME_STR = "2025-05-21 10:00:00"

class TestBackend:
    """Tests all user methods, and then mostly add methods"""

    def test_add_user_success(self, be: Backend):
        """Test successfully adding a new user."""
        user_id = 101
        display_name = 'TestUser101'
        source = 'discord'
        permissions = 210

        be.add_user(
            user_id=user_id,
            source=source,
            display_name=display_name,
            permissions=permissions
        )
        user = be.get_user(user_id=user_id)
        assert user is not None, "User should be found in the database."
        assert user['id'] == user_id
        assert user['username'] == display_name, "Display name should match."
        assert user['source'] == source
        assert user['permissions'] == permissions
        assert user['creation_date'] == MOCK_DATETIME_STR, "Creation date should match the mocked timestamp."

    def test_add_user_duplicate_id(self, be: Backend):
        """Test adding a user with an ID that already exists."""
        user_id = 102
        be.add_user(user_id=user_id, source='discord', display_name='OriginalUser')

        with pytest.raises(ValueError, match=f'User with ID {user_id} already exists.'):
            be.add_user(user_id=user_id, source='discord', display_name='DuplicateUser')

    def test_get_user_not_found(self, be: Backend):
        """Test getting a user that does not exist."""
        non_existent_user_id = 999
        with pytest.raises(LookupError, match='User not found.'):
            be.get_user(user_id=non_existent_user_id)

    def test_get_many_users_empty(self, be: Backend):
        """Test getting users when the users table is empty."""
        users = be.get_many_users()
        assert isinstance(users, tuple), "Should return a tuple."
        assert len(users) == 0, "Should return an empty tuple if no users exist."

    def test_get_many_users_with_data(self, be: Backend):
        """Test getting multiple users. 👥"""
        user_data = [
            {'user_id': 201, 'source': 'A', 'display_name': 'Alice', 'permissions': 200},
            {'user_id': 202, 'source': 'B', 'display_name': 'Bob', 'permissions': 210},
            {'user_id': 203, 'source': 'A', 'display_name': 'Charlie', 'permissions': 220},
        ]
        for data in user_data:
            be.add_user(**data)

        users = be.get_many_users()
        assert len(users) == len(user_data), "Should return all added users."

        retrieved_ids = {user['id'] for user in users}
        expected_ids = {data['user_id'] for data in user_data}
        assert retrieved_ids == expected_ids, "All user IDs should be present."

        # Check if display names are correctly retrieved (and reformatted to 'username')
        retrieved_usernames = {user['username'] for user in users}
        expected_usernames = {data['display_name'] for data in user_data}
        assert retrieved_usernames == expected_usernames

    def test_get_many_users_ids_only(self, be: Backend):
        """Test getting only user IDs."""
        be.add_user(user_id=301, source='X', display_name='UserX')
        be.add_user(user_id=302, source='Y', display_name='UserY')

        user_ids = be.get_many_users(ids_only=True)
        assert isinstance(user_ids, tuple), "Should return a tuple of IDs."
        assert len(user_ids) == 2
        assert set(user_ids) == {301, 302}, "Set of IDs should match."

    def test_update_user_success(self, be: Backend):
        """Test successfully updating an existing user's details."""
        user_id = 401
        be.add_user(
            user_id=user_id,
            source='initial_source',
            display_name='OldName',
            permissions=100
        )

        new_display_name = 'NewName'
        new_permissions = 150
        be.update_user(
            user_id=user_id,
            display_name=new_display_name,
            permissions=new_permissions
        )

        user = be.get_user(user_id=user_id)
        assert user['username'] == new_display_name, "Display name should be updated."
        assert user['permissions'] == new_permissions, "Permissions should be updated."
        assert user['source'] == 'initial_source', "Source should remain unchanged if not specified in update."

    def test_update_user_partial_update(self, be: Backend):
        """Test updating only specific fields of a user."""
        user_id = 402
        initial_permissions = 200
        be.add_user(
            user_id=user_id,
            source='test_source',
            display_name='OriginalDisplayName',
            permissions=initial_permissions
        )

        new_display_name = 'UpdatedDisplayNameOnly'
        be.update_user(user_id=user_id, display_name=new_display_name)

        user = be.get_user(user_id=user_id)
        assert user['username'] == new_display_name
        assert user['permissions'] == initial_permissions, "Permissions should not change if not specified."

    def test_update_user_non_existent(self, be: Backend):
        """Test updating a user that does not exist.
        
        The Backend.update_user method currently raises a generic Exception
        if the SqlHelper's update operation fails (e.g., returns status != 'success').
        It doesn't specifically check if 0 rows were affected for a 'success' status.
        This test assumes SqlHelper.update will return 'success' even if no rows are updated.
        If SqlHelper signals failure on 0 affected rows, this test might need adjustment.
        """
        non_existent_user_id = 998
        try:
            be.update_user(user_id=non_existent_user_id, display_name='GhostUser')
            # If SqlHelper.update returns 'success' with 0 rows affected, no exception might be raised by Backend.
            # To confirm, try to get the user (it shouldn't exist).
            with pytest.raises(LookupError):
                be.get_user(user_id=non_existent_user_id)
        except Exception as e:
            # If your SqlHelper or Backend is designed to raise an error for non-existent updates:
            pytest.fail(f"Update on non-existent user raised an unexpected exception: {e}")

    def test_remove_user_success(self, be: Backend):
        """Test successfully removing an existing user."""
        user_id = 501
        be.add_user(user_id=user_id, source='temp_source', display_name='UserToRemove')

        # Verify user exists before removal
        assert be.get_user(user_id=user_id) is not None

        be.remove_user(user_id=user_id)

        with pytest.raises(LookupError, match='User not found.'):
            be.get_user(user_id=user_id)

    def test_remove_user_non_existent(self, be: Backend):
        """Test removing a user that does not exist.
        
        Similar to update_user, Backend.remove_user raises a generic Exception
        if the SqlHelper's delete operation indicates failure.
        If SqlHelper returns 'success' even with 0 rows affected, Backend might not raise.
        """
        non_existent_user_id = 997
        try:
            be.remove_user(user_id=non_existent_user_id)
            # No exception is expected if SqlHelper reports success on 0 rows deleted.
        except Exception as e:
            # If your setup is stricter:
            pytest.fail(f"Remove on non-existent user raised an unexpected exception: {e}")

      
    # # GAMES # #
    def test_add_game_success(self, be: Backend):
        """Test successfully adding a new game."""
        user_id = 101
        name = 'testgame'
        start_date = '2024-04-02'
        end_date = '2024-05-02'
        starting_money = 1000
        total_picks = 10
        be.add_user(user_id=user_id, source='discord') # Must add a user or it gets mad

        be.add_game(
            user_id=int(user_id),
            name=str(name), 
            start_date=str(start_date), 
            end_date=str(end_date), 
            starting_money=float(starting_money), 
            total_picks=int(total_picks), 
        )
        game = be.get_many_games(owner_id=user_id, name=name)[0]
        assert game['id'] == 1 # First game should get ID 1
        assert game['name'] == name # First game should get ID 1
        assert game['start_date'] == start_date # First game should get ID 1
        assert game['end_date'] == end_date # First game should get ID 1
        assert game['starting_money'] == starting_money # First game should get ID 1
        assert game['total_picks'] == total_picks # First game should get ID 1
        
    def test_add_game_infinite_success(self, be: Backend):
        """Test successfully adding a new game with no end date."""
        user_id = 101
        name = 'testgame'
        start_date = '2024-04-02'
        starting_money = 1000
        total_picks = 10
        be.add_user(user_id=user_id, source='discord') # Must add a user or it gets mad

        be.add_game(
            user_id=int(user_id),
            name=str(name), 
            start_date=str(start_date), 
            starting_money=float(starting_money), 
            total_picks=int(total_picks), 
        )
        game = be.get_many_games(owner_id=user_id, name=name)[0]
        assert game['id'] == 1 # First game should get ID 1
        assert game['name'] == name # First game should get ID 1
        assert game['start_date'] == start_date # First game should get ID 1
        assert game['starting_money'] == starting_money # First game should get ID 1
        assert game['total_picks'] == total_picks # First game should get ID 1
    
    def test_add_game_duplicate_name(self, be: Backend):
        """Test successfully adding a new game."""
        user_id = 101
        name = 'testgame'
        start_date = '2024-04-02'
        end_date = '2024-05-02'
        starting_money = 1000
        total_picks = 10
        be.add_user(user_id=user_id, source='discord') # Must add a user or it gets mad

        be.add_game(
            user_id=int(user_id),
            name=str(name), 
            start_date=str(start_date), 
            end_date=str(end_date), 
            starting_money=float(starting_money), 
            total_picks=int(total_picks), 
        ) 
        game = be.get_many_games(owner_id=user_id, name=name)[0] # Confirm first game works
        assert game['id'] == 1 # First game should get ID 1
        assert game['name'] == name # First game should get ID 1
        assert game['start_date'] == start_date # First game should get ID 1
        assert game['end_date'] == end_date # First game should get ID 1
        assert game['starting_money'] == starting_money # First game should get ID 1
        assert game['total_picks'] == total_picks # First game should get ID 1
        
        with pytest.raises(Exception, match='Failed to add game.'):
            be.add_game(
                user_id=int(user_id),
                name=str(name), 
                start_date=str(start_date), 
                end_date=str(end_date), 
                starting_money=float(starting_money), 
                total_picks=int(total_picks), 
            )
    
    # # STOCKS # #
    def test_add_stock_success(self, be: Backend):
        # Add a stock
        ticker = 'MSFT'
        exchange = 'REAL'
        company_name = 'MichaelSoft Bindows'
        
        be.add_stock(
            ticker=ticker,
            exchange=exchange,
            company_name=company_name
        )
        stock = be.get_stock(ticker_or_id=ticker)
        assert stock['ticker'] == ticker
        assert stock['exchange'] == exchange
        assert stock['name'] == company_name
        
    def test_add_stock_duplicate(self, be: Backend):
        # Try to add the same stock twice
        ticker = 'MSFT'
        exchange = 'REAL'
        company_name = 'MichaelSoft Bindows'
        
        be.add_stock(
            ticker=ticker,
            exchange=exchange,
            company_name=company_name
        )
        with pytest.raises(ValueError): # Expect value error
            be.add_stock(
                ticker=ticker,
                exchange=exchange,
                company_name=company_name
            )
        
    # # STOCK PRICES # #
    def test_add_stock_price_ticker_success(self, be: Backend): # Add by ticker
        ticker = 'MSFT'
        s_price = 1203.2333
        d_datetime='2025-05-21 10:00:00'
        be.add_stock( # Need a stock for this
            ticker=ticker,
            exchange='REAL',
            company_name='MichaelSoft Bindows'
        )
        
        be.add_stock_price(
            ticker_or_id=ticker,
            price=s_price,
            datetime=d_datetime
        )
        price = be.get_stock_price(price_id=1) # Only 1 item.
        assert price['stock_id'] == 1
        assert price['price'] == s_price
        assert price['datetime'] == d_datetime
    
    def test_add_stock_price_id_success(self, be: Backend): # Add by ID
        ticker = 'MSFT'
        s_price = 1203.2333
        d_datetime='2025-05-21 10:00:00'
        be.add_stock( # Need a stock for this
            ticker=ticker,
            exchange='REAL',
            company_name='MichaelSoft Bindows'
        )
        
        be.add_stock_price( # There should only be 1 stock
            ticker_or_id=1, 
            price=s_price,
            datetime=d_datetime
        )
        price = be.get_stock_price(price_id=1) # Only 1 item.
        assert price['stock_id'] == 1
        assert price['price'] == s_price
        assert price['datetime'] == d_datetime
    
    def test_add_stock_price_invalid_stock(self, be: Backend): # Stock ID isn't real
        s_price = 1203.2333
        d_datetime='2025-05-21 10:00:00'
        
        with pytest.raises(LookupError, match='Stock not found.'):
            be.add_stock_price( # There should only be 1 stock
                ticker_or_id=1, 
                price=s_price,
                datetime=d_datetime
            )

        