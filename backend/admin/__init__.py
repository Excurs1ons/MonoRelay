"""Admin module for MonoRelay - user management and system administration."""
from __future__ import annotations

from .routes import router as admin_router
from .routes import user_router

__all__ = ["admin_router", "user_router"]
