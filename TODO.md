# TODO - Multi-LLM Support Refactor

## Backend
- [ ] Create `backend/services/llm/` module:
  - [ ] `backend/services/llm/__init__.py`
  - [ ] `backend/services/llm/factory.py` with `get_llm(provider, model)` + fallback to default OpenAI
  - [ ] `backend/services/llm/registry.py` (provider mapping)
- [ ] Add `backend/config/models.json` (catalog)
- [ ] Add Models APIs:
  - [ ] `GET /providers`
  - [ ] `GET /providers/{provider}/models`
- [ ] Extend tenant document with `tenant.ai` defaults:
  - [ ] Update `backend/controllers/tenants.py` tenant registration to store `ai: { provider, model }`
  - [ ] Update `GET /tenants/me` response to include `ai`
- [ ] Add `PUT /tenants/ai`:
  - [ ] Validate provider + model against `models.json`
  - [ ] Persist to tenant doc under `tenant.ai`
- [ ] Refactor chat LLM call sites to use provider-agnostic abstraction:
  - [ ] `backend/services/chat_service.py`
  - [ ] `backend/services/suggested.py`
  - [ ] `backend/services/crawler.py` (business description generation)
  - [ ] `backend/controllers/leads.py` (lead summary)
- [ ] Keep embeddings unchanged:
  - [ ] Do NOT refactor `backend/services/embedder.py`

## Frontend (Dashboard)
- [ ] Update `apps/dashboard/src/api.ts` with calls:
  - [ ] `GET /providers`
  - [ ] `GET /providers/{provider}/models`
  - [ ] `PUT /tenants/ai`
- [ ] Update `apps/dashboard/src/pages/Settings.tsx`:
  - [ ] Add “AI Model” section (Provider dropdown + Model dropdown + pricing display + Save)
- [ ] Update frontend types/interfaces for `tenant.ai`

## Verification
- [ ] Run backend checks/tests (lint/type if available)
- [ ] Manual verification:
  - [ ] Selecting provider+model affects chat rewrite/classification/answer generation/summaries
  - [ ] Invalid model triggers fallback to default OpenAI without breaking chatbot
  - [ ] New endpoints return correct provider/model lists
