# Lead Form System — End-to-End Implementation Plan

## Guiding Principle

Identity (form_id, field_id) stays stable and structural everywhere; only display text (title, label, description) is allowed to change freely. Keep anything load-bearing out of free text.

---

## Phase 1: field_id Immutability (Authoring)

**Problem:** Backend regenerates all field_ids on every PUT. Frontend strips field_ids from the payload. A tenant renaming "Phone" to "Mobile Number" breaks every existing lead's field mapping.

**Backend — `backend/models/requests.py` `LeadFormFieldInput`:**
- Add `field_id: Optional[str] = None`

**Backend — `backend/controllers/leads.py` update endpoint (~line 137):**
- Accept `field_id` in incoming fields
- On update: if a field has a `field_id` that exists in the current form's fields array, preserve it; if empty/missing, generate a new UUID
- Existing fields keep their IDs across saves

**Frontend — `apps/dashboard/src/components/LeadFormBuilder.tsx`:**
- On save (~line 106): include `field_id` in the payload for existing fields
- On "Add Field": leave `field_id` as empty string (backend generates new UUID)
- On field removal: don't send that field, backend drops it from the array

---

## Phase 2: Caching (Triggering)

**Problem:** `get_all_enabled_for_tenant()` hits MongoDB on every single chat message. Unnecessary load for data that rarely changes mid-conversation.

**Fix — `backend/core/cache.py` (new file):**
- Add `get_cached_enabled_forms(tenant_id) -> list[dict]`
- Use Redis with 60s TTL
- Key pattern: `enabled_forms:{tenant_id}`
- Invalidate on form create/update/delete (in leads controller endpoints)

**Backend — `backend/controllers/leads.py`:**
- On create/update/delete of form configs, call `invalidate_enabled_forms_cache(tenant_id)`

**Backend — `backend/services/chat_service.py`:**
- Replace all 6 direct `form_config_repo.get_all_enabled_for_tenant()` calls with `get_cached_enabled_forms()`

---

## Phase 3: form_id Validation (Triggering)

**Problem:** `_complete_answer()` and `_complete_answer_stream()` accept any `form_id` the LLM returns. No cross-reference against the actual forms list. Defends against both bugs and model hallucination.

**Backend — `backend/services/chat_service.py`:**

**In `_complete_answer()` (~line 499):**
```python
if show_form:
    valid_ids = {f["form_id"] for f in (forms or [])}
    if form_id not in valid_ids:
        show_form = False
        form_id = ""
```

**In `_complete_answer_stream()` (~line 548):**
```python
if show_form:
    valid_ids = {f["form_id"] for f in (forms or [])}
    if form_id not in valid_ids:
        show_form = False
        form_id = ""
```

---

## Phase 4: Fallback Text from Form Title (Triggering)

**Problem:** Hardcoded "Let me get that for you!" reads as canned if it fires twice in a session. Should derive from the form's own title.

**Backend — `backend/services/chat_service.py`:**

**In `_complete_answer()` (~line 504):**
```python
if show_form and not answer:
    form_title = ""
    if forms:
        for f in forms:
            if f.get("form_id") == form_id:
                form_title = f.get("title", "")
                break
    answer = f"Sure, here's the {form_title}!" if form_title else "Let me get that for you!"
```

**In `_complete_answer_stream()` (~line 553):**
```python
if show_form and not full_answer:
    form_title = ""
    if forms:
        for f in forms:
            if f.get("form_id") == form_id:
                form_title = f.get("title", "")
                break
    fallback = f"Sure, here's the {form_title}!" if form_title else "Let me get that for you!"
    full_answer = fallback
    yield fallback
```

**Backend — `backend/controllers/chat.py`:**
- Update validation cleanup to match both fallback patterns:
```python
if result.answer.startswith("Sure, here's the") or result.answer == "Let me get that for you!":
    result.answer = "Let me help you with that."
```

---

## Phase 5: Rename custom_fields → values (Submission)

**Problem:** Payload key should be `values`, not `custom_fields`. Clean separation.

**Frontend — `apps/widget/src/components/EnquiryForm.tsx:53`:**
- Change `onSubmit({ custom_fields: trimmed, form_id: formId })` to `onSubmit({ values: trimmed, form_id: formId })`

**Frontend — `apps/widget/src/Widget.tsx:324`:**
- Change `custom_fields: formData.custom_fields` to `values: formData.values`

**Frontend — `apps/widget/src/api.ts:28`:**
- Update `EnquiryData` interface: rename `custom_fields` to `values`

**Backend — `backend/models/requests.py:106`:**
- Add `values: Optional[dict] = None`
- Keep `custom_fields: Optional[dict] = None` for backward compat

**Backend — `backend/controllers/leads.py`:**
- Prefer `req.values` over `req.custom_fields`:
```python
custom_fields = req.values or req.custom_fields or {}
```

**Backend — `backend/views/responses.py:77`:**
- Add `form_id: Optional[str] = None` and `custom_fields: Optional[dict] = None` to `DashboardLeadResponse`

---

## Phase 6: Dynamic Dashboard Table (Rendering)

**Problem:** Hardcoded name/email/phone/message/date columns don't match dynamic forms.

**Frontend — `apps/dashboard/src/pages/Leads.tsx`:**

**Add form filter to Leads tab:**
- Show the form sidebar (or a dropdown) in the Leads tab
- Add "All Forms" option at the top
- Selecting a form filters leads by `form_id`

**When a specific form is selected:**
- Build columns from `form.fields` sorted by `order`
- Headers = field labels + "Submitted" (date, fixed last column)
- Each row reads `lead.custom_fields[field_id]` (or `lead.values[field_id]`)
- Avatar/initials uses the first field value

**When "All Forms" is selected:**
- Show Form Name + Date columns
- Click a row to drill into that form's view

---

## Phase 7: Archived Fields + Legacy Leads (Dashboard)

**Problem:** Old leads with removed field_ids or no form_id are silently dropped from view.

**Frontend — `apps/dashboard/src/pages/Leads.tsx`:**

**Archived fields:**
- After building the column set from current form fields, scan all filtered leads for any `custom_fields` keys that don't match current field_ids
- Render those as "Archived: {label}" columns at the end of the table
- These columns show data from old leads that had fields since removed from the form

**Legacy submissions:**
- Detect leads without `form_id` or without `custom_fields`
- Render from top-level `name`/`email`/`phone` as a separate rendering path
- These are submissions from older widget versions before dynamic forms

---

## File Change Summary

| File | Changes |
|---|---|
| `backend/models/requests.py` | Add `field_id` to `LeadFormFieldInput`, add `values` to `LeadSubmitRequest` |
| `backend/controllers/leads.py` | Preserve field_ids on update, validate form_id, prefer `values` over `custom_fields` |
| `backend/controllers/chat.py` | Update fallback text cleanup pattern |
| `backend/services/chat_service.py` | Validate form_id, derive fallback from form title |
| `backend/core/cache.py` (new) | Redis cache for enabled forms with TTL |
| `backend/views/responses.py` | Add `form_id`, `custom_fields` to `DashboardLeadResponse` |
| `apps/dashboard/src/components/LeadFormBuilder.tsx` | Send field_ids on save |
| `apps/dashboard/src/pages/Leads.tsx` | Dynamic table columns, archived fields, form filter |
| `apps/widget/src/components/EnquiryForm.tsx` | Rename `custom_fields` → `values` |
| `apps/widget/src/Widget.tsx` | Rename `custom_fields` → `values` |
| `apps/widget/src/api.ts` | Update `EnquiryData` interface |
