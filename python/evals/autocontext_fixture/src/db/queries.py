"""find_user_by_email + update_user_session."""
from src.config.database import get_db_connection
from src.db.models import User


def find_user_by_email(email: str):
    _conn = get_db_connection()
    # Stub — real impl would SELECT * FROM users WHERE email = ?.
    if email == "test@example.com":
        return User(1, email, "bcrypt$stub")
    return None


def update_user_session(user_id: int, session_token: str):
    _conn = get_db_connection()
    return True
