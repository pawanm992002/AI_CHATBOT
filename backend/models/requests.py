from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime


class TenantRegisterRequest(BaseModel):
    domain: str
    password: str
    business_name: str
    email: str
    plan: Optional[str] = "free"
    theme: Optional[str] = "default"
    description: Optional[str] = None


class TenantLoginRequest(BaseModel):
    domain: str
    password: str


class CrawlRequest(BaseModel):
    seed_url: str
    urls: Optional[List[str]] = None


class ChatRequest(BaseModel):
    query: str
    session_id: Optional[str] = None
    visitor_id: Optional[str] = None  # NEW
    current_url: str
    current_page_title: str


class DashboardSchoolChatRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    session_id: Optional[str] = None


class SourceCreateRequest(BaseModel):
    source_type: str = Field(..., pattern=r"^(pdf|faq|text|website)$")
    name: str


class FAQCreateRequest(BaseModel):
    question: str
    answer: str


class FAQUpdateRequest(BaseModel):
    question: Optional[str] = None
    answer: Optional[str] = None


class TextDocCreateRequest(BaseModel):
    title: str
    body: str


class TextDocUpdateRequest(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None


class EnquirySubmitRequest(BaseModel):
    name: str
    email: str
    phone: Optional[str] = None
    message: Optional[str] = None
    session_id: str


class FeedbackRequest(BaseModel):
    message_id: str
    session_id: str
    visitor_id: Optional[str] = None  # NEW
    rating: str = Field(..., pattern=r"^(like|dislike)$")


class SuggestedQuestionsUpdateRequest(BaseModel):
    questions: List[str]


class SettingsUpdateRequest(BaseModel):
    business_name: Optional[str] = None
    description: Optional[str] = None
    theme: Optional[str] = None
    suggested_questions_manual: Optional[List[str]] = None


class LeadFormFieldInput(BaseModel):
    label: str
    type: str = Field(..., pattern=r"^(text|email|phone|textarea|select|checkbox)$")
    required: bool = False
    placeholder: Optional[str] = None
    options: Optional[List[str]] = None
    order: int = 0
    field_role: Optional[str] = Field(default=None, pattern=r"^(name|email|phone)?$")


class LeadFormConfigCreateRequest(BaseModel):
    title: str
    fields: List[LeadFormFieldInput]
    trigger_instructions: str = ""
    enabled: bool = True


class LeadFormConfigUpdateRequest(BaseModel):
    title: Optional[str] = None
    fields: Optional[List[LeadFormFieldInput]] = None
    trigger_instructions: Optional[str] = None
    enabled: Optional[bool] = None


class LeadSubmitRequest(BaseModel):
    form_id: Optional[str] = None
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    message: Optional[str] = None
    session_id: str
    visitor_id: Optional[str] = None  # NEW
    custom_fields: Optional[dict] = None
