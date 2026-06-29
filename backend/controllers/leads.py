import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request

from core.auth import db, get_current_tenant, verify_api_key
from models.requests import (
    LeadFormConfigCreateRequest,
    LeadFormConfigUpdateRequest,
    LeadSubmitRequest,
)
from views.responses import (
    LeadResponse,
    LeadFormConfigResponse,
    LeadFormFieldResponse,
    LeadSubmitResponse,
)
from services.llm.factory import get_llm
from repositories.lead_repository import LeadRepository, LeadFormConfigRepository

router = APIRouter(tags=["leads"])
lead_repo = LeadRepository()
form_config_repo = LeadFormConfigRepository()

_SUMMARIZE_PROMPT = (
    "Summarize the following conversation into one concise sentence "
    "capturing what the visitor was interested in or asking about. "
    "Keep it under 200 characters. Focus on the product/service they were enquiring about."
)


async def _summarize_context(context: str) -> str:
    if not context or len(context.strip()) < 10:
        return ""
    try:
        llm = get_llm("openai", "gpt-4o-mini")
        resp = await llm.ainvoke([
            {"role": "system", "content": _SUMMARIZE_PROMPT},
            {"role": "user", "content": context},
        ])
        return resp.content.strip()
    except Exception:
        return context.strip()[:200]


def _field_to_response(field: dict) -> LeadFormFieldResponse:
    return LeadFormFieldResponse(
        field_id=field["field_id"],
        label=field["label"],
        type=field["type"],
        required=field["required"],
        placeholder=field.get("placeholder"),
        options=field.get("options"),
        order=field["order"],
    )


def _config_to_response(config: dict) -> LeadFormConfigResponse:
    return LeadFormConfigResponse(
        form_id=config["form_id"],
        title=config["title"],
        fields=[_field_to_response(f) for f in config.get("fields", [])],
        trigger_instructions=config.get("trigger_instructions", ""),
        enabled=config.get("enabled", True),
        created_at=config["created_at"],
        updated_at=config["updated_at"],
    )


# ──────────────────────────────────────────────
#  Lead Form Config CRUD (Dashboard - cookie auth)
# ──────────────────────────────────────────────


@router.get("/lead-forms", response_model=list[LeadFormConfigResponse])
async def list_lead_forms(current_tenant: dict = Depends(get_current_tenant)):
    tenant_id = current_tenant["tenant_id"]
    configs = await form_config_repo.get_by_tenant(tenant_id)
    return [_config_to_response(c) for c in configs]


@router.post("/lead-forms", response_model=LeadFormConfigResponse)
async def create_lead_form(
    req: LeadFormConfigCreateRequest,
    current_tenant: dict = Depends(get_current_tenant),
):
    tenant_id = current_tenant["tenant_id"]
    now = datetime.now(timezone.utc)
    form_id = str(uuid.uuid4())

    fields = []
    for i, f in enumerate(req.fields):
        fields.append({
            "field_id": str(uuid.uuid4()),
            "label": f.label,
            "type": f.type,
            "required": f.required,
            "placeholder": f.placeholder,
            "options": f.options,
            "order": f.order if f.order else i,
        })

    config_data = {
        "form_id": form_id,
        "tenant_id": tenant_id,
        "title": req.title,
        "fields": fields,
        "trigger_instructions": req.trigger_instructions,
        "enabled": req.enabled,
        "created_at": now,
        "updated_at": now,
    }

    await form_config_repo.create(config_data)
    return _config_to_response(config_data)


@router.put("/lead-forms/{form_id}", response_model=LeadFormConfigResponse)
async def update_lead_form(
    form_id: str,
    req: LeadFormConfigUpdateRequest,
    current_tenant: dict = Depends(get_current_tenant),
):
    tenant_id = current_tenant["tenant_id"]
    existing = await form_config_repo.get_by_form_id(tenant_id, form_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Lead form not found")

    update_data: dict = {"updated_at": datetime.now(timezone.utc)}

    if req.title is not None:
        update_data["title"] = req.title
    if req.trigger_instructions is not None:
        update_data["trigger_instructions"] = req.trigger_instructions
    if req.enabled is not None:
        update_data["enabled"] = req.enabled
    if req.fields is not None:
        fields = []
        for i, f in enumerate(req.fields):
            fields.append({
                "field_id": str(uuid.uuid4()),
                "label": f.label,
                "type": f.type,
                "required": f.required,
                "placeholder": f.placeholder,
                "options": f.options,
                "order": f.order if f.order else i,
            })
        update_data["fields"] = fields

    await form_config_repo.update(tenant_id, form_id, update_data)
    updated = await form_config_repo.get_by_form_id(tenant_id, form_id)
    return _config_to_response(updated)


@router.delete("/lead-forms/{form_id}")
async def delete_lead_form(
    form_id: str,
    current_tenant: dict = Depends(get_current_tenant),
):
    tenant_id = current_tenant["tenant_id"]
    deleted = await form_config_repo.delete(tenant_id, form_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Lead form not found")
    return {"status": "ok"}


# ──────────────────────────────────────────────
#  Widget: get active form config (API key auth)
# ──────────────────────────────────────────────


@router.get("/widget/lead-form")
async def get_widget_lead_form(current_tenant: dict = Depends(verify_api_key)):
    tenant_id = current_tenant["tenant_id"]
    config = await form_config_repo.get_enabled_for_tenant(tenant_id)
    if not config:
        return None
    return _config_to_response(config)


@router.get("/widget/lead-form/{form_id}")
async def get_widget_lead_form_by_id(form_id: str, current_tenant: dict = Depends(verify_api_key)):
    tenant_id = current_tenant["tenant_id"]
    config = await form_config_repo.get_by_form_id(tenant_id, form_id)
    if not config or not config.get("enabled", True):
        return None
    return _config_to_response(config)


# ──────────────────────────────────────────────
#  Submit lead (supports both legacy + dynamic)
# ──────────────────────────────────────────────


@router.post("/leads", response_model=LeadSubmitResponse)
async def submit_lead(req: LeadSubmitRequest, request: Request, current_tenant: dict = Depends(verify_api_key)):
    tenant_id = current_tenant["tenant_id"]
    session_id = req.session_id or ""

    from core.rate_limiter import check_rate_limit, get_client_ip
    
    # 1. Limit by IP: 30 per minute
    ip = get_client_ip(request)
    if await check_rate_limit(f"rate_limit:leads:ip:{ip}", limit=30, window=60):
        raise HTTPException(status_code=429, detail="Too many lead submissions. Please try again later.")
        
    # 2. Limit by Session: 10 per minute
    if session_id:
        if await check_rate_limit(f"rate_limit:leads:session:{session_id}", limit=10, window=60):
            raise HTTPException(status_code=429, detail="Too many lead submissions for this session. Please try again later.")

    summary = await _summarize_context(req.message or "")

    # Build custom_fields from legacy fields if no custom_fields provided
    custom_fields = req.custom_fields or {}
    if req.name and "name" not in custom_fields:
        custom_fields["name"] = req.name
    if req.email and "email" not in custom_fields:
        custom_fields["email"] = req.email
    if req.phone and "phone" not in custom_fields:
        custom_fields["phone"] = req.phone

    lead = {
        "lead_id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "session_id": req.session_id,
        "name": req.name or custom_fields.get("name", ""),
        "email": req.email or custom_fields.get("email", ""),
        "phone": req.phone or custom_fields.get("phone", ""),
        "message": summary,
        "raw_context": req.message or "",
        "source_url": "",
        "form_id": req.form_id or "",
        "custom_fields": custom_fields,
        "created_at": datetime.now(timezone.utc),
    }

    await lead_repo.create(lead)

    return LeadSubmitResponse(success=True, message="Thank you! We'll get back to you soon.")


@router.get("/dashboard/leads")
async def list_leads(current_tenant: dict = Depends(get_current_tenant)):
    tenant_id = current_tenant["tenant_id"]
    leads = await lead_repo.get_by_tenant(tenant_id)
    return leads
