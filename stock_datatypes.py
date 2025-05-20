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
    
