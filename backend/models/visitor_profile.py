from pydantic import BaseModel, Field
from typing import List, Optional, Union, Literal, Annotated
from datetime import datetime

class PageVisitedRule(BaseModel):
    type: Literal["page_visited"] = "page_visited"
    pattern: str = Field(..., description="URL pattern to match (supports wildcards)")
    priority: int = Field(default=0, ge=0)

class LeadFormFieldRule(BaseModel):
    type: Literal["lead_form_field"] = "lead_form_field"
    field_key: str = Field(..., description="Key in lead custom_fields to check")
    pattern: str = Field(..., description="Value pattern to match")
    priority: int = Field(default=0, ge=0)

class MessageCountRule(BaseModel):
    type: Literal["message_count_gte"] = "message_count_gte"
    count: int = Field(..., ge=1, description="Minimum total messages across all sessions")
    priority: int = Field(default=0, ge=0)

class KeywordMatchRule(BaseModel):
    type: Literal["keyword_match"] = "keyword_match"
    keywords: List[str] = Field(..., min_length=1, description="Keywords or regex patterns to match in user messages")
    priority: int = Field(default=0, ge=0)

class UtmSourceRule(BaseModel):
    type: Literal["utm_source"] = "utm_source"
    sources: List[str] = Field(..., min_length=1, description="UTM source values to match")
    priority: int = Field(default=0, ge=0)

ProfileRule = Annotated[
    Union[
        PageVisitedRule,
        LeadFormFieldRule,
        MessageCountRule,
        KeywordMatchRule,
        UtmSourceRule,
    ],
    Field(discriminator="type")
]

class VisitorProfileBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    color: str = Field(default="#6366f1", pattern=r"^#[0-9a-fA-F]{6}$")
    rules: List[ProfileRule] = Field(default_factory=list)
    llm_criteria: Optional[str] = Field(default=None, max_length=2000)
    enabled: bool = True

class VisitorProfileCreate(VisitorProfileBase):
    pass

class VisitorProfileUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=500)
    color: Optional[str] = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    rules: Optional[List[ProfileRule]] = None
    llm_criteria: Optional[str] = Field(default=None, max_length=2000)
    enabled: Optional[bool] = None

class VisitorProfileResponse(VisitorProfileBase):
    profile_id: str
    tenant_id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class VisitorProfileHistoryEntry(BaseModel):
    profile_id: str
    profile_label: str
    assigned_at: datetime
    reason: str
    source: Literal["rule", "llm"]

class VisitorIdentity(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    updated_at: Optional[datetime] = None
    source_lead_id: Optional[str] = None

class VisitorProfileAssignment(BaseModel):
    profile_id: Optional[str] = None
    profile_label: Optional[str] = None
    profile_confidence: Optional[float] = Field(default=None, ge=0, le=1)
    profile_history: List[VisitorProfileHistoryEntry] = Field(default_factory=list)
    last_classified_at: Optional[datetime] = None