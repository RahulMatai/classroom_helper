# app/auth/jwt.py
# ════════════════════════════════════════════════
# JWT Token Management
#
# WHY THIS FILE EXISTS:
# After a user logs in via magic link we issue
# a JWT token. Every subsequent request includes
# this token to prove who they are.
#
# WHY ASYMMETRIC KEYS (RS256)?
# Symmetric (HS256): one key signs AND verifies
#   → if key leaks, anyone can create fake tokens
# Asymmetric (RS256): private key signs, public verifies
#   → private key never leaves our server
#   → public key can be shared safely
# TOKEN TYPES:
# Access token  → short lived (60 mins)
#                 included in every request
# Refresh token → long lived (7 days)
#                 used only to get new access token

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from jose import jwt, JWTError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logger import get_logger
from app.db.models import RefreshToken, User

log = get_logger(__name__)

def create_access_token(user:User,additional_claims:Dict[str,Any]= None)->str:
    """
    create a short lived token for magic link
     
     Token contains:
        sub        → user ID
        tenant_id  → which school
        role       → teacher/student/parent/admin
        email      → user email
        exp        → expiry timestamp
        iat        → issued at timestamp
        jti        → unique token ID (for revocation)
        
    """
    now = datetime.utcnow()
    expire = now + timedelta(minutes=settings.JWT_ACCESS_TTL_MINUTES)
    
    claims = {
        # Standard JWT claims
        "sub":       str(user.id),
        "exp":       expire,
        "iat":       now,
        "jti":       secrets.token_hex(16),
        # Our custom claims
        "tenant_id": str(user.tenant_id),
        "role":      user.role.value,
        "email":     user.email,
        "type":      "access"
    }
    if additional_claims:
        claims.update(additional_claims)
    private_key = settings.JWT_PRIVATE_KEY.replace('\\n', '\n')
    token = jwt.encode(claims,private_key,algorithm= settings.JWT_ALGORITHM)
    log.info("access_token_created",
             user_id=str(user.id),
             tenant_id=str(user.tenant_id),
             role=user.role.value,
             expires_at=expire.isoformat())

    return token
    
def create_refresh_token(user:User,db:Session,device_info:str=None,parent_token_id:str=None):
    """
    create a long lived token
    it will be stored in databaseas a has (encrypted )never as rae token
    """
    raw_token =  secrets.token_urlsafe(64)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    expires_at =  datetime.utcnow()+ timedelta(day = settings.JWT_REFRESH_TTL_DAYS)
    refresh_token = RefreshToken(
       user_id = str(user.id),
        token_hash = token_hash,
        parent_token_id = parent_token_id,
        device_info = device_info,
        expires_at = expires_at,
        is_revoked = False
    )
    db.add(refresh_token)
    db. flush()
    log.info("refresh_token_created",
             user_id=str(user.id),
             token_id=str(refresh_token.id),
             expires_at=expires_at.isoformat())

    return raw_token

#--------token Verification----------------------
def verify_access_token(token:str):
    #verify and decode token
    try:
        public_key = settings.JWT_PUBLIC_KEY.replace('\\n', '\n')
        claims = jwt.decode(
            token,
            public_key,
            algorithms=[settings.JWT_ALGORITHM]
        )

        # Make sure it's an access token
        if claims.get("type") != "access":
            log.warning("wrong_token_type",
                        expected="access",
                        got=claims.get("type"))
            return None

        return claims
    except JWTError as e:
        log.warning("token Verification failed",error=str(e))
        return None
    
def revoke_token_chain(token: RefreshToken, db:Session):
    #revoke all tokens in chain this will be used when token seems stolen
        log.warning("revoking_token_chain",
                token_id=str(token.id),
                user_id=str(token.user_id))
        db.query(RefreshToken).filter(
        RefreshToken.user_id == token.user_id,
        RefreshToken.is_revoked == False
    ).update({"is_revoked": True})
        db.flush()
    
def verify_refresh_token(raw_token:str, db:Session):
    #verify the refresh token against the databse
    token_hash = hashlib.sha3_256(raw_token.encode()).hexdigest()
    refresh_token = db.query(RefreshToken).filter(
        RefreshToken.token_hash == token_hash
    ).first()
    if not refresh_token:
        log.warning("refresh_token_not_found")
        return None

    if refresh_token.is_revoked:
        log.warning("revoked_token_used",
                    token_id=str(refresh_token.id),
                    user_id=str(refresh_token.user_id))
        # Revoke entire chain — possible token theft
        revoke_token_chain(refresh_token, db)
        return None
    if refresh_token.expires_at < datetime.utcnow():
        log.warning("expired_refresh_token",
                    token_id=str(refresh_token.id))
        return None

    return refresh_token
def rotate_refresh_token(old_token: RefreshToken, user: User, db: Session , device_info: str = None):
    # refresh the old token we have and recieve the new token 
    old_token.is_revoked = True
    db.flush()
    log.info("refresh_token_rotated",
             old_token_id=str(old_token.id),
             user_id=str(user.id))
    return create_refresh_token(
        user=user,
        db=db,
        device_info=device_info,
        parent_token_id=str(old_token.id)
    )

def revoke_token(token_id: str, db:Session)-> None:
    """
    Revoke a specific refresh token
    
    """
    token = db.query ( RefreshToken).filter(RefreshToken.id == token_id).first()
    if token:
        token.is_revoked= True
        db. flush()
        log.info("token_revoked",
                 token_id=token_id,
                 user_id=str(token.user_id))
    
    
    
    
    

    