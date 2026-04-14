"""FastAPI main application for Helpyy Hand."""

import logging
import os

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

app = FastAPI(
    title="Helpyy Hand API",
    description="Multi-agent financial inclusion platform for BBVA Colombia",
    version="0.1.0",
)

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

# TODO: Add rate limiter middleware
# TODO: Add auth middleware

# Routers
app.include_router(chat.router, prefix="/api/v1", tags=["chat"])
app.include_router(onboarding.router, prefix="/api/v1/onboarding", tags=["onboarding"])
app.include_router(scoring.router, prefix="/api/v1", tags=["scoring"])
app.include_router(notifications.router, prefix="/api/v1", tags=["notifications"])


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "helpyy-hand-api"}
