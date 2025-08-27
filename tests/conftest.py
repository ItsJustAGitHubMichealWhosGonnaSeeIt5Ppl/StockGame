import pytest
import os
import tempfile
# PART GEMINI BUT IT DIDNT REALLY WORK 
MODULE_NAME_FOR_PATCHING = "stocks"

MOCK_DATETIME_STR = "2025-05-21 10:00:00" # Fixed timestamp for tests
MOCK_DATE_STR = "2025-05-21" # Fixed date for tests

@pytest.fixture(scope="function", autouse=True)
def mock_iso8601_fixed(mocker):
    """Mocks the _iso8601 helper for consistent timestamps in Backend methods."""
    def side_effect_iso8601(format_type=None):
        if format_type == 'date':
            return MOCK_DATE_STR
        return MOCK_DATETIME_STR
        
    mocker.patch(f'{MODULE_NAME_FOR_PATCHING}._iso8601', side_effect=side_effect_iso8601)

@pytest.fixture(scope="function")
def db_path():
    """Creates a temporary SQLite database file for each test function."""
    db_fd, path = tempfile.mkstemp(suffix=".sqlite")
    os.close(db_fd)  # SqlHelper will open it
    yield path
    os.unlink(path) # Clean up after the test

@pytest.fixture(scope="function")
def be(db_path):
    """Provides a Backend instance connected to a real, temporary SQLite DB."""
    from sqlite_creator_real import create
    from stocks import Backend    

    create(db_path) # Initialize the schema in the temporary database
    backend = Backend(db_name=db_path)
    return backend

@pytest.fixture(scope="function")
def fe(db_path):
    """Provides a Frontend instance connected to a real, temporary SQLite DB."""
    from sqlite_creator_real import create
    from stocks import Frontend    

    create(db_path) # Initialize the schema in the temporary database
    frontend = Frontend(database_name=db_path, owner_user_id=10, source='testing')
    return frontend