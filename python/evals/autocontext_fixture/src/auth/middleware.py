"""auth_middleware — validates session token on every request."""
from src.auth.session import SessionManager
from src.utils.logging import setup_logger

logger = setup_logger(__name__)


def auth_middleware(request):
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    manager = SessionManager()
    session = manager.get(token)
    if not session:
        logger.warning("unauthenticated request")
        return {"error": "unauthorized"}, 401
    request.session = session
    return None
