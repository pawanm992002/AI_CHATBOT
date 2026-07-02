"""Pydantic v2 schemas for visitor profiles (simplified real-time classification)."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class VisitorProfileBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(..., max_length=500)
    response_instructions: Optional[str] = Field(None, max_length=2000)
    color: str = Field(default="#6366f1", pattern=r"^#[0-9a-fA-F]{6}$")
    enabled: bool = True


class VisitorProfileCreate(VisitorProfileBase):
    pass


class VisitorProfileUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    response_instructions: Optional[str] = Field(None, max_length=2000)
    color: Optional[str] = Field(None, pattern=r"^#[0-9a-fA-F]{6}$")
    enabled: Optional[bool] = None


class VisitorProfileResponse(VisitorProfileBase):
    profile_id: str
    tenant_id: str
    created_at: datetime
    updated_at: datetime
