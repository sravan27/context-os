"""Session manager tests."""
from src.auth.session import SessionManager, create_session
from src.config.settings import Settings


def test_session_manager_get_missing():
    mgr = SessionManager()
    assert mgr.get("nope") is None


def test_create_session_uses_settings():
    s = create_session("a@b.com")
    assert s.email == "a@b.com"
    assert s.token
    assert isinstance(Settings(), Settings)
