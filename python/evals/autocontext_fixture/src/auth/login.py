"""Login flow: handle_login + validate_credentials."""
from src.auth.session import create_session
from src.db.queries import find_user_by_email
from src.utils.crypto import verify_password


def validate_credentials(email: str, password: str) -> bool:
    user = find_user_by_email(email)
    if not user:
        return False
    return verify_password(password, user.password_hash)


def handle_login(email: str, password: str):
    if not validate_credentials(email, password):
        return {"error": "invalid credentials"}, 401
    session = create_session(email)
    return {"session_token": session.token}, 200
