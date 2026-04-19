"""Login endpoint tests."""
from src.auth.login import handle_login, validate_credentials
from src.api.rate_limit import rate_limit_decorator


def test_handle_login_rejects_bad_password():
    body, status = handle_login("test@example.com", "wrong")
    assert status == 401


def test_rate_limit_wraps_handler():
    wrapped = rate_limit_decorator(handle_login, limit=1)
    assert callable(wrapped)
