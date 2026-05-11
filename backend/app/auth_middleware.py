"""Mechanical authentication gate — every request to ``/api/*`` carries a
valid session cookie or returns 401, with a small whitelist for the auth
routes themselves and the health probe.

Routes that need the current user object should still take
``current_user: User = Depends(get_current_user)`` in their signature.
This middleware only enforces presence + validity of the cookie; the
dependency resolves the user object lazily inside the handler.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.auth import SESSION_COOKIE, verify_session

_PUBLIC_PATH_EXACT = frozenset({
    "/health",
    "/openapi.json",
    "/docs",
    "/redoc",
    "/favicon.ico",
})

_PUBLIC_PATH_PREFIXES = (
    "/api/auth/",
    "/docs/",
    "/redoc/",
)


def _is_public(path: str) -> bool:
    if path in _PUBLIC_PATH_EXACT:
        return True
    return any(path.startswith(p) for p in _PUBLIC_PATH_PREFIXES)


class AuthRequiredMiddleware(BaseHTTPMiddleware):
    """Block unauthenticated requests at the edge.

    OPTIONS (CORS preflight) and the public-path whitelist pass through.
    Everything else needs a valid HMAC-signed session cookie.
    """

    async def dispatch(self, request: Request, call_next):
        if request.method == "OPTIONS":
            return await call_next(request)
        if _is_public(request.url.path):
            return await call_next(request)

        token = request.cookies.get(SESSION_COOKIE) or ""
        data_dir = Path(request.app.state.data_dir)
        if not verify_session(token, data_dir):
            return JSONResponse(
                status_code=401,
                content={"detail": "Authentication required"},
            )

        return await call_next(request)
