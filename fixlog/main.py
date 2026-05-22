from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from fixlog.api import confirm, entries, feed, questions, sandbox, search, sessions, verifications
from fixlog.config import get_settings
from fixlog.db.seed import seed_accounts_from_settings
from fixlog.db.session import SessionLocal
from fixlog.web import routes as web_routes
from fixlog.workers.verifier import VerifierWorker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def build_lifespan(
    seed_accounts: bool,
    start_verifier: bool,
    verifier_worker: VerifierWorker | None = None,
) -> object:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        worker: VerifierWorker | None = None
        if seed_accounts:
            settings = get_settings()
            with SessionLocal() as db:
                seed_accounts_from_settings(db, settings)
        if start_verifier:
            settings = get_settings()
            worker = verifier_worker or VerifierWorker(
                session_factory=SessionLocal,
                allowed_images=settings.sandbox_allowed_images,
                queue_size=settings.fixlog_sandbox_queue_size,
                timeout_s=settings.fixlog_sandbox_timeout_s,
                memory_mb=settings.fixlog_sandbox_memory_mb,
            )
            app.state.verifier_worker = worker
            await worker.start()
            logger.info(
                "verifier worker started queue_size=%s allowed_images=%s",
                settings.fixlog_sandbox_queue_size,
                ",".join(sorted(settings.sandbox_allowed_images)),
            )
        else:
            app.state.verifier_worker = verifier_worker
        try:
            yield
        finally:
            if worker is not None:
                await worker.stop()
                logger.info("verifier worker stopped")

    return lifespan


def create_app(
    seed_accounts: bool = True,
    start_verifier: bool | None = None,
    verifier_worker: VerifierWorker | None = None,
) -> FastAPI:
    should_start_verifier = (
        get_settings().fixlog_verifier_enabled if start_verifier is None else start_verifier
    )
    if verifier_worker is not None:
        should_start_verifier = True
    app = FastAPI(
        title="fixlog",
        lifespan=build_lifespan(seed_accounts, should_start_verifier, verifier_worker),
    )
    app.mount("/static", StaticFiles(directory="fixlog/web/static"), name="static")
    app.include_router(web_routes.router)
    app.include_router(sessions.router)
    app.include_router(entries.router)
    app.include_router(sandbox.router)
    app.include_router(questions.router)
    app.include_router(verifications.router)
    app.include_router(confirm.router)
    app.include_router(feed.router)
    app.include_router(search.router)
    return app


app = create_app()
