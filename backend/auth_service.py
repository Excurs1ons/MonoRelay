"""Authentication service with registration and login."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Optional

from fastapi import HTTPException, status

from .auth_models import Token, User, UserCreate, UserLogin, UserManager
from .auth_utils import create_access_token, create_refresh_token, verify_token

logger = logging.getLogger("monorelay.auth")


class AuthService:
    """Service layer for authentication operations."""
    
    def __init__(self, user_manager: Optional[UserManager] = None, jwt_secret: str = ""):
        self.user_manager = user_manager or UserManager()
        self.jwt_secret = jwt_secret
    
    async def init(self):
        """Initialize the auth service."""
        await self.user_manager.init()
    
    async def close(self):
        """Close the auth service."""
        await self.user_manager.close()
    
    async def register(self, user_data: UserCreate, is_first_user: bool = False) -> Token:
        """Register a new user and return tokens."""
        try:
            is_admin = is_first_user
            is_super_admin = is_first_user
            user = await self.user_manager.create_user(user_data, is_admin=is_admin, is_super_admin=is_super_admin)

            access_token = create_access_token(user.id, config_secret=self.jwt_secret)
            refresh_token = create_refresh_token(user.id, config_secret=self.jwt_secret)

            logger.info(f"User registered: {user.username} (admin={is_admin}, super_admin={is_super_admin})")
            
            return Token(
                access_token=access_token,
                token_type="bearer",
                expires_in=60 * 60 * 24,  # 24 hours
                refresh_token=refresh_token,
                user={
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "is_admin": user.is_admin,
                    "is_super_admin": user.is_super_admin,
                }
            )
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e)
            )
    
    async def login(self, login_data: UserLogin) -> Token:
        """Authenticate user and return tokens."""
        user = await self.user_manager.authenticate_user(
            login_data.username,
            login_data.password
        )
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
            )
        
        access_token = create_access_token(user.id, config_secret=self.jwt_secret)
        refresh_token = create_refresh_token(user.id, config_secret=self.jwt_secret)
        
        logger.info(f"User logged in: {user.username}")
        
        return Token(
            access_token=access_token,
            token_type="bearer",
            expires_in=60 * 60 * 24,  # 24 hours
            refresh_token=refresh_token,
            user={
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "is_admin": user.is_admin,
                "is_super_admin": user.is_super_admin,
            }
        )
    
    async def get_current_user(self, token: str) -> Optional[User]:
        """Get current user from token."""
        user_id = verify_token(token, config_secret=self.jwt_secret)
        if user_id is None:
            return None
        return await self.user_manager.get_user_by_id(user_id)
    
    async def refresh_token(self, refresh_token: str) -> Optional[Token]:
        """Refresh access token using refresh token."""
        from .auth_utils import refresh_access_token, verify_token
        
        user_id = verify_token(refresh_token, token_type="refresh", config_secret=self.jwt_secret)
        if user_id is None:
            return None
        
        user = await self.user_manager.get_user_by_id(user_id)
        if not user or not user.is_active:
            return None
        
        access_token = create_access_token(user.id, config_secret=self.jwt_secret)
        new_refresh_token = create_refresh_token(user.id, config_secret=self.jwt_secret)
        
        return Token(
            access_token=access_token,
            token_type="bearer",
            expires_in=60 * 60 * 24,
            refresh_token=new_refresh_token,
            user={
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "is_admin": user.is_admin,
                "is_super_admin": user.is_super_admin,
            }
        )
    
    async def has_users(self) -> bool:
        """Check if any users exist."""
        return await self.user_manager.has_users()
