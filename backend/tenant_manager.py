"""Tenant manager for multi-tenant configuration and provider management."""
from __future__ import annotations

import json
import logging
import time
from typing import Optional, List, Dict, Any

from .auth_models import UserManager
from .models import TenantConfig, TenantProvider, TenantAPIKey

logger = logging.getLogger("monorelay.tenant")


class TenantManager:
    """Manager for tenant-specific configuration and providers."""

    def __init__(self, user_manager: UserManager):
        self.user_manager = user_manager

    async def get_tenant_config(self, user_id: int) -> Optional[TenantConfig]:
        """Get tenant configuration for a user."""
        if not self.user_manager._db:
            await self.user_manager.init()
        cursor = await self.user_manager._db.execute(
            "SELECT * FROM tenant_configs WHERE user_id = ?",
            (user_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return TenantConfig(
            user_id=row["user_id"],
            config_json=row["config_json"],
            created_at=row["created_at"],
            updated_at=row["updated_at"]
        )

    async def create_tenant_config(self, user_id: int, config: Dict[str, Any]) -> TenantConfig:
        """Create tenant configuration for a user."""
        if not self.user_manager._db:
            await self.user_manager.init()
        now = time.time()
        config_json = json.dumps(config)
        cursor = await self.user_manager._db.execute(
            "INSERT INTO tenant_configs (user_id, config_json, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (user_id, config_json, now, now)
        )
        await self.user_manager._db.commit()
        return await self.get_tenant_config(user_id)

    async def update_tenant_config(self, user_id: int, config: Dict[str, Any]) -> Optional[TenantConfig]:
        """Update tenant configuration for a user."""
        if not self.user_manager._db:
            await self.user_manager.init()
        now = time.time()
        config_json = json.dumps(config)
        await self.user_manager._db.execute(
            "UPDATE tenant_configs SET config_json = ?, updated_at = ? WHERE user_id = ?",
            (config_json, now, user_id)
        )
        await self.user_manager._db.commit()
        return await self.get_tenant_config(user_id)

    async def delete_tenant_config(self, user_id: int) -> bool:
        """Delete tenant configuration for a user."""
        if not self.user_manager._db:
            await self.user_manager.init()
        cursor = await self.user_manager._db.execute(
            "DELETE FROM tenant_configs WHERE user_id = ?",
            (user_id,)
        )
        await self.user_manager._db.commit()
        return cursor.rowcount > 0

    async def get_tenant_providers(self, user_id: int) -> List[TenantProvider]:
        """Get all providers for a tenant."""
        if not self.user_manager._db:
            await self.user_manager.init()
        cursor = await self.user_manager._db.execute(
            "SELECT * FROM tenant_providers WHERE user_id = ? ORDER BY priority DESC",
            (user_id,)
        )
        rows = await cursor.fetchall()
        return [
            TenantProvider(
                id=row["id"],
                user_id=row["user_id"],
                provider_name=row["provider_name"],
                enabled=bool(row["enabled"]),
                base_url=row["base_url"] or "",
                headers_json=row["headers_json"] or "",
                models_json=row["models_json"] or "",
                priority=row["priority"],
                created_at=row["created_at"],
                updated_at=row["updated_at"]
            )
            for row in rows
        ]

    async def create_tenant_provider(
        self,
        user_id: int,
        provider_name: str,
        enabled: bool = True,
        base_url: str = "",
        headers: Dict[str, str] = None,
        models: Dict[str, List[str]] = None,
        priority: int = 100
    ) -> Optional[TenantProvider]:
        """Create a tenant provider."""
        if not self.user_manager._db:
            await self.user_manager.init()
        now = time.time()
        headers_json = json.dumps(headers or {})
        models_json = json.dumps(models or {})
        try:
            cursor = await self.user_manager._db.execute(
                """INSERT INTO tenant_providers 
                   (user_id, provider_name, enabled, base_url, headers_json, models_json, priority, created_at, updated_at) 
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (user_id, provider_name, 1 if enabled else 0, base_url, headers_json, models_json, priority, now, now)
            )
            await self.user_manager._db.commit()
            return await self.get_tenant_provider(cursor.lastrowid)
        except Exception as e:
            logger.error(f"Failed to create tenant provider: {e}")
            return None

    async def get_tenant_provider(self, provider_id: int) -> Optional[TenantProvider]:
        """Get a specific tenant provider."""
        if not self.user_manager._db:
            await self.user_manager.init()
        cursor = await self.user_manager._db.execute(
            "SELECT * FROM tenant_providers WHERE id = ?",
            (provider_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return TenantProvider(
            id=row["id"],
            user_id=row["user_id"],
            provider_name=row["provider_name"],
            enabled=bool(row["enabled"]),
            base_url=row["base_url"] or "",
            headers_json=row["headers_json"] or "",
            models_json=row["models_json"] or "",
            priority=row["priority"],
            created_at=row["created_at"],
            updated_at=row["updated_at"]
        )

    async def update_tenant_provider(
        self,
        provider_id: int,
        enabled: bool = None,
        base_url: str = None,
        headers: Dict[str, str] = None,
        models: Dict[str, List[str]] = None,
        priority: int = None
    ) -> Optional[TenantProvider]:
        """Update a tenant provider."""
        if not self.user_manager._db:
            await self.user_manager.init()
        now = time.time()
        updates = []
        values = []
        
        if enabled is not None:
            updates.append("enabled = ?")
            values.append(1 if enabled else 0)
        if base_url is not None:
            updates.append("base_url = ?")
            values.append(base_url)
        if headers is not None:
            updates.append("headers_json = ?")
            values.append(json.dumps(headers))
        if models is not None:
            updates.append("models_json = ?")
            values.append(json.dumps(models))
        if priority is not None:
            updates.append("priority = ?")
            values.append(priority)
        
        if not updates:
            return await self.get_tenant_provider(provider_id)
        
        updates.append("updated_at = ?")
        values.append(now)
        values.append(provider_id)
        
        await self.user_manager._db.execute(
            f"UPDATE tenant_providers SET {', '.join(updates)} WHERE id = ?",
            values
        )
        await self.user_manager._db.commit()
        return await self.get_tenant_provider(provider_id)

    async def delete_tenant_provider(self, provider_id: int) -> bool:
        """Delete a tenant provider."""
        if not self.user_manager._db:
            await self.user_manager.init()
        cursor = await self.user_manager._db.execute(
            "DELETE FROM tenant_providers WHERE id = ?",
            (provider_id,)
        )
        await self.user_manager._db.commit()
        return cursor.rowcount > 0

    async def get_tenant_api_keys(self, user_id: int) -> List[TenantAPIKey]:
        """Get all API keys for a tenant."""
        if not self.user_manager._db:
            await self.user_manager.init()
        cursor = await self.user_manager._db.execute(
            "SELECT * FROM tenant_api_keys WHERE user_id = ?",
            (user_id,)
        )
        rows = await cursor.fetchall()
        return [
            TenantAPIKey(
                id=row["id"],
                user_id=row["user_id"],
                provider_name=row["provider_name"],
                key_value=row["key_value"],
                label=row["label"],
                enabled=bool(row["enabled"]),
                weight=row["weight"],
                rate_limit=row["rate_limit"],
                cooldown=row["cooldown"],
                created_at=row["created_at"],
                last_used_at=row["last_used_at"]
            )
            for row in rows
        ]

    async def create_tenant_api_key(
        self,
        user_id: int,
        provider_name: str,
        key_value: str,
        label: str = "default",
        enabled: bool = True,
        weight: int = 1,
        rate_limit: int = 0,
        cooldown: int = 0
    ) -> Optional[TenantAPIKey]:
        """Create a tenant API key."""
        if not self.user_manager._db:
            await self.user_manager.init()
        now = time.time()
        try:
            cursor = await self.user_manager._db.execute(
                """INSERT INTO tenant_api_keys 
                   (user_id, provider_name, key_value, label, enabled, weight, rate_limit, cooldown, created_at) 
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (user_id, provider_name, key_value, label, 1 if enabled else 0, weight, rate_limit, cooldown, now)
            )
            await self.user_manager._db.commit()
            return await self.get_tenant_api_key(cursor.lastrowid)
        except Exception as e:
            logger.error(f"Failed to create tenant API key: {e}")
            return None

    async def get_tenant_api_key(self, key_id: int) -> Optional[TenantAPIKey]:
        """Get a specific tenant API key."""
        if not self.user_manager._db:
            await self.user_manager.init()
        cursor = await self.user_manager._db.execute(
            "SELECT * FROM tenant_api_keys WHERE id = ?",
            (key_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return TenantAPIKey(
            id=row["id"],
            user_id=row["user_id"],
            provider_name=row["provider_name"],
            key_value=row["key_value"],
            label=row["label"],
            enabled=bool(row["enabled"]),
            weight=row["weight"],
            rate_limit=row["rate_limit"],
            cooldown=row["cooldown"],
            created_at=row["created_at"],
            last_used_at=row["last_used_at"]
        )

    async def update_tenant_api_key(
        self,
        key_id: int,
        enabled: bool = None,
        label: str = None,
        weight: int = None,
        rate_limit: int = None,
        cooldown: int = None
    ) -> Optional[TenantAPIKey]:
        """Update a tenant API key."""
        if not self.user_manager._db:
            await self.user_manager.init()
        updates = []
        values = []
        
        if enabled is not None:
            updates.append("enabled = ?")
            values.append(1 if enabled else 0)
        if label is not None:
            updates.append("label = ?")
            values.append(label)
        if weight is not None:
            updates.append("weight = ?")
            values.append(weight)
        if rate_limit is not None:
            updates.append("rate_limit = ?")
            values.append(rate_limit)
        if cooldown is not None:
            updates.append("cooldown = ?")
            values.append(cooldown)
        
        if not updates:
            return await self.get_tenant_api_key(key_id)
        
        values.append(key_id)
        
        await self.user_manager._db.execute(
            f"UPDATE tenant_api_keys SET {', '.join(updates)} WHERE id = ?",
            values
        )
        await self.user_manager._db.commit()
        return await self.get_tenant_api_key(key_id)

    async def delete_tenant_api_key(self, key_id: int) -> bool:
        """Delete a tenant API key."""
        if not self.user_manager._db:
            await self.user_manager.init()
        cursor = await self.user_manager._db.execute(
            "DELETE FROM tenant_api_keys WHERE id = ?",
            (key_id,)
        )
        await self.user_manager._db.commit()
        return cursor.rowcount > 0

    async def update_key_last_used(self, key_id: int) -> bool:
        """Update the last_used_at timestamp for a key."""
        if not self.user_manager._db:
            await self.user_manager.init()
        now = time.time()
        await self.user_manager._db.execute(
            "UPDATE tenant_api_keys SET last_used_at = ? WHERE id = ?",
            (now, key_id)
        )
        await self.user_manager._db.commit()
        return True
