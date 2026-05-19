from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from fixlog.api import confirm, entries, feed, questions, search, sessions, verifications
from fixlog.config import get_settings
from fixlog.db.seed import seed_accounts_from_settings
from fixlog.db.session import SessionLocal
from fixlog.web import routes as web_routes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def build_lifespan(seed_accounts: bool) -> object:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if seed_accounts:
            settings = get_settings()
            with SessionLocal() as db:
                seed_accounts_from_settings(db, settings)
        yield

    return lifespan


def create_app(seed_accounts: bool = True) -> FastAPI:
    app = FastAPI(title="fixlog", lifespan=build_lifespan(seed_accounts))
    app.mount("/static", StaticFiles(directory="fixlog/web/static"), name="static")
    app.include_router(web_routes.router)
    app.include_router(sessions.router)
    app.include_router(entries.router)
    app.include_router(questions.router)
    app.include_router(verifications.router)
    app.include_router(confirm.router)
    app.include_router(feed.router)
    app.include_router(search.router)
    return app


app = create_app()
