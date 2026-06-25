# Multi-LLM Support Refactor Plan

## Goal
Refactor the AI layer so every tenant can choose their preferred LLM provider and model from the dashboard.

- Keep chatbot architecture unchanged (RAG, crawling, vector search, auth, knowledge gaps, etc.)
- Only replace hardcoded OpenAI usage with a provider-agnostic LLM abstraction.
- Use LangChain **only** as the LLM abstraction layer (do **not** migrate business logic to LangChain).

---

## Requirements
### Providers to support
- OpenAI
- Groq
- OpenRouter

### Future providers
Addable later without modifying business logic, ideally only:
- `backend/services/llm/` module
- `backend/config/models.json`

### Architecture constraints
- No provider-specific code outside `backend/services/llm/`
- Single model per tenant
- All LLM calls must be routed through a single abstraction and use:
  - tenant.ai.provider
  - tenant.ai.model

---

## Proposed Module Structure
Create a new module:

```
backend/
  services/
    llm/
      __init__.py
      factory.py
      registry.py
```

---

## LLM Factory
Create a single function:

- `get_llm(provider, model)`

Returns the appropriate LangChain chat model:
- OpenAI → `ChatOpenAI`
- Groq → `ChatGroq`
- OpenRouter → `ChatOpenRouter`

Business logic must never know provider/model implementation details.

### Required call pattern
Replace any existing OpenAI direct usage:
- old:
  - `client.chat.completions.create(...)`
- new:
  - `llm = get_llm(provider, model)`
  - `response = await llm.ainvoke(messages)`

---

## Tenant Configuration
Extend tenant document:

### From
- `tenant`

### To
- `tenant.ai`:
```json
{
  "ai": {
    "provider": "groq",
    "model": "llama-3.3-70b-versatile"
  }
}
```

Only one model is selected per tenant, used across:
- Chat
- Query Rewrite
- Query Classification
- Suggested Questions
- Business Description
- Lead Summary
- Conversation Summaries

---

## Available Models Catalog
Add:

- `backend/config/models.json`

Example:
```json
[
  {
    "provider": "groq",
    "id": "llama-3.3-70b-versatile",
    "name": "Llama 3.3 70B",
    "input_price": 0.59,
    "output_price": 0.79
  },
  {
    "provider": "groq",
    "id": "qwen/qwen3-32b",
    "name": "Qwen3 32B",
    "input_price": 0.29,
    "output_price": 0.59
  },
  {
    "provider": "openrouter",
    "id": "deepseek/deepseek-chat-v3-0324",
    "name": "DeepSeek V3",
    "input_price": 0.27,
    "output_price": 1.10
  },
  {
    "provider": "openai",
    "id": "gpt-4.1-mini",
    "name": "GPT-4.1 Mini",
    "input_price": 0.40,
    "output_price": 1.60
  }
]
```

Backend should:
- read this file
- expose it via APIs
- **not** hardcode model names in frontend

Later: replace JSON with DB/provider sync without frontend changes.

---

## Dashboard UI
Add a simple “AI Model” section inside Settings.

UI requirements:
- AI Provider dropdown (OpenRouter / Groq / OpenAI)
- AI Model dropdown based on provider
- Estimated Pricing displayed (input/output)
- Save button

Constraints:
- No temperature/context/reasoning advanced settings
- No separate models per task
- Extremely simple UI

Save triggers:
- `PUT /tenants/ai`

---

## APIs
### Providers listing
`GET /providers`
Response:
```json
["OpenAI", "Groq", "OpenRouter"]
```

### Models listing
`GET /providers/{provider}/models`
Response:
```json
[
  {
    "id": "deepseek/deepseek-chat-v3-0324",
    "name": "DeepSeek V3",
    "input_price": 0.27,
    "output_price": 1.10
  }
]
```

### Tenant config save
`PUT /tenants/ai`

Request:
```json
{
  "provider": "groq",
  "model": "llama-3.3-70b-versatile"
}
```

Persist to tenant document under `tenant.ai`.

---

## Environment Variables
Support multiple providers:

- `OPENAI_API_KEY=`
- `GROQ_API_KEY=`
- `OPENROUTER_API_KEY=`

Future providers should only require adding another API key (plus module changes).

---

## Error Handling
If configured model cannot be initialized:
- log error
- fall back to default OpenAI model
- do not crash chatbot
- return meaningful error only if fallback fails too

This fallback logic belongs in `backend/services/llm/factory.py`.

---

## Design Principles
- Keep existing chatbot architecture unchanged
- Only abstract LLM calls
- Provider-specific code only in `backend/services/llm/`
- One model selection per tenant
- Easy to add providers later
- No unnecessary complexity

---

## Non-Goals
Do NOT implement:
- agent frameworks (LangGraph)
- LangSmith/tool routing
- multi-model orchestration
- per-task model selection
- AI workflows
- cost tracking/token analytics
- admin model management / auto sync

---

## Implementation Plan (with file-level sequencing)

### Phase 0 — Repo analysis (this is the planning stage)
1. Identify all existing OpenAI call sites.
2. Identify how `tenant` is resolved per request.
3. Identify where message payloads and parsing happen.

### Phase 1 — Create LLM abstraction module
Create:
- `backend/services/llm/__init__.py`
- `backend/services/llm/registry.py` (providers mapping)
- `backend/services/llm/factory.py` (get_llm + fallback/error handling)

### Phase 2 — Add tenant.ai defaults + persistence
Update tenant schema/repository so missing `tenant.ai` defaults safely:
- default provider: `openai`
- default model: match current default behavior (initially likely `gpt-4o-mini` or current existing default)

Update repositories/controllers responsible for:
- tenant creation
- tenant update
- tenant read for request handling

### Phase 3 — Replace OpenAI chat completions usage
Update call sites to:
- load tenant.ai.provider/model
- `llm = get_llm(provider, model)`
- `await llm.ainvoke(messages)`
- keep existing prompt composition and output parsing

Call sites expected to update (based on current search results):
- `backend/services/chat_service.py`
- `backend/services/suggested.py`
- `backend/services/crawler.py`
- `backend/controllers/leads.py`

### Phase 4 — Models catalog + backend APIs
Add:
- `backend/config/models.json`

Create endpoints:
- `GET /providers`
- `GET /providers/{provider}/models`
- `PUT /tenants/ai`

Add helper to load models.json and validate provider/model IDs.

### Phase 5 — Dashboard wiring
Update frontend:
- `apps/dashboard/src/pages/Settings.tsx`
- dashboard API calls and types under `apps/dashboard/src/api.ts` and relevant interfaces/models

Implement UI:
- provider dropdown triggers model list fetch
- save calls `PUT /tenants/ai`
- pricing shown from models.json response fields

### Phase 6 — Tests / verification
- Run backend lint/type checks
- Manually verify:
  - selecting provider+model changes output
  - missing/invalid model triggers fallback without crashing
  - endpoints serve provider/model lists correctly

---

## Notes on embeddings
The current code uses OpenAI embeddings in `backend/services/embedder.py`.

This task spec focuses on Chat + rewrite/classify/summarize flows.
Proposed for this phase:
- keep embeddings unchanged (still OpenAI)
- only refactor chat LLM usage first

If you later require embeddings provider selection, we’ll extend the abstraction for embeddings in a separate phase.

---

## Next step (required to start implementation)
Read the following files to lock down exact message formats and parsing behavior before writing the final edit plan:
- `backend/services/chat_service.py`
- `backend/services/suggested.py`
- `backend/services/crawler.py`
- `backend/controllers/leads.py`
- `backend/services/embedder.py`
