# app/core/logger.py
# ════════════════════════════════════════════════
# Structured Logging Setup
# 
# WHY STRUCTURED LOGGING?
# Regular print() or basic logging gives you:
#   "Error occurred at 14:23:01"
# 
# Structured logging gives you:
#   {
#     "timestamp": "2026-05-18T14:23:01Z",
#     "level": "error",
#     "event": "agent_failed",
#     "agent": "teacher_agent",
#     "user_id": "usr_123",
#     "channel": "telegram",
#     "correlation_id": "req_abc123",
#     "error": "LLM timeout after 30s"
#   }
# 
# With structured logs you can:
# - Search: "show me all errors for user_id=usr_123"
# - Trace: follow a request across agent → tool → DB
# - Debug: see exactly what state the app was in when it failed
# - Monitor: set alerts when error rate spikes
#
# CORRELATION ID:
# Every request gets a unique ID (e.g. req_abc123).
# This ID is attached to EVERY log line for that request.
# So you can trace: 
#   channel received message [req_abc123]
#   → safety agent filtered [req_abc123]  
#   → router classified [req_abc123]
#   → teacher agent created assignment [req_abc123]
#   → saved to DB [req_abc123]
# Even if 1000 requests happen simultaneously,
# you can filter by correlation_id and see just yours.
#
# PII REDACTION:
# We never log raw message content by default.
# A student's submission text should never appear in logs.
# The redact() function masks sensitive content.
# ════════════════════════════════════════════════

import logging
import sys
import uuid
from contextvars import ContextVar
from typing import Any
import structlog

# ── Context Variable ──────────────────────────────
# This stores the correlation_id for the current request
# ContextVar is thread-safe and async-safe
# Each request gets its own isolated value
correlation_id_var: ContextVar[str] = ContextVar(
    "correlation_id",
    default="no-correlation-id"
)

# ── PII Redaction ─────────────────────────────────
# Fields that should NEVER appear in logs
SENSITIVE_FIELDS = {
    "password",
    "token",
    "secret",
    "auth_token",
    "magic_link",
    "jwt",
    "private_key",
    "message_body",    # raw student/teacher message content
    "submission_text", # student submission content
    "voice_transcript" # voice note transcriptions
}

def redact_sensitive(
    logger: Any,
    method: str,
    event_dict: dict
) -> dict:
    """
    Structlog processor that redacts sensitive fields.
    
    Runs on every log call automatically.
    If a log contains a sensitive field, its value
    is replaced with [REDACTED].
    
    Example:
        log.info("user_login", token="abc123")
        → {"event": "user_login", "token": "[REDACTED]"}
    """
    for field in SENSITIVE_FIELDS:
        if field in event_dict:
            event_dict[field] = "[REDACTED]"
    return event_dict


def add_correlation_id(
    logger: Any,
    method: str,
    event_dict: dict
) -> dict:
    """
    Structlog processor that adds correlation_id to every log.
    
    Reads from the ContextVar set at the start of each request.
    This means every log line for a request automatically
    includes the same correlation_id — no manual passing needed.
    """
    event_dict["correlation_id"] = correlation_id_var.get()
    return event_dict


def add_app_info(
    logger: Any,
    method: str,
    event_dict: dict
) -> dict:
    """
    Adds app-level context to every log line.
    Useful when running multiple services.
    """
    event_dict["app"] = "classroom-companion"
    return event_dict


# ── Configure Structlog ───────────────────────────
def setup_logging(log_level: str = "INFO", json_logs: bool = False):
    """
    Call this ONCE at app startup (in main.py).
    
    Args:
        log_level: "DEBUG", "INFO", "WARNING", "ERROR"
        json_logs: True in production (machine readable)
                   False in development (human readable)
    
    Why two formats?
    - Development: coloured, readable console output
    - Production: JSON so log aggregators (Grafana, Datadog)
                  can parse and index each field separately
    """

    # Shared processors — run on every log line
    shared_processors = [
        # Add timestamp
        structlog.processors.TimeStamper(fmt="iso"),
        # Add log level
        structlog.stdlib.add_log_level,
        # Add correlation ID
        add_correlation_id,
        # Add app info
        add_app_info,
        # Redact sensitive fields
        redact_sensitive,
        # Format exceptions properly
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if json_logs:
        # Production: JSON format
        # Each log line is a valid JSON object
        # Easy for log aggregators to parse
        renderer = structlog.processors.JSONRenderer()
    else:
        # Development: coloured console output
        # Much easier to read during development
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=shared_processors + [renderer],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Also configure standard Python logging
    # So third-party libraries (FastAPI, SQLAlchemy)
    # go through the same pipeline
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level.upper()),
    )

    # Quieten noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)


# ── Logger Factory ────────────────────────────────
def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """
    Get a logger for a specific module.
    
    Usage:
        from app.core.logger import get_logger
        log = get_logger(__name__)
        
        log.info("assignment_created",
                 assignment_id="asgn_123",
                 teacher_id="usr_456",
                 student_count=8)
        
        log.error("llm_failed",
                  agent="teacher_agent",
                  model="llama-3.3-70b-versatile",
                  error=str(e))
    
    The name parameter (usually __name__) tells you
    which file the log came from.
    """
    return structlog.get_logger(name)


# ── Correlation ID Helpers ────────────────────────
def generate_correlation_id() -> str:
    """
    Generate a new unique correlation ID.
    Format: req_<8 random chars>
    Example: req_a3f9bc12
    
    Short enough to read, unique enough to not collide.
    """
    return f"req_{uuid.uuid4().hex[:8]}"


def set_correlation_id(correlation_id: str = None) -> str:
    """
    Set correlation ID for the current request context.
    
    Call this at the START of every request handler.
    All subsequent log calls in this request will
    automatically include this ID.
    
    Args:
        correlation_id: Use existing ID (e.g. from 
                       X-Correlation-ID header) or
                       generate a new one if None.
    Returns:
        The correlation_id that was set.
    """
    cid = correlation_id or generate_correlation_id()
    correlation_id_var.set(cid)
    return cid


def get_correlation_id() -> str:
    """Get the current request's correlation ID."""
    return correlation_id_var.get()


# ── Convenience Loggers ───────────────────────────
# Pre-built loggers for each major component
# Import these directly instead of calling get_logger()

agent_log    = get_logger("agents")
channel_log  = get_logger("channels")
auth_log     = get_logger("auth")
db_log       = get_logger("database")
api_log      = get_logger("api")
event_log    = get_logger("events")