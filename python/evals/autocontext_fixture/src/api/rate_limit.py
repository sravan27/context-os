"""rate_limit_decorator + RATE_LIMIT_CONFIG."""
import time
from collections import defaultdict

RATE_LIMIT_CONFIG = {
    "default_per_minute": 60,
    "login_per_minute": 5,
    "burst": 10,
}

_request_log = defaultdict(list)


def rate_limit_decorator(handler, limit=None):
    cap = limit or RATE_LIMIT_CONFIG["default_per_minute"]

    def wrapped(request):
        key = getattr(request, "ip", "unknown")
        now = time.time()
        _request_log[key] = [t for t in _request_log[key] if now - t < 60]
        if len(_request_log[key]) >= cap:
            return {"error": "rate limited"}, 429
        _request_log[key].append(now)
        return handler(request)

    return wrapped
