"""Rate limiting — slowapi wrapper for FastAPI."""
from slowapi import Limiter
from slowapi.util import get_remote_address

# 30 requests/minute per IP on chat, 60 on other endpoints
limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])
