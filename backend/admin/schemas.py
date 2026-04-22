"""Pydantic schemas for admin API requests and responses."""
from __future__ import annotations

from typing import Optional, Any
from pydantic import BaseModel, Field


class UserResponse(BaseModel):
    id: int
    username: str
    email: Optional[str] = None
    is_admin: bool
    is_active: bool
    is_super_admin: bool
    role: str
    balance: float
    sso_provider: Optional[str] = None
    sso_provider_id: Optional[str] = None
    created_at: float
    updated_at: float


class UserUpdateRequest(BaseModel):
    is_active: Optional[bool] = None
    is_admin: Optional[bool] = None
    is_super_admin: Optional[bool] = None
    email: Optional[str] = None
    role: Optional[str] = None


class BalanceUpdateRequest(BaseModel):
    adjustment: float = Field(..., description="Amount to add (positive) or subtract (negative)")


class RedemptionCodeCreateRequest(BaseModel):
    amount: float = Field(..., ge=0, description="Amount each code is worth")
    count: int = Field(default=1, ge=1, le=100, description="Number of codes to generate")
    prefix: str = Field(default="PRISMA-", description="Code prefix")


class RedemptionCodeResponse(BaseModel):
    id: int
    code: str
    amount: float
    is_used: bool
    used_by: Optional[int] = None
    used_at: Optional[float] = None
    created_at: float


class RedeemCodeRequest(BaseModel):
    code: str = Field(..., min_length=1, description="Redemption code to redeem")


class ClearDataRequest(BaseModel):
    confirm: bool = Field(default=False, description="Must be true to confirm")


class UsageStatsResponse(BaseModel):
    total_requests: int
    total_cost: float
    requests_by_model: dict[str, int]
    cost_by_model: dict[str, float]


class CacheStatsResponse(BaseModel):
    enabled: bool
    ttl_seconds: int
    max_size: int
    current_size: int
    hit_rate: float


class CacheConfigRequest(BaseModel):
    enabled: bool = True
    ttl_seconds: int = Field(default=300, ge=0)
    max_size: int = Field(default=1000, ge=1)


class APIResponse(BaseModel):
    success: bool
    message: str
    data: Optional[Any] = None
    metadata: Optional[dict[str, Any]] = None
