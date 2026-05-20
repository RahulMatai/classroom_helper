# app/main.py
# ════════════════════════════════════════════════
# FastAPI Application Entry Point
#
# WHY THIS FILE EXISTS:
# This is where the app starts.
# Sets up FastAPI, connects all routes,
# starts Telegram bot, checks all services.
#
# TO RUN:
# uvicorn app.main:app --reload
# ════════════════════════════════════════════════

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.logger import setup_logging, get_logger
from app.core.events import check_redis_connection
from app.db.session import check_db_connection, create_tables
from app.channels.telegram import create_telegram_app

log = get_logger(__name__)


# ── Lifespan ──────────────────────────────────────
# Runs on startup and shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup and shutdown logic.
    Checks all services are running before
    accepting any requests.
    """
    # ── Startup ───────────────────────────────────
    setup_logging(
        log_level="DEBUG" if settings.DEBUG else "INFO",
        json_logs=settings.is_production
    )

    log.info("app_starting",
             app_name=settings.APP_NAME,
             env=settings.APP_ENV)

    # Check database
    db_ok = check_db_connection()
    if not db_ok:
        log.error("startup_failed_db")
        raise RuntimeError("Database connection failed")

    # Check Redis
    redis_ok = check_redis_connection()
    if not redis_ok:
        log.error("startup_failed_redis")
        raise RuntimeError("Redis connection failed")

    # Create tables if not exist
    create_tables()

    log.info("app_started_successfully",
             app_name=settings.APP_NAME)

    yield

    # ── Shutdown ──────────────────────────────────
    log.info("app_shutting_down")


# ── FastAPI App ───────────────────────────────────
app = FastAPI(
    title=settings.APP_NAME,
    description="Multi-channel AI classroom platform",
    version="1.0.0",
    lifespan=lifespan
)

# ── CORS ──────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Routes ────────────────────────────────────────

@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "app": settings.APP_NAME,
        "status": "running",
        "env": settings.APP_ENV
    }


@app.get("/health")
async def health():
    """
    Detailed health check.
    Checks all services.
    """
    db_ok = check_db_connection()
    redis_ok = check_redis_connection()

    status = "healthy" if db_ok and redis_ok else "degraded"

    return {
        "status": status,
        "database": "ok" if db_ok else "error",
        "redis": "ok" if redis_ok else "error",
    }


telegram_app = create_telegram_app()

@app.post("/webhook/telegram")
async def telegram_webhook(request: Request):
    """Receive webhook updates from Telegram."""
    
    # Verify secret token
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if secret != settings.TELEGRAM_WEBHOOK_SECRET:
        log.warning("invalid_telegram_webhook_secret",
                    received=secret,
                    expected=settings.TELEGRAM_WEBHOOK_SECRET)
        return JSONResponse(
            status_code=403,
            content={"error": "Invalid secret"}
        )

    body = await request.json()
    log.info("telegram_webhook_received", body=str(body)[:100])

    from telegram import Update
    if not telegram_app.running:
        await telegram_app.initialize()

    update = Update.de_json(body, telegram_app.bot)
    await telegram_app.process_update(update)

    return JSONResponse(content={"ok": True})




@app.get("/stream/{tenant_id}")
async def stream_events(tenant_id: str, request: Request):
    """
    SSE endpoint for live dashboard updates.
    Browser connects here to receive live events.

    When teacher creates assignment →
    this endpoint pushes event to all
    connected student browsers instantly.
    """
    from fastapi.responses import StreamingResponse
    from app.core.events import subscribe_to_tenant_events
    import json
    import asyncio

    async def event_generator():
        # Send initial connection confirmation
        yield f"data: {json.dumps({'type': 'connected', 'tenant_id': tenant_id})}\n\n"

        # Keep connection alive with heartbeat
        # In production this would subscribe to Redis
        count = 0
        while True:
            if await request.is_disconnected():
                break
            # Heartbeat every 30 seconds
            yield f"data: {json.dumps({'type': 'heartbeat', 'count': count})}\n\n"
            count += 1
            await asyncio.sleep(30)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"
        }
    )