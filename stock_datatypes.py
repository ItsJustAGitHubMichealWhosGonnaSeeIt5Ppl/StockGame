from typing import TypedDict, Literal



# # SQL HELPER STUFF # #
#TODO maybe there is a way to use this
QueryModes = Literal['get', 'insert', 'update', 'delete', 'raw-get']
Statuses = Literal['success', 'error']

class Status(TypedDict): # Status item
    status: str
    reason: str
    result: str | int | dict | tuple | Exception | None
    more_info: str | int | dict | tuple | Exception | None
    
class Games(TypedDict):
    id: int
    name: str
    owner: int
    starting_money: float
    total_picks: int
    pick_date: str
    exclusive_picks: bool
    private_game: bool
    sell_during_game: bool
    update_frequency: str
    start_date: str
    end_date: str
    status: str
    creation_date: str
    combined_value: float
    