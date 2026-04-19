"""SessionManager + create_session."""
import secrets
from src.config.settings import Settings


class SessionManager:
    def __init__(self):
        self.sessions = {}

    def get(self, token):
        return self.sessions.get(token)

    def invalidate(self, token):
        self.sessions.pop(token, None)


def create_session(email: str):
    token = secrets.token_urlsafe(32)
    settings = Settings()
    manager = SessionManager()
    manager.sessions[token] = {"email": email, "ttl": settings.session_ttl}
    return type("Session", (), {"token": token, "email": email})
