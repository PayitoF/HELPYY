"""JWT authentication middleware."""

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware


class AuthMiddleware(BaseHTTPMiddleware):
    """JWT token validation for protected endpoints."""

    async def dispatch(self, request: Request, call_next) -> Response:
        # TODO: extract JWT from Authorization header
        # TODO: validate token, extract user_id
        # TODO: attach user to request state
        response = await call_next(request)
        return response
