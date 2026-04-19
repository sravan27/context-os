"""Rate-limit tests."""
from src.api.rate_limit import rate_limit_decorator, RATE_LIMIT_CONFIG


def test_rate_limit_config_defaults():
    assert RATE_LIMIT_CONFIG["default_per_minute"] == 60
    assert RATE_LIMIT_CONFIG["login_per_minute"] == 5


def test_rate_limit_decorator_allows_under_cap():
    calls = []

    def handler(req):
        calls.append(req)
        return ({"ok": True}, 200)

    wrapped = rate_limit_decorator(handler, limit=3)
    req = type("Req", (), {"ip": "1.2.3.4"})()
    for _ in range(3):
        _, status = wrapped(req)
        assert status == 200
    _, status = wrapped(req)
    assert status == 429
