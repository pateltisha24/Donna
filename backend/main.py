"""
Donna backend — FastAPI entry point.

Starts the FastAPI app, mounts all routes, and kicks off APScheduler.
"""

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import get_sessions, router
from scheduler.jobs import start_scheduler, stop_scheduler

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger("donna.main")

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="Donna", description="Your AI personal secretary", version="1.0.0")

# Allow the Next.js frontend to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # credentials not required — wildcard is safe here
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

# ---------------------------------------------------------------------------
# Startup / shutdown
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def on_startup():
    logger.info("Donna backend starting up…")
    # Ensure data directory exists
    db_path = os.getenv("SQLITE_DB_PATH", "./data/donna.db")
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    # Start APScheduler, passing the session store getter
    start_scheduler(get_sessions)
    logger.info("Donna backend ready.")


@app.on_event("shutdown")
async def on_shutdown():
    logger.info("Donna backend shutting down…")
    stop_scheduler()
