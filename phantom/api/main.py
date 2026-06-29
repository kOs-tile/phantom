"""
PHANTOM FastAPI Application
Lifespan management: browser session startup/shutdown, queue workers, cache connection.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from phantom.browser.session import BrowserSession
from phantom.cache.result_store import ResultStore
from phantom.config import settings
from phantom.queue.task_queue import TaskQueue


# ── Global application state ─────────────────────────────────────────────────

browser_session: BrowserSession = BrowserSession()
task_queue: TaskQueue = TaskQueue()
result_store: ResultStore = ResultStore()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: start services on startup, clean up on shutdown."""
    logger.info("PHANTOM starting up...")

    # Connect cache (non-fatal if Redis unavailable)
    await result_store.connect()

    # Start task queue workers
    await task_queue.start()

    # Start browser session
    try:
        await browser_session.start()
        logger.info("PHANTOM browser session ready")
    except Exception as exc:
        logger.warning(
            "Browser session failed to start (running without browser): {}",
            exc,
        )

    logger.info(
        "PHANTOM ready — API at {}:{}, browser={}, cache={}",
        settings.api_host,
        settings.api_port,
        browser_session.is_running,
        result_store.backend,
    )

    yield  # Application runs here

    logger.info("PHANTOM shutting down...")
    await task_queue.stop()
    await browser_session.stop()
    await result_store.disconnect()
    logger.info("PHANTOM shutdown complete")


# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="PHANTOM — Hermes Agent Stealth Browser Engine",
    description=(
        "Production-grade stealth browser automation engine for Hermes agents. "
        "Browse, scrape, and extract structured data from any website while "
        "mimicking real human behavior to bypass anti-bot systems."
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Mount routes ──────────────────────────────────────────────────────────────

from phantom.api.routes import router  # noqa: E402

app.include_router(router)


# ── Entrypoint ────────────────────────────────────────────────────────────────

def serve() -> None:
    """Start the PHANTOM API server."""
    uvicorn.run(
        "phantom.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        log_level=settings.log_level.lower(),
        reload=False,
    )


if __name__ == "__main__":
    serve()
