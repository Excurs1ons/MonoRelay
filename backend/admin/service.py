"""Business logic layer for admin operations."""
from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Optional

from ..auth_models import User, UserManager, RedemptionCode
from ..auth_service import AuthService

logger = logging.getLogger("monorelay.admin")


class AdminService:
    """Service layer for admin operations."""

    def __init__(self, user_manager: UserManager, auth_service: AuthService):
        self.user_manager = user_manager
        self.auth_service = auth_service

    async def list_users(self, limit: int = 100, offset: int = 0) -> list[User]:
        """List all users with pagination."""
        return await self.user_manager.list_users(limit=limit, offset=offset)

    async def update_balance(self, user_id: int, adjustment: float) -> bool:
        """Update user balance."""
        return await self.user_manager.update_balance(user_id, adjustment)

    async def delete_user(self, user_id: int) -> bool:
        """Delete a user."""
        if user_id == 0:
            return False
        return await self.user_manager.delete_user(user_id)

    async def list_redemption_codes(self, limit: int = 100) -> list[RedemptionCode]:
        """List all redemption codes."""
        return await self.user_manager.list_redemption_codes(limit=limit)

    async def generate_codes(self, amount: float, count: int = 1, prefix: str = "PRISMA-") -> list[str]:
        """Generate redemption codes."""
        return await self.user_manager.generate_codes(amount, count, prefix)

    async def redeem_code(self, user_id: int, code: str) -> Optional[float]:
        """Redeem a code for a user."""
        return await self.user_manager.redeem_code(user_id, code)

    async def update_user(self, user_id: int, **kwargs) -> Optional[User]:
        """Update user fields."""
        return await self.user_manager.update_user(user_id, **kwargs)

    async def clear_all_data(self) -> bool:
        """Clear all local data and reset system."""
        try:
            data_dir = Path("./data")
            config_file = Path("./config.yml")

            await self.user_manager.close()

            if data_dir.exists():
                shutil.rmtree(data_dir)
                data_dir.mkdir(exist_ok=True)
                logger.info("Data directory cleared")

            if config_file.exists():
                example = Path("./config.yml.example")
                if example.exists():
                    shutil.copy(example, config_file)
                else:
                    config_file.unlink()
                logger.info("Config file reset")

            return True
        except Exception as e:
            logger.error(f"Failed to clear data: {e}")
            return False
