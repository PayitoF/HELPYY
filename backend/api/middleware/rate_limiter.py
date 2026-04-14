"""Rate limiting middleware — per-user request throttling."""

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware


class RateLimiterMiddleware(BaseHTTPMiddleware):
    """Rate limiting per user to prevent abuse."""

    async def dispatch(self, request: Request, call_next) -> Response:
        # TODO: extract user_id from request
        # TODO: check rate limit (sliding window)
        # TODO: return 429 if exceeded
        response = await call_next(request)
        return response
