"""User + Session + Token models."""


class User:
    def __init__(self, id, email, password_hash):
        self.id = id
        self.email = email
        self.password_hash = password_hash


class Session:
    def __init__(self, token, user_id, expires_at):
        self.token = token
        self.user_id = user_id
        self.expires_at = expires_at


class Token:
    def __init__(self, value, purpose, user_id):
        self.value = value
        self.purpose = purpose
        self.user_id = user_id
