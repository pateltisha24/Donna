"""
Donna backend — FastAPI entry point.

Starts the FastAPI app, mounts all routes, and kicks off APScheduler.
"""

import logging
import os

from dotenv import load_dotenv

# Load .env (project root) for local dev; in Docker, env_file already sets these.
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import router
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

# Allowed origins are configurable; defaults to local dev frontend.
# Set CORS_ALLOW_ORIGINS to a comma-separated list in production.
_origins = os.getenv("CORS_ALLOW_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
allowed_origins = [o.strip() for o in _origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
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

    # Start APScheduler (jobs persist briefings to the default session)
    start_scheduler()
    logger.info("Donna backend ready.")


@app.on_event("shutdown")
async def on_shutdown():
    logger.info("Donna backend shutting down…")
    stop_scheduler()
