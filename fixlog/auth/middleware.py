from __future__ import annotations

from urllib.parse import quote

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, RedirectResponse, Response

from fixlog.auth.web import account_from_request
from fixlog.config import get_settings
from fixlog.db.session import SessionLocal

PUBLIC_EXACT_PATHS = (
    "/",
    "/agent",
    "/healthz",
    "/install.sh",
    "/login",
    "/skill.md",
    "/favicon.ico",
)
PUBLIC_PREFIX_PATHS = ("/static/",)
PUBLIC_HTML_EXACT_PATHS = (
    "/partials/feed-list",
)


class FixlogAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        settings = get_settings()
        if not settings.fixlog_auth_required or _is_public_path(request):
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


def _is_public_path(request: Request) -> bool:
    path = request.url.path
    if path in PUBLIC_EXACT_PATHS or any(
        path.startswith(item) for item in PUBLIC_PREFIX_PATHS
    ):
        return True
    if request.method == "GET" and path in PUBLIC_HTML_EXACT_PATHS:
        return True
    # Collector write endpoints own bearer-token validation in route dependencies.
    # Let them receive scoped device tokens without granting those tokens dashboard access.
    return (
        path == "/collector/status"
        or path == "/collector/issues"
        or path == "/sessions/start"
        or (path.startswith("/sessions/") and path.endswith("/heartbeat"))
        or (path.startswith("/sessions/") and path.endswith("/events"))
    )


def _wants_html(request: Request) -> bool:
    accept = request.headers.get("accept", "")
    return "text/html" in accept and "application/json" not in accept
