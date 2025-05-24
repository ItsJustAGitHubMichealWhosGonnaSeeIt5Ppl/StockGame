# Exceptions will go here

# # GENERIC # #

class AlreadyExistsError(Exception):
    def __init__(self, table, duplicate, message:str=''):
        self.table = table # Table that item was attempted to add to.
        self.duplicate = duplicate # Item that already exists
        self.message = message
        super().__init__(self.message)

class DoesntExistError(Exception):
    def __init__(self, table, item, message:str=''):
        self.table = table # Table that item was attempted to add to.
        self.item = item # Item that doesn't exist
        self.message = message
        super().__init__(self.message)

class WrongTypeError(Exception): # Something received data of the wrong type
    def __init__(self, table, message:str=''):
        self.table = table
        self.message = message
        super().__init__(self.message)

class AddFailed(Exception):
    def __init__(self, placeholder, message:str):
        self.placeholder = placeholder
        self.message = message
        super().__init__(self.message)
    pass

class GetSingleFailed(Exception):
    def __init__(self, placeholder, message:str):
        self.placeholder = placeholder
        self.message = message
        super().__init__(self.message)
    pass

class GetMultipleFailed(Exception):
    def __init__(self, placeholder, message:str):
        self.placeholder = placeholder
        self.message = message
        super().__init__(self.message)
    pass

class UpdateFailed(Exception):
    def __init__(self, placeholder, message:str):
        self.placeholder = placeholder
        self.message = message
        super().__init__(self.message)
    pass

class RemoveFailed(Exception):
    def __init__(self, placeholder, message:str):
        self.placeholder = placeholder
        self.message = message
        super().__init__(self.message)
    pass

# # USER # #

class UserExistsError(Exception): # User alreadty exists
    def __init__(self, user_id, message:str='User already exists.'):
        self.user_id = user_id
        self.message = message
        super().__init__(self.message)


# # GAME # #
class InvalidDateFormatError(Exception):
    def __init__(self, date_field, message:str=''):
        self.date_field = date_field
        self.message = message
        super().__init__(self.message)
        
        
# # STOCK PICKS # #
class NotAllowedError(Exception): 
    def __init__(self, action:str, reason:str, message:str=''):
        self.action = action
        self.reason = reason
        self.message = message
        super().__init__(self.message)