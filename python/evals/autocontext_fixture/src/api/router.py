"""APIRouter — imports auth middleware, registers endpoints."""
from src.auth.middleware import auth_middleware
from src.auth.login import handle_login
from src.api.rate_limit import rate_limit_decorator


class APIRouter:
    def __init__(self):
        self.routes = {}

    def add(self, path, handler):
        self.routes[path] = handler

    def dispatch(self, request):
        err = auth_middleware(request)
        if err:
            return err
        handler = self.routes.get(request.path)
        if not handler:
            return {"error": "not found"}, 404
        return handler(request)


def build_router():
    router = APIRouter()
    router.add("/login", rate_limit_decorator(handle_login))
    return router
