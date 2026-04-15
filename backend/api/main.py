"""FastAPI main application for Helpyy Hand."""

import logging
import os

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Configure logging so Docker logs show agent activity
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

from backend.api.routers import chat, onboarding, scoring, notifications
from backend.api.routers import observability

from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from backend.api.middleware.rate_limiter import limiter

app = FastAPI(
    title="Helpyy Hand API",
    description="Multi-agent financial inclusion platform for BBVA Colombia",
    version="0.1.0",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# PII filter — tokenizes before agents, detokenizes after
from backend.api.middleware.pii_filter import PIIFilterMiddleware
app.add_middleware(PIIFilterMiddleware)

# Routers
app.include_router(chat.router, prefix="/api/v1", tags=["chat"])
app.include_router(onboarding.router, prefix="/api/v1/onboarding", tags=["onboarding"])
app.include_router(scoring.router, prefix="/api/v1", tags=["scoring"])
app.include_router(notifications.router, prefix="/api/v1", tags=["notifications"])
app.include_router(observability.router, prefix="/api/v1", tags=["observability"])


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "helpyy-hand-api"}
