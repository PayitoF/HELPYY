"""PII filter middleware — tokenizes PII before agents, detokenizes after.

Intercepts JSON request bodies containing a "content" or "message" field,
tokenizes any PII found, and detokenizes the response before returning.
"""

import json
import uuid

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from backend.security.pii_tokenizer import tokenize_pii
from backend.security.pii_detokenizer import detokenize_response, get_vault
from backend.security.audit_logger import log_pii_access

# Paths that should NOT be filtered (health checks, static, etc.)
# /api/v1/chat is handled by the chat router directly (it needs the
# original untokenized message for OnboardingAgent data extraction).
_SKIP_PREFIXES = ("/health", "/docs", "/openapi.json", "/redoc",
                  "/api/v1/chat", "/api/v1/onboarding")


class PIIFilterMiddleware(BaseHTTPMiddleware):
    """Middleware that intercepts ALL incoming messages to tokenize PII
    before they reach any agent, and detokenizes responses before
    sending to the frontend.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        if any(path.startswith(p) for p in _SKIP_PREFIXES):
            return await call_next(request)

        # --- Tokenize request body ---
        session_id = request.headers.get("X-Session-ID", str(uuid.uuid4()))

        if request.method in ("POST", "PUT", "PATCH"):
            body_bytes = await request.body()
            if body_bytes:
                try:
                    body = json.loads(body_bytes)
                    body, session_id = await _tokenize_body(body, session_id)
                    # Replace the request body with the tokenized version
                    request._body = json.dumps(body, ensure_ascii=False).encode()
                except (json.JSONDecodeError, UnicodeDecodeError):
                    pass  # Not JSON — pass through

        # Store session_id on request state for downstream use
        request.state.session_id = session_id

        # --- Call the actual endpoint ---
        response = await call_next(request)

        # --- Detokenize response body ---
        if response.headers.get("content-type", "").startswith("application/json"):
            resp_body = b""
            async for chunk in response.body_iterator:
                if isinstance(chunk, str):
                    resp_body += chunk.encode()
                else:
                    resp_body += chunk

            try:
                resp_data = json.loads(resp_body)
                resp_data = _detokenize_body(resp_data, session_id)
                new_body = json.dumps(resp_data, ensure_ascii=False).encode()
                return Response(
                    content=new_body,
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    media_type="application/json",
                )
            except (json.JSONDecodeError, UnicodeDecodeError):
                return Response(
                    content=resp_body,
                    status_code=response.status_code,
                    headers=dict(response.headers),
                )

        return response


async def _tokenize_body(body: dict, session_id: str) -> tuple[dict, str]:
    """Tokenize PII in known text fields and store mapping in vault."""
    # Extract session_id from body if present
    session_id = body.get("session_id", session_id)

    text_fields = ("content", "message", "text")
    vault = get_vault()

    for field in text_fields:
        if field in body and isinstance(body[field], str):
            tokenized, mapping = tokenize_pii(body[field])
            if len(mapping) > 1:  # more than just _types
                vault.store(session_id, mapping)
                for token in mapping:
                    if token != "_types":
                        log_pii_access(session_id, "tokenize", token, "request_middleware")
            body[field] = tokenized

    return body, session_id


def _detokenize_body(body: dict, session_id: str) -> dict:
    """Detokenize PII tokens in known response text fields."""
    text_fields = ("content", "message", "text", "response", "body")
    for field in text_fields:
        if field in body and isinstance(body[field], str):
            body[field] = detokenize_response(body[field], session_id)
    return body
