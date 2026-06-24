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


class ChatRequest(BaseModel):
    query: str
    session_id: Optional[str] = None
    current_url: str
    current_page_title: str


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
    rating: str = Field(..., pattern=r"^(like|dislike)$")


class SuggestedQuestionsUpdateRequest(BaseModel):
    questions: List[str]


class SettingsUpdateRequest(BaseModel):
    business_name: Optional[str] = None
    description: Optional[str] = None
    theme: Optional[str] = None
    suggested_questions_manual: Optional[List[str]] = None