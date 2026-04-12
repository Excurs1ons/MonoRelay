"""JWT token utilities for authentication."""
from __future__ import annotations

import logging
import secrets
import time
from datetime import datetime, timedelta
from typing import Optional

from jose import JWTError, jwt

logger = logging.getLogger("monorelay.auth")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 1 day
REFRESH_TOKEN_EXPIRE_DAYS = 7  # 7 days

_jwt_secret: Optional[str] = None


def get_jwt_secret(config_secret: str = "") -> str:
    global _jwt_secret
    if _jwt_secret is None:
        if config_secret:
            _jwt_secret = config_secret
        else:
            secret_path = "./data/jwt_secret.txt"
            try:
                with open(secret_path, "r") as f:
                    _jwt_secret = f.read().strip()
            except FileNotFoundError:
                _jwt_secret = secrets.token_urlsafe(32)
                try:
                    import os
                    os.makedirs("./data", exist_ok=True)
                    with open(secret_path, "w") as f:
                        f.write(_jwt_secret)
                    logger.info("Generated new JWT secret")
                except Exception:
                    pass
    return _jwt_secret


def create_access_token(user_id: int, expires_delta: Optional[timedelta] = None, config_secret: str = "") -> str:
    """Create JWT access token for user."""
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode = {
        "sub": str(user_id),
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "access"
    }
    secret = get_jwt_secret(config_secret)
    encoded_jwt = jwt.encode(to_encode, secret, algorithm=ALGORITHM)
    return encoded_jwt


def create_refresh_token(user_id: int, config_secret: str = "") -> str:
    """Create JWT refresh token for user."""
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode = {
        "sub": str(user_id),
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "refresh"
    }
    secret = get_jwt_secret(config_secret)
    encoded_jwt = jwt.encode(to_encode, secret, algorithm=ALGORITHM)
    return encoded_jwt


def verify_token(token: str, token_type: str = "access", config_secret: str = "") -> Optional[int]:
    """Verify JWT token and return user_id if valid."""
    try:
        secret = get_jwt_secret(config_secret)
        payload = jwt.decode(token, secret, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        token_type_claim: str = payload.get("type", "access")
        
        if user_id is None:
            return None
        
        if token_type_claim != token_type:
            return None
        
        return int(user_id)
    except JWTError:
        return None


def refresh_access_token(refresh_token: str, config_secret: str = "") -> Optional[str]:
    """Create new access token from refresh token."""
    user_id = verify_token(refresh_token, token_type="refresh", config_secret=config_secret)
    if user_id is None:
        return None
    return create_access_token(user_id, config_secret=config_secret)
