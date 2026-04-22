"""FastAPI routes for admin endpoints."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Request, HTTPException, status, Depends

from ..auth_models import User
from .dependencies import require_admin, require_super_admin
from .schemas import (
    UserResponse,
    UserUpdateRequest,
    BalanceUpdateRequest,
    RedemptionCodeCreateRequest,
    RedemptionCodeResponse,
    RedeemCodeRequest,
    ClearDataRequest,
    UsageStatsResponse,
    CacheStatsResponse,
    CacheConfigRequest,
    APIResponse,
)

logger = logging.getLogger("monorelay.admin")

router = APIRouter(prefix="/api/admin", tags=["admin"])

user_router = APIRouter(prefix="/api", tags=["user"])


def api_response(data=None, message="OK", page=1, page_size=20, total=0):
    """Wrap admin API responses in standard envelope."""
    return {
        "success": True,
        "message": message,
        "data": data,
        "metadata": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "timestamp": datetime.now().isoformat()
        }
    }


@router.get("/users", response_model=APIResponse)
async def list_users(request: Request, _admin: User = Depends(require_admin)):
    """List all users (admin only)."""
    from ..main import auth_service

    users = await auth_service.user_manager.list_users()
    return api_response(data=[u.model_dump() for u in users])


@router.post("/users/{user_id}/balance", response_model=APIResponse)
async def update_user_balance(user_id: int, body: BalanceUpdateRequest, request: Request, _admin: User = Depends(require_admin)):
    """Update user balance (admin only)."""
    from ..main import auth_service

    success = await auth_service.user_manager.update_balance(user_id, body.adjustment)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")
    return api_response(message="余额已更新")


@router.delete("/users/{user_id}", response_model=APIResponse)
async def delete_user(user_id: int, request: Request, _admin: User = Depends(require_admin)):
    """Delete user (admin only)."""
    from ..main import auth_service

    if user_id == 0:
        raise HTTPException(status_code=400, detail="Cannot delete system admin")
    success = await auth_service.user_manager.delete_user(user_id)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")
    return api_response(message="用户已删除")


@router.put("/users/{user_id}", response_model=APIResponse)
async def update_user(user_id: int, body: UserUpdateRequest, request: Request, _admin: User = Depends(require_admin)):
    """Update user (admin only)."""
    from ..main import auth_service

    user = await auth_service.user_manager.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Build update dict from non-None fields
    updates = {}
    if body.is_active is not None:
        updates["is_active"] = body.is_active
    if body.is_admin is not None:
        updates["is_admin"] = body.is_admin
    if body.is_super_admin is not None:
        updates["is_super_admin"] = body.is_super_admin
    if body.email is not None:
        updates["email"] = body.email

    updated_user = await auth_service.user_manager.update_user(user_id, **updates)
    if not updated_user:
        raise HTTPException(status_code=500, detail="Failed to update user")

    return api_response(message="用户已更新", data={
        "id": updated_user.id,
        "username": updated_user.username,
        "email": updated_user.email,
        "is_active": updated_user.is_active,
        "is_admin": updated_user.is_admin,
        "is_super_admin": updated_user.is_super_admin,
    })


@router.get("/redemption-codes", response_model=APIResponse)
async def list_redemption_codes(request: Request, _admin: User = Depends(require_admin)):
    """List all redemption codes (admin only)."""
    from ..main import auth_service

    codes = await auth_service.user_manager.list_redemption_codes()
    return api_response(data=[c.model_dump() for c in codes])


@router.post("/redemption-codes", response_model=APIResponse)
async def create_redemption_codes(body: RedemptionCodeCreateRequest, request: Request, _admin: User = Depends(require_admin)):
    """Generate redemption codes (admin only)."""
    from ..main import auth_service

    codes = await auth_service.user_manager.generate_codes(
        body.amount, body.count, body.prefix
    )
    return api_response(data=codes)


@router.post("/clear-data", response_model=APIResponse)
async def clear_data(body: ClearDataRequest, request: Request, _admin: User = Depends(require_super_admin)):
    """Clear all local data and reset system (super admin only)."""
    from ..main import auth_service

    if not body.confirm:
        raise HTTPException(status_code=400, detail="Must confirm to clear data")

    logger.warning(f"SYSTEM RESET INITIATED BY {request.state.user.username}")

    try:
        import os
        import shutil
        from pathlib import Path

        data_dir = Path("./data")
        config_file = Path("./config.yml")

        await auth_service.user_manager.close()

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

        import signal
        os.kill(os.getpid(), signal.SIGINT)

        return api_response(message="System reset initiated")
    except Exception as e:
        logger.error(f"Reset failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@user_router.post("/user/redeem", response_model=APIResponse)
async def redeem_code(body: RedeemCodeRequest, request: Request):
    """Redeem a code (authenticated users)."""
    from ..main import auth_service

    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    amount = await auth_service.user_manager.redeem_code(user.id, body.code)
    if amount is None:
        raise HTTPException(status_code=400, detail="Invalid or already used redemption code")
    return api_response(message=f"成功兑换 ${amount:.2f}", data={"amount": amount})


@user_router.get("/usage/stats", response_model=APIResponse)
async def usage_stats(request: Request, client_id: Optional[str] = None):
    """Get usage statistics."""
    from ..main import usage_tracker

    return api_response(data=usage_tracker.get_stats(client_id))


@user_router.post("/usage/clear", response_model=APIResponse)
async def usage_clear(request: Request, client_id: Optional[str] = None):
    """Clear usage statistics."""
    from ..main import usage_tracker

    usage_tracker.clear(client_id)
    return api_response(message=f"Usage stats cleared{' for: ' + client_id if client_id else ''}")


@user_router.get("/cache/stats", response_model=APIResponse)
async def cache_stats(request: Request):
    """Get response cache statistics."""
    from ..main import response_cache

    return api_response(data=response_cache.stats())


@user_router.post("/cache/clear", response_model=APIResponse)
async def cache_clear(request: Request, model: Optional[str] = None):
    """Clear response cache."""
    from ..main import response_cache

    response_cache.invalidate(model)
    return api_response(message=f"Cache cleared{' for model: ' + model if model else ''}")


@user_router.post("/cache/enable", response_model=APIResponse)
async def cache_enable(body: CacheConfigRequest, request: Request):
    """Enable/disable response cache and configure parameters."""
    from ..main import response_cache

    if body.enabled:
        response_cache._max_size = body.max_size
        response_cache._ttl_seconds = body.ttl_seconds
    return api_response(
        data={
            "enabled": body.enabled,
            "ttl_seconds": response_cache._ttl_seconds,
            "max_size": response_cache._max_size
        }
    )


@router.get("/tenants", response_model=APIResponse)
async def list_tenants(request: Request, _admin: User = Depends(require_admin)):
    """List all tenants (admin only)."""
    from ..main import auth_service, tenant_manager

    users = await auth_service.user_manager.list_users()
    tenants = []
    for user in users:
        tenant_config = await tenant_manager.get_tenant_config(user.id)
        if tenant_config:
            tenants.append({
                "user_id": user.id,
                "username": user.username,
                "email": user.email,
                "has_config": True,
                "created_at": tenant_config.created_at,
                "updated_at": tenant_config.updated_at
            })
        else:
            tenants.append({
                "user_id": user.id,
                "username": user.username,
                "email": user.email,
                "has_config": False,
                "created_at": None,
                "updated_at": None
            })

    return api_response(data=tenants)


@router.get("/tenants/{user_id}", response_model=APIResponse)
async def get_tenant_config(user_id: int, request: Request, _admin: User = Depends(require_admin)):
    """Get tenant configuration (admin only)."""
    from ..main import auth_service, tenant_manager

    user = await auth_service.user_manager.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    tenant_config = await tenant_manager.get_tenant_config(user_id)
    if not tenant_config:
        return api_response(data={
            "user_id": user_id,
            "username": user.username,
            "email": user.email,
            "has_config": False,
            "config": None
        })

    import json
    config_data = json.loads(tenant_config.config_json)
    return api_response(data={
        "user_id": user_id,
        "username": user.username,
        "email": user.email,
        "has_config": True,
        "config": config_data,
        "created_at": tenant_config.created_at,
        "updated_at": tenant_config.updated_at
    })


@router.put("/tenants/{user_id}", response_model=APIResponse)
async def update_tenant_config(user_id: int, body: dict, request: Request, _admin: User = Depends(require_admin)):
    """Update tenant configuration (admin only)."""
    from ..main import auth_service, tenant_manager

    user = await auth_service.user_manager.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    config = body.get("config", {})
    existing = await tenant_manager.get_tenant_config(user_id)

    if existing:
        updated = await tenant_manager.update_tenant_config(user_id, config)
    else:
        created = await tenant_manager.create_tenant_config(user_id, config)
        updated = created

    if not updated:
        raise HTTPException(status_code=500, detail="Failed to update tenant config")

    return api_response(message="Tenant configuration updated")


@router.delete("/tenants/{user_id}", response_model=APIResponse)
async def delete_tenant_config(user_id: int, request: Request, _admin: User = Depends(require_admin)):
    """Delete tenant configuration (admin only)."""
    from ..main import auth_service, tenant_manager

    user = await auth_service.user_manager.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    success = await tenant_manager.delete_tenant_config(user_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete tenant config")
    
    return api_response(message="Tenant configuration deleted")


@router.get("/tenants/{user_id}/providers", response_model=APIResponse)
async def list_tenant_providers(user_id: int, request: Request, _admin: User = Depends(require_admin)):
    """List tenant providers (admin only)."""
    from ..main import auth_service, tenant_manager

    user = await auth_service.user_manager.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    providers = await tenant_manager.get_tenant_providers(user_id)
    return api_response(data=[p.model_dump() for p in providers])


@router.post("/tenants/{user_id}/providers", response_model=APIResponse)
async def create_tenant_provider(user_id: int, body: dict, request: Request, _admin: User = Depends(require_admin)):
    """Create tenant provider (admin only)."""
    from ..main import auth_service, tenant_manager

    user = await auth_service.user_manager.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    provider = await tenant_manager.create_tenant_provider(
        user_id=user_id,
        provider_name=body.get("provider_name"),
        enabled=body.get("enabled", True),
        base_url=body.get("base_url", ""),
        headers=body.get("headers", {}),
        models=body.get("models", {}),
        priority=body.get("priority", 100)
    )
    
    if not provider:
        raise HTTPException(status_code=500, detail="Failed to create tenant provider")
    
    return api_response(data=provider.model_dump())


@router.put("/tenants/{user_id}/providers/{provider_id}", response_model=APIResponse)
async def update_tenant_provider(user_id: int, provider_id: int, body: dict, request: Request, _admin: User = Depends(require_admin)):
    """Update tenant provider (admin only)."""
    from ..main import auth_service, tenant_manager

    user = await auth_service.user_manager.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    provider = await tenant_manager.update_tenant_provider(
        provider_id=provider_id,
        enabled=body.get("enabled"),
        base_url=body.get("base_url"),
        headers=body.get("headers"),
        models=body.get("models"),
        priority=body.get("priority")
    )
    
    if not provider:
        raise HTTPException(status_code=500, detail="Failed to update tenant provider")
    
    return api_response(data=provider.model_dump())


@router.delete("/tenants/{user_id}/providers/{provider_id}", response_model=APIResponse)
async def delete_tenant_provider(user_id: int, provider_id: int, request: Request, _admin: User = Depends(require_admin)):
    """Delete tenant provider (admin only)."""
    from ..main import auth_service, tenant_manager

    user = await auth_service.user_manager.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    success = await tenant_manager.delete_tenant_provider(provider_id, user_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete tenant provider")
    
    return api_response(message="Tenant provider deleted")


@router.get("/tenants/{user_id}/keys", response_model=APIResponse)
async def list_tenant_keys(user_id: int, request: Request, _admin: User = Depends(require_admin)):
    """List tenant API keys (admin only)."""
    from ..main import auth_service, tenant_manager

    user = await auth_service.user_manager.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    keys = await tenant_manager.get_tenant_api_keys(user_id)
    return api_response(data=[k.model_dump() for k in keys])


@router.post("/tenants/{user_id}/keys", response_model=APIResponse)
async def create_tenant_key(user_id: int, body: dict, request: Request, _admin: User = Depends(require_admin)):
    """Create tenant API key (admin only)."""
    from ..main import auth_service, tenant_manager

    user = await auth_service.user_manager.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    key = await tenant_manager.create_tenant_api_key(
        user_id=user_id,
        provider_name=body.get("provider_name"),
        key_value=body.get("key_value"),
        label=body.get("label", "default"),
        enabled=body.get("enabled", True),
        weight=body.get("weight", 1),
        rate_limit=body.get("rate_limit", 0),
        cooldown=body.get("cooldown", 0)
    )
    
    if not key:
        raise HTTPException(status_code=500, detail="Failed to create tenant API key")
    
    return api_response(data=key.model_dump())


@router.put("/tenants/{user_id}/keys/{key_id}", response_model=APIResponse)
async def update_tenant_key(user_id: int, key_id: int, body: dict, request: Request, _admin: User = Depends(require_admin)):
    """Update tenant API key (admin only)."""
    from ..main import auth_service, tenant_manager

    user = await auth_service.user_manager.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    key = await tenant_manager.update_tenant_api_key(
        key_id=key_id,
        enabled=body.get("enabled"),
        label=body.get("label"),
        weight=body.get("weight"),
        rate_limit=body.get("rate_limit"),
        cooldown=body.get("cooldown")
    )
    
    if not key:
        raise HTTPException(status_code=500, detail="Failed to update tenant API key")
    
    return api_response(data=key.model_dump())


@router.delete("/tenants/{user_id}/keys/{key_id}", response_model=APIResponse)
async def delete_tenant_key(user_id: int, key_id: int, request: Request, _admin: User = Depends(require_admin)):
    """Delete tenant API key (admin only)."""
    from ..main import auth_service, tenant_manager

    user = await auth_service.user_manager.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    success = await tenant_manager.delete_tenant_api_key(key_id, user_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete tenant API key")
    
    return api_response(message="Tenant API key deleted")
