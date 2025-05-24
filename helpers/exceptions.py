# Exceptions will go here

# # GENERIC # #

class AlreadyExistsError(Exception):
    def __init__(self, table, duplicate, message:str=''):
        self.table = table # Table that item was attempted to add to.
        self.duplicate = duplicate # Item that already exists
        self.message = message
        super().__init__(self.message)
    pass

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
        
