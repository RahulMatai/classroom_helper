# app/core/events.py
# ════════════════════════════════════════════════
# Redis Event Bus — Pub/Sub
#
# WHY THIS FILE EXISTS:
# When a teacher creates an assignment, every
# connected student's dashboard must show a
# live popup within 1 second — without refresh.
#
# HOW IT WORKS:
# 1. Teacher creates assignment
# 2. We publish event to Redis channel
# 3. Redis broadcasts to all subscribers
# 4. SSE connections receive it instantly
# 5. Browser shows popup

#
# -----IMPORTANT-------------
# publish() → send an event
# subscribe() → listen for events
# Never use this for permanent storage —
# use the database for that.
# ════════════════════════════════════════════════

import json
import redis
from typing import Dict, Any, Generator

from app.core.config import settings
from app.core.logger import get_logger

log = get_logger(__name__)

# ── Event Types ───────────────────────────────────
# These are the events that flow through the bus.
# Keep this list updated as you add new events.

class EventType:
    """
    All possible event types in the system.
    Used as channel names in Redis pub/sub.

    Naming convention: entity.action
    Examples:
        assignment.created  → teacher made assignment
        submission.received → student submitted work
        feedback.sent       → teacher sent feedback
        reminder.sent       → bot sent a nudge
    """
    ASSIGNMENT_CREATED  = "assignment.created"
    ASSIGNMENT_UPDATED  = "assignment.updated"
    SUBMISSION_RECEIVED = "submission.received"
    FEEDBACK_SENT       = "feedback.sent"
    REMINDER_SENT       = "reminder.sent"
    DIGEST_SENT         = "digest.sent"
    ESCALATION_SENT     = "escalation.sent"
    USER_JOINED         = "user.joined"


# ── Redis Client ──────────────────────────────────
# Two separate clients — one for publishing,
# one for subscribing.
# Why two? A client in subscribe mode can ONLY
# subscribe — it cannot publish or do anything else.

def get_redis_client() -> redis.Redis:
    """
    Returns a Redis client for publishing events.
    Used by agents to fire events.
    """
    return redis.from_url(
        settings.REDIS_URL,
        decode_responses=True
    )

def get_redis_pubsub():
    """
    Returns a Redis pubsub object for subscribing.
    Used by SSE endpoint to listen for events.
    """
    client = redis.from_url(
        settings.REDIS_URL,
        decode_responses=True
    )
    return client.pubsub()


# ── Publisher ─────────────────────────────────────
def publish_event(
    event_type: str,
    tenant_id: str,
    data: Dict[str, Any],
    correlation_id: str = None
) -> None:
    """
    Publish an event to Redis pub/sub bus.

    Called by agents after important operations.
    All connected SSE clients will receive it.

    Args:
        event_type: From EventType class
            e.g. EventType.ASSIGNMENT_CREATED
        tenant_id: Which school this event is for
            Only that school's users will see it
        data: Event payload — what happened
            e.g. {"assignment_id": "...", "title": "..."}
        correlation_id: Request trace ID

    Example:
        publish_event(
            event_type=EventType.ASSIGNMENT_CREATED,
            tenant_id=teacher.tenant_id,
            data={
                "assignment_id": assignment.id,
                "title": assignment.title,
                "teacher_name": teacher.full_name,
            }
        )
    """
    try:
        # Build event envelope
        event = {
            "type": event_type,
            "tenant_id": tenant_id,
            "data": data,
            "correlation_id": correlation_id or "system",
        }

        # Channel name includes tenant_id so events
        # only go to the right school's subscribers
        channel = f"tenant:{tenant_id}:{event_type}"

        # Publish to Redis
        client = get_redis_client()
        client.publish(channel, json.dumps(event))

        log.info("event_published",
                 event_type=event_type,
                 tenant_id=tenant_id,
                 channel=channel,
                 correlation_id=correlation_id)

    except Exception as e:
        log.error("event_publish_failed",
                  event_type=event_type,
                  tenant_id=tenant_id,
                  error=str(e),
                  exc_info=True)
        # Don't raise — event bus failure should
        # never crash the main operation
        # Log it and move on


# ── Subscriber ────────────────────────────────────
def subscribe_to_tenant_events(
    tenant_id: str,
    event_types: list = None
) -> Generator:
    """
    Subscribe to all events for a tenant.
    Used by SSE endpoint to stream events
    to connected browser clients.

    Args:
        tenant_id: Which school to subscribe to
        event_types: Specific events to listen for
            None = listen to all events

    Yields:
        Event dictionaries as they arrive

    Usage in SSE endpoint:
        for event in subscribe_to_tenant_events(tid):
            yield f"data: {json.dumps(event)}\n\n"
    """
    pubsub = get_redis_pubsub()

    # Build list of channels to subscribe to
    if event_types:
        channels = [
            f"tenant:{tenant_id}:{et}"
            for et in event_types
        ]
    else:
        # Subscribe to all events for this tenant
        channels = [f"tenant:{tenant_id}:*"]
        pubsub.psubscribe(*channels)
        log.info("subscribed_to_tenant_events",
                 tenant_id=tenant_id,
                 pattern=channels)

        # Yield events as they arrive
        for message in pubsub.listen():
            if message["type"] == "pmessage":
                try:
                    event = json.loads(message["data"])
                    yield event
                except json.JSONDecodeError:
                    continue
            return

    pubsub.subscribe(*channels)
    log.info("subscribed_to_tenant_events",
             tenant_id=tenant_id,
             channels=channels)

    for message in pubsub.listen():
        if message["type"] == "message":
            try:
                event = json.loads(message["data"])
                yield event
            except json.JSONDecodeError:
                continue


# ── Health Check ──────────────────────────────────
def check_redis_connection() -> bool:
    """
    Tests if Redis is reachable.
    Called at startup to fail fast if Redis is down.
    """
    try:
        client = get_redis_client()
        client.ping()
        log.info("redis_connection_ok")
        return True
    except Exception as e:
        log.error("redis_connection_failed",
                  error=str(e),
                  exc_info=True)
        return False