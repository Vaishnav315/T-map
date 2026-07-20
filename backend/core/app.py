"""
SentinelIQ AI Safety Platform — FastAPI Application Factory
======================================================
Production-hardened app: env-driven CORS, lifespan events,
startup validation, and structured logging.
"""

import sys
import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

# ── Logging setup ────────────────────────────────────────────────────────────
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("vigil.app")

# ── Startup Validation ───────────────────────────────────────────────────────
def _validate_env():
    """Fail fast if critical environment variables are missing or insecure."""
    secret_key = os.getenv("SECRET_KEY", "")
    if not secret_key or secret_key.startswith("CHANGE_ME"):
        raise EnvironmentError(
            "[SentinelIQ STARTUP] FATAL: SECRET_KEY is not set or is using the default placeholder.\n"
            "  Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\"\n"
            "  Then set it in your .env file."
        )

    internal_secret = os.getenv("INTERNAL_YOLO_SECRET", "")
    if not internal_secret or internal_secret.startswith("CHANGE_ME"):
        raise EnvironmentError(
            "[SentinelIQ STARTUP] FATAL: INTERNAL_YOLO_SECRET is not set.\n"
            "  Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(32))\"\n"
            "  Then set it in your .env file."
        )

    logger.info("[SentinelIQ] Environment validation passed.")


# ── Application Lifespan ─────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Unified startup/shutdown lifecycle manager (replaces deprecated on_event)."""
    # ── STARTUP ──
    logger.info("=" * 60)
    logger.info("  SentinelIQ AI Safety Platform — Server Starting")
    logger.info("=" * 60)

    try:
        _validate_env()
    except EnvironmentError as e:
        logger.critical(str(e))
        sys.exit(1)

    try:
        from backend.core.state import start_state_updater, initialize_state
        from backend.core.config_loader import loader
        from backend.core.database import ensure_schema

        # Initialize DB tables (runs migrations if needed)
        ensure_schema()
        logger.info("[SentinelIQ] Database schema verified.")

        # Initialize camera state
        registry = loader.get_camera_registry()
        initialize_state(registry)
        logger.info(f"[SentinelIQ] Camera state initialized — {len(registry)} cameras loaded.")

        # Start background workers
        start_state_updater()
        logger.info("[SentinelIQ] Background state updater and VLM queue started.")
    except Exception as e:
        logger.error(f"[SentinelIQ STARTUP ERROR] {e}", exc_info=True)

    yield  # ← Application runs here

    # ── SHUTDOWN ──
    logger.info("[SentinelIQ] Server shutting down gracefully.")


# ── Application Factory ──────────────────────────────────────────────────────
def create_app() -> FastAPI:
    """Factory function to create and configure the production FastAPI app."""

    app = FastAPI(
        title="SentinelIQ AI Safety Platform",
        description=(
            "Production-grade industrial AI safety monitoring platform. "
            "Multi-camera RTSP ingestion, YOLOv8 + ByteTrack tracking, "
            "homography perspective projection, and 4-tier VLM alert verification."
        ),
        version="1.0.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    # ── CORS Middleware ───────────────────────────────────────────────────────
    raw_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000")
    allowed_origins = [o.strip() for o in raw_origins.split(",") if o.strip()]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Tenant-ID"],
        expose_headers=["X-Request-ID"],
    )
    logger.info(f"[SentinelIQ] CORS configured for origins: {allowed_origins}")

    # ── Register API Routes ───────────────────────────────────────────────────
    from backend.api.routes import api_router
    from backend.api.saas_routes import saas_router
    from backend.api.integration_routes import integration_router

    app.include_router(api_router)
    app.include_router(saas_router)
    app.include_router(integration_router)

    # ── Health check (unauthenticated, for load balancers) ───────────────────
    @app.get("/health", tags=["System"])
    async def health_check():
        return {"status": "ok", "service": "SentinelIQ AI Safety Platform", "version": "1.0.0"}

    return app


app = create_app()
