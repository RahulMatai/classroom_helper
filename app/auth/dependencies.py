# app/auth/dependencies.py
# ════════════════════════════════════════════════
# FastAPI Auth Dependencies
#
# WHY THIS FILE EXISTS:
# FastAPI dependencies run before route handlers.
# These functions extract and verify the JWT token
# from every request automatically.
#
# HOW IT WORKS:
# 1. Request comes in with Authorization header
# 2. get_current_user() extracts and verifies JWT
# 3. If valid → route handler runs with user object
# 4. If invalid → 401 Unauthorized returned
#
# ---------IMPORTANT -----------
# Add Depends(get_current_user) to any route
# that needs authentication.
# Add Depends(require_teacher) for teacher-only routes.

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.auth.jwt import verify_access_token
from app.core.logger import get_logger, set_correlation_id
from app.core.policy import is_teacher, is_admin, is_student
from app.db.models import User, UserRole
from app.db.session import get_db

log = get_logger(__name__)

security = HTTPBearer()
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """
    extract and verify token from request
    
    """
    correlation_id = set_correlation_id ()
    token= credentials.credentials
    claims = verify_access_token(token)
    if not claims:
        log.warning("invalid_token",
                    correlation_id=correlation_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )

    # Get user from database
    user = db.query(User).filter(
        User.id == claims["sub"],
        User.is_active == True
    ).first()
    if not user:
        log.warning("user_not_found",
                    user_id=claims["sub"],
                    correlation_id=correlation_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )
    # Verify tenant matches token
    if str(user.tenant_id) != claims["tenant_id"]:
        log.warning("tenant_mismatch",
                    user_id=str(user.id),
                    correlation_id=correlation_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token tenant mismatch"
        )
        log.info("user_authenticated",
             user_id=str(user.id),
             role=str(user.role),
             correlation_id=correlation_id)

    return user

async def require_teacher(
    user: User = Depends(get_current_user)
) -> User:
    """
    Required the current user to be a teacher
    
    """
    if not is_teacher(user):
        log.warning("unauthorized_teacher_access",
                    user_id=str(user.id),
                    role=str(user.role))
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Teacher access required"
        )
    return user
async def require_admin(
    user: User = Depends(get_current_user)
) -> User:
    """Require admin role."""
    if not is_admin(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return user

async def require_student(
    user: User = Depends(get_current_user)
) -> User:
    """Require student role."""
    if not is_student(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Student access required"
        )
    return user

async def get_optional_user(
    credentials: HTTPAuthorizationCredentials = Depends(
        HTTPBearer(auto_error=False)
    ),
    db: Session = Depends(get_db)
) -> User:
    """
    Get current user if authenticated, None if not.
    """
    if not credentials:
        return None
    try:
        return await get_current_user(credentials, db)
    except HTTPException:
        return None