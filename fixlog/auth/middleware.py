from __future__ import annotations

from urllib.parse import quote

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, RedirectResponse, Response

from fixlog.auth.web import account_from_request
from fixlog.config import get_settings
from fixlog.db.session import SessionLocal

PUBLIC_PATHS = (
    "/healthz",
    "/login",
    "/static/",
    "/favicon.ico",
)


class FixlogAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        settings = get_settings()
        if not settings.fixlog_auth_required or _is_public_path(request.url.path):
            return await call_next(request)

        session_factory = getattr(request.app.state, "session_factory", SessionLocal)
        with session_factory() as db:
            account = account_from_request(request, db, settings)
            if account is not None:
                request.state.fixlog_account_id = str(account.id)
                return await call_next(request)

        if _wants_html(request):
            next_path = request.url.path
            if request.url.query:
                next_path = f"{next_path}?{request.url.query}"
            return RedirectResponse(
                url=f"/login?next={quote(next_path, safe='')}",
                status_code=303,
            )
        return JSONResponse({"detail": "Authentication required"}, status_code=401)


def _is_public_path(path: str) -> bool:
    return any(path == item or path.startswith(item) for item in PUBLIC_PATHS)


def _wants_html(request: Request) -> bool:
    accept = request.headers.get("accept", "")
    return "text/html" in accept and "application/json" not in accept
