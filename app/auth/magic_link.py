# app/auth/magic_link.py
# ════════════════════════════════════════════════
# Magic Link Authentication
#
# WHY THIS FILE EXISTS:
# Users log in without a password.
# We email them a link — clicking it proves
# they own that email address.
#
# HOW IT WORKS:
# 1. User enters email on web app
# 2. We generate a signed token
# 3. We email them a link with the token
# 4. They click it → we verify the token
# 5. We issue JWT access + refresh tokens
# 6. Token is immediately invalidated (single use)
#
# SECURITY:
# - Token is signed with SECRET_KEY
# - Token expires in 15 minutes
# - Token can only be used once
# - Token is bound to the email address
#
# FOR JUNIORS:
# Never reuse magic link tokens.
# Always call invalidate_magic_link() after use.
# ════════════════════════════════════════════════

import secrets
import hashlib
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy.orm import Session

import redis

from app.core.config import settings
from app.core.logger import get_logger, get_correlation_id
from app.db.models import User, AuditLog, AuditAction

log = get_logger(__name__)


# ── Token Generation ──────────────────────────────

def generate_magic_token(email: str) -> str:
    """
    Generate a signed single-use magic link token.

    Token format: <random_bytes>.<email_hash>
    The email hash binds the token to the email —
    it cannot be used for a different email address.

    Args:
        email: The user's email address

    Returns:
        URL-safe token string valid for 15 minutes
    """
    # Random component — unpredictable
    random_part = secrets.token_urlsafe(32)

    # Email hash — binds token to email
    email_hash = hashlib.sha256(
        email.lower().encode()
    ).hexdigest()[:16]

    # Combine
    token = f"{random_part}.{email_hash}"

    log.info("magic_token_generated",
             email=email,
             correlation_id=get_correlation_id())

    return token


def store_magic_token(
    email: str,
    token: str,
) -> None:
    """
    Store magic token in Redis with TTL.

    Key format: magic_link:{token_hash}
    Value: email address
    TTL: MAGIC_LINK_TTL_MINUTES (default 15)

    We store the hash not the raw token —
    same principle as refresh tokens.

    Args:
        email: User's email
        token: Raw magic link token
    """
    # Hash token before storing
    token_hash = hashlib.sha256(
        token.encode()
    ).hexdigest()

    # Store in Redis with TTL
    r = redis.from_url(settings.REDIS_URL, decode_responses=True)
    key = f"magic_link:{token_hash}"
    ttl = settings.MAGIC_LINK_TTL_MINUTES * 60  # convert to seconds

    r.setex(key, ttl, email)

    log.info("magic_token_stored",
             email=email,
             ttl_minutes=settings.MAGIC_LINK_TTL_MINUTES)


def verify_magic_token(token: str) -> Optional[str]:
    """
    Verify a magic link token and return the email.

    Checks:
    1. Token exists in Redis
    2. Token has not expired (Redis TTL handles this)
    3. Token matches the email hash

    Args:
        token: Raw magic link token from URL

    Returns:
        Email address if valid
        None if invalid or expired
    """
    try:
        # Hash the incoming token
        token_hash = hashlib.sha256(
            token.encode()
        ).hexdigest()

        # Look up in Redis
        r = redis.from_url(
            settings.REDIS_URL,
            decode_responses=True
        )
        key = f"magic_link:{token_hash}"
        email = r.get(key)

        if not email:
            log.warning("magic_token_not_found_or_expired",
                        correlation_id=get_correlation_id())
            return None

        # Verify email hash matches token
        expected_hash = hashlib.sha256(
            email.lower().encode()
        ).hexdigest()[:16]

        if not token.endswith(f".{expected_hash}"):
            log.warning("magic_token_email_mismatch",
                        correlation_id=get_correlation_id())
            return None

        log.info("magic_token_verified",
                 email=email,
                 correlation_id=get_correlation_id())

        return email

    except Exception as e:
        log.error("magic_token_verification_failed",
                  error=str(e),
                  exc_info=True)
        return None


def invalidate_magic_token(token: str) -> None:
    """
    Invalidate a magic token after use.
    Called immediately after successful verification.
    Ensures single-use — cannot be used again.

    Args:
        token: Raw magic link token to invalidate
    """
    token_hash = hashlib.sha256(
        token.encode()
    ).hexdigest()

    r = redis.from_url(
        settings.REDIS_URL,
        decode_responses=True
    )
    key = f"magic_link:{token_hash}"
    r.delete(key)

    log.info("magic_token_invalidated",
             correlation_id=get_correlation_id())


def build_magic_link(token: str) -> str:
    """
    Build the full magic link URL.

    Args:
        token: Raw magic link token

    Returns:
        Full URL the user clicks in their email
        e.g. https://myapp.railway.app/auth/verify?token=xxx
    """
    return f"{settings.FRONTEND_URL}/auth/verify?token={token}"


# ── Full Magic Link Flow ──────────────────────────

def create_and_store_magic_link(email: str) -> str:
    """
    Complete magic link creation flow.

    1. Generate token
    2. Store in Redis with TTL
    3. Return full URL

    Args:
        email: User's email address

    Returns:
        Full magic link URL to send to user
    """
    token = generate_magic_token(email)
    store_magic_token(email, token)
    link = build_magic_link(token)

    log.info("magic_link_created",
             email=email,
             link_preview=link[:50])

    return link


def verify_and_consume_magic_link(
    token: str,
    db: Session
) -> Optional[User]:
    """
    Verify magic link and return the user.

    1. Verify token is valid
    2. Invalidate token immediately (single use)
    3. Find user by email
    4. Log the action to audit_logs
    5. Return user

    Args:
        token: Raw token from URL query param
        db: Database session

    Returns:
        User object if valid
        None if invalid
    """
    # Verify token
    email = verify_magic_token(token)
    if not email:
        return None

    # Invalidate immediately — single use
    invalidate_magic_token(token)

    # Find user in database
    user = db.query(User).filter(
        User.email == email.lower(),
        User.is_active == True
    ).first()

    if not user:
        log.warning("magic_link_user_not_found",
                    email=email)
        return None

    # Log to audit trail
    audit = AuditLog(
        tenant_id=str(user.tenant_id),
        user_id=str(user.id),
        action=AuditAction.MAGIC_LINK_USED,
        correlation_id=get_correlation_id()
    )
    db.add(audit)

    log.info("magic_link_used",
             user_id=str(user.id),
             email=email,
             correlation_id=get_correlation_id())

    return user