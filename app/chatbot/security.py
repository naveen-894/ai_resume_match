"""Security helpers for the chatbot API: rate limiting, an internal shared-secret
check, and basic input sanitization.

The backend's global CORS policy (`app/main.py`) currently allows all origins,
which is too broad to rely on alone for a feature that accepts free-text input
and triggers outbound email. The shared-secret header is defense-in-depth on
top of that: the Next.js proxy (the only intended caller) sends it from its
server-side environment, so direct public callers are rate-limited harder and
get no special trust.
"""
import re

from fastapi import Header, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.chatbot import config

limiter = Limiter(key_func=get_remote_address)

# Strip control characters (except newline/tab) that have no business being in
# chat text and are sometimes used in injection/obfuscation attempts.
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def sanitize_text(value: str) -> str:
    return _CONTROL_CHARS.sub("", value).strip()


async def verify_internal_caller(
    x_chatbot_key: str | None = Header(default=None),
) -> None:
    """When CHATBOT_INTERNAL_API_KEY is set, require it on every chatbot request.
    Left optional (no-op) when unset, so local development without the env var
    configured isn't blocked — but production deployments should set it."""
    if config.INTERNAL_API_KEY and x_chatbot_key != config.INTERNAL_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")


def rate_limit_key(request: Request) -> str:
    """Rate-limit per client IP; falls back to a shared bucket if IP is unavailable
    behind a proxy that doesn't forward it (slowapi's get_remote_address already
    reads X-Forwarded-For when present)."""
    return get_remote_address(request)


async def enforce_max_body_size(request: Request) -> None:
    """Rejects oversized requests by Content-Length before the body is parsed,
    independent of per-field validation (defense against large-payload abuse)."""
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > config.MAX_REQUEST_BODY_BYTES:
        raise HTTPException(status_code=413, detail="Request body too large")
