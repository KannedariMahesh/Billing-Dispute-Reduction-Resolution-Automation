from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


class AuditRequestMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Audit-Logged"] = "true"
        return response
