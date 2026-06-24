import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from core.auth import db, get_current_tenant, verify_api_key
from models.requests import EnquirySubmitRequest
from views.responses import LeadResponse, DashboardLeadResponse
from services.embedder import openai_client
from repositories.lead_repository import LeadRepository

router = APIRouter(tags=["leads"])
lead_repo = LeadRepository()

_SUMMARIZE_PROMPT = (
    "Summarize the following conversation into one concise sentence "
    "capturing what the visitor was interested in or asking about. "
    "Keep it under 200 characters. Focus on the product/service they were enquiring about."
)


async def _summarize_context(context: str) -> str:
    if not context or len(context.strip()) < 10:
        return ""
    try:
        resp = await openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": _SUMMARIZE_PROMPT},
                {"role": "user", "content": context},
            ],
            max_tokens=100,
            temperature=0.0,
        )
        return resp.choices[0].message.content.strip()
    except Exception:
        return context.strip()[:200]


@router.post("/leads", response_model=LeadResponse)
async def submit_lead(req: EnquirySubmitRequest, current_tenant: dict = Depends(verify_api_key)):
    tenant_id = current_tenant["tenant_id"]

    summary = await _summarize_context(req.message or "")

    lead = {
        "lead_id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "session_id": req.session_id,
        "name": req.name,
        "email": req.email,
        "phone": req.phone or "",
        "message": summary,
        "raw_context": req.message or "",
        "source_url": "",
        "created_at": datetime.now(timezone.utc),
    }

    await lead_repo.create(lead)

    return LeadResponse(success=True, message="Thank you! We'll get back to you soon.")


@router.get("/dashboard/leads")
async def list_leads(current_tenant: dict = Depends(get_current_tenant)):
    tenant_id = current_tenant["tenant_id"]
    leads = await lead_repo.get_by_tenant(tenant_id)
    return leads