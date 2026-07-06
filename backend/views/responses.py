from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str


class CrawlJobResponse(BaseModel):
    job_id: str


class SourceResponse(BaseModel):
    source_id: str
    source_type: str
    name: str
    status: str
    chunk_count: int
    config: dict
    created_at: datetime
    last_indexed_at: Optional[datetime] = None


class SourceCreateResponse(BaseModel):
    source_id: str
    source_type: str
    name: str
    status: str


class ChatSource(BaseModel):
    url: str
    title: str
    section_title: Optional[str] = None
    section_path: Optional[str] = None


class ChatResponse(BaseModel):
    message_id: str
    answer: str
    sources: List[ChatSource]
    suggested_form_id: str = ""
    suggested_form_title: str = ""


class WidgetConfigResponse(BaseModel):
    theme: str
    suggested_questions: List[str]
    show_sources: bool = True
    lead_form: Optional[dict] = None


class FAQResponse(BaseModel):
    faq_id: str
    source_id: str
    question: str
    answer: str
    created_at: datetime


class TextDocResponse(BaseModel):
    doc_id: str
    source_id: str
    title: str
    body: str
    created_at: datetime
    updated_at: datetime


class LeadResponse(BaseModel):
    success: bool
    message: str


class DashboardLeadResponse(BaseModel):
    lead_id: str
    name: str
    email: str
    phone: Optional[str] = None
    message: Optional[str] = None
    session_id: str
    source_url: Optional[str] = None
    created_at: datetime


class FeedbackResponse(BaseModel):
    status: str


class TenantResponse(BaseModel):
    tenant_id: str
    domain: str
    business_name: str
    email: str
    plan: str
    theme: str
    description: Optional[str] = None
    created_at: datetime
    api_key: Optional[str] = None
    suggested_questions_manual: List[str] = []
    suggested_questions_auto: List[str] = []
    show_sources: bool = True
    ai: Optional[dict] = None


class CrawlJobStatusResponse(BaseModel):
    job_id: str
    status: str
    seed_url: str
    pages_crawled: int
    chunks_created: int
    error: Optional[str] = None
    started_at: datetime
    finished_at: Optional[datetime] = None


class KnowledgeGapResponse(BaseModel):
    gap_id: str
    query: str
    url: str
    gap_type: str
    count: int
    status: str
    cluster_id: Optional[str] = None
    first_seen: datetime
    last_seen: datetime


class SettingsResponse(BaseModel):
    business_name: str
    domain: str
    email: str
    description: Optional[str] = None
    theme: str
    suggested_questions_manual: List[str] = []
    suggested_questions_auto: List[str] = []


class LeadFormFieldResponse(BaseModel):
    field_id: str
    label: str
    type: str
    required: bool
    placeholder: Optional[str] = None
    options: Optional[List[str]] = None
    order: int
    field_role: Optional[str] = None


class LeadFormConfigResponse(BaseModel):
    form_id: str
    title: str
    fields: List[LeadFormFieldResponse]
    trigger_instructions: str
    enabled: bool
    created_at: datetime
    updated_at: datetime


class LeadSubmitResponse(BaseModel):
    success: bool
    message: str


class OverviewStatsResponse(BaseModel):
    total_conversations: int
    total_messages: int
    total_leads: int
    total_sources: int
    knowledge_gaps_open: int
    knowledge_gaps_resolved: int