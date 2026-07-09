# AGENTS.md

Instructions for AI coding agents working on this codebase.

## Project Overview

Multi-tenant SaaS platform that lets clients crawl their websites, upload knowledge, and embed an AI-powered chat widget on their site. Uses RAG (Retrieval-Augmented Generation) with hybrid vector + BM25 search. Includes a **School ERP Module** for multi-tenant school data (students, fees, transport, hostel) with query safety and `/school` chat commands.

## Tech Stack

- **Backend**: Python 3.12+ / FastAPI / Uvicorn / Motor (MongoDB async) / Redis / LangChain (LLM + embeddings)
- **Frontend**: React 18 / TypeScript / Vite / TailwindCSS 4 / pnpm monorepo
- **Widget**: IIFE bundle injected via `<script>` tag, WebSocket streaming, CSS injection
- **Database**: MongoDB Atlas (vector search + text search)
- **Deployment**: PM2 / Nginx / GitHub Actions (EC2) / Render

## Repository Structure

```
backend/           # Python FastAPI application
  main.py          # App entry, middleware, startup
  core/            # Auth, config, Redis, schema validation
  controllers/     # FastAPI routers (HTTP handlers)
  services/        # Business logic (chat, search, ingestion, crawling)
  repositories/    # MongoDB data access layer
  models/          # Pydantic request/response schemas
  views/           # Pydantic response models
  templates/       # HTML test pages
  uploads/         # Uploaded PDF storage (gitignored)

apps/
  dashboard/       # React admin dashboard (SPA, cookie-based auth)
  widget/          # Embeddable chat widget (IIFE, API key auth)

packages/
  shared/          # @chatbot/shared - TypeScript types, hooks, components
```

## Commands

### Development
```bash
pnpm dev                    # Run all (backend :8000, dashboard :3000, widget :5174)
pnpm dev:backend            # FastAPI only (uvicorn --reload)
pnpm dev:dashboard          # Dashboard Vite dev server
pnpm dev:widget             # Widget Vite dev server
```

### Build
```bash
pnpm build                  # Build dashboard + widget
pnpm build:widget           # Widget IIFE bundle -> apps/widget/dist/widget.js
pnpm build:dashboard        # Dashboard -> apps/dashboard/dist/
```

### Production
```bash
pnpm start                  # Build + run uvicorn on port 8000
```

### Linting & Type Checking
```bash
# Frontend (per-app)
pnpm --filter dashboard lint
pnpm --filter widget lint

# Backend (pyright)
pyright

# Python dependency sync
uv sync
```

### Testing
```bash
# Widget locally
open backend/templates/test_page.html
```

## Code Conventions

### Backend (Python)
- Follow layered architecture: Controllers -> Services -> Repositories
- All routes use async/await with Motor for MongoDB operations
- Pydantic v2 for all request/response validation
- Auth: JWT in HttpOnly cookies for tenants, API key (Bearer) for widget
- Rate limiting: 3 layers — per-IP, per-tenant, per-session (Redis sorted sets, sliding window)
- Schema validation enforced on startup via JSON Schema in `core/schema_validator.py`
- Profile classification happens inline via the query rewrite LLM call (zero added latency) — no background sweep, persistent at the visitor level across all sessions
- All visitor/conversation queries must include `tenant_id` alongside `visitor_id` or `session_id` for multi-tenant isolation
- Language mirroring: the chatbot detects the user's language and replies in the same language (Hinglish, Hindi, English) via `_LANGUAGE_RULE` constant in chat prompts
- First-token buffering: the streaming pipeline buffers the first token to strip leading hallucinated artifacts (stray punctuation, markdown fragments) before streaming to the widget
- Explicit enquiry form confirmation: when the LLM triggers a lead form, the backend streams the text response first, then asks the visitor to confirm before rendering the form
- Archival Triggers:
  1) **Over-limit active turn compression**: moves oldest turns to DO Spaces if a single session exceeds 60 messages.
  2) **Session completion trigger**: fully archives previous sessions to DO Spaces in the background when a visitor initializes a new chat session.

### Frontend (TypeScript/React)
- Dashboard: SPA with react-router-dom, private/admin routes, TailwindCSS dark theme (slate-950)
- Widget: IIFE self-executing bundle, auto-initializes from `data-api-key` attribute
- Session management: uses `sessionStorage` for tab-bound `session_id` and `localStorage` for cross-session `visitor_id` persistence
- Widget UI: includes a "+" (New Chat) button in the header to reset the current session and clear message history while preserving the visitor's long-lived identity
- Shared types and hooks via `@chatbot/shared` workspace package
- Widget auth via `Authorization: Bearer <api_key>` header; WebSocket uses SHA-256 hashed key as query param

### Git
- `master` is the production branch (triggers EC2 deploy via GitHub Actions)
- `staging` is the staging branch (triggers separate EC2 deploy to staging environment on port 8001)
- Write concise commit messages matching repo style
- Never commit `.env` files or secrets

## Key Files

| File | Purpose |
|---|---|
| `backend/core/config.py` | Pydantic Settings, env variable loading |
| `backend/core/auth.py` | JWT creation/verification, API key auth, rate limiter |
| `backend/services/chat_service.py` | Core chat pipeline (classify, search, answer, tool calling for lead forms, log gaps, personalized greeting, school mode `/school`/`/exit`/`/logout`) — all conversation queries scoped by `(session_id, tenant_id)` |
| `backend/services/vector_search.py` | Hybrid vector + BM25 search |
| `backend/services/ingestion.py` | Document chunking/embedding pipeline |
| `backend/services/embedder.py` | OpenAI embeddings via LangChain `OpenAIEmbeddings` |
| `backend/services/llm/factory.py` | Provider-agnostic LLM factory (OpenAI, Groq, OpenRouter) — `get_llm()`, `get_llm_raw()`, `_to_lc_messages()`, `extract_usage()` |
| `backend/services/llm/pricing.py` | Centralized LLM pricing table and `calculate_cost()` for cost estimation |
| `backend/services/admin_analytics_service.py` | MongoDB aggregation pipelines for platform-wide analytics (overview, timeseries, per-tenant, model leaderboard) |
| `backend/services/archival_service.py` | Hot/cold conversation storage — archives old turns (>40 msgs) to DO Spaces, `_pending` set prevents concurrent archival per conversation |
| `backend/services/visitor_profile_service.py` | Real-time profile classification (inline via rewrite LLM call), profile context injection into system prompt |
| `backend/services/storage.py` | DigitalOcean Spaces upload/delete utility (S3-compatible) for PDF storage and conversation archival |
| `backend/services/pdf_parser.py` | PDF text extraction via PyMuPDF (fitz), page-by-page markdown formatting |
| `backend/config/models.json` | LLM model catalog — 20 models across 3 providers (OpenAI, Groq, OpenRouter) |
| `backend/repositories/knowledge_gap_repository.py` | CRUD for knowledge gaps with vector similarity deduplication |
| `backend/repositories/feedback_repository.py` | CRUD for message feedback (like/dislike) |
| `backend/repositories/source_repository.py` | CRUD for knowledge sources |
| `backend/repositories/source_job_repository.py` | Indexing job tracking (crawl, pdf_index, faq_index, text_index) |
| `backend/repositories/text_doc_repository.py` | CRUD for text documents |
| `backend/core/rate_limiter.py` | Redis-based sliding window rate limiter (per-IP, per-tenant, per-session) |
| `apps/widget/src/components/ErrorBoundary.tsx` | React error boundary preventing widget crashes from killing WebSocket |
| `apps/widget/src/components/EnquiryForm.tsx` | Dynamic lead form component rendered via LLM tool calling |
| `backend/core/schema_validator.py` | MongoDB JSON schema validators (29 collections) |
| `apps/widget/src/Widget.tsx` | Main widget component (WebSocket streaming) |
| `apps/widget/src/index.tsx` | Widget bootstrapper (reads `data-api-key` from script tag) |
| `apps/dashboard/src/App.tsx` | Dashboard router with private/admin routes |
| `apps/dashboard/src/pages/AdminAnalytics.tsx` | Platform-wide analytics page (KPIs, charts, model leaderboard, tenant search) |
| `apps/dashboard/src/pages/TenantAnalytics.tsx` | Per-tenant analytics drill-down page (includes profile distribution widget) |
| `apps/dashboard/src/pages/VisitorProfiles.tsx` | CRUD UI for visitor profiles with rule builder and LLM criteria |
| `apps/dashboard/src/components/analytics/TenantSelector.tsx` | Reusable tenant search dropdown component |
| `apps/dashboard/src/components/analytics/ModelUsageTable.tsx` | Per-model token/cost/latency breakdown table |
| `backend/models/visitor_profile.py` | Pydantic v2 schemas for visitor profiles (name, description, response_instructions, color, enabled) |
| `backend/repositories/visitor_profile_repository.py` | CRUD for visitor_profiles collection |
| `backend/controllers/visitor_profiles.py` | Dashboard JWT-authenticated routes for profile CRUD, visitor identity management |
| `backend/controllers/conversations.py` | Dashboard JWT-authenticated conversation detail + full history (merges DO Spaces archive) endpoints |
| `packages/shared/src/types.ts` | Shared TypeScript interfaces (includes VisitorProfile, Visitor, LeadFormField with field_role) |
| `scripts/seed_school_data.py` | Excel → MongoDB seeder for school ERP data (CLI: `--source-file`, `--dev`) |
| `backend/services/school_data_service.py` | NL→MongoDB query engine for school data, audit logging, session management, fee summary |
| `backend/services/school_data_filter.py` | Query safety allowlists + `build_safe_filter()` for school collections |
| `backend/models/school_data.py` | Pydantic v2 schemas for all 10 school entities + audit log |
| `backend/repositories/school_repository.py` | CRUD for schools, classes, sections |
| `backend/repositories/school_student_repository.py` | CRUD for students (search, get by admission, by class) |
| `backend/repositories/school_fee_repository.py` | CRUD for applied_fees + payments |
| `backend/repositories/school_transport_repository.py` | CRUD for routes, stops, transport_assign |
| `backend/repositories/school_hostel_repository.py` | CRUD for hostel_assign |
| `backend/tests/test_school_query_safety.py` | 16 unit tests for query safety |

## Database Collections

`tenants`, `sources`, `crawl_jobs`, `source_jobs`, `faqs`, `documents`, `chunks`, `parents`, `pages`, `leads`, `lead_form_configs`, `conversations`, `visitors`, `message_feedback`, `knowledge_gaps`, `visitor_profiles`, `school_teachers`, `school_classes`, `school_sections`, `school_students`, `school_applied_fees`, `school_payments`, `school_routes`, `school_stops`, `school_transport_assign`, `school_hostel_assign`, `school_audit_log`

## Environment Variables

Copy `.env.production.example` to `.env` and fill in:
- `MONGODB_URI` — MongoDB Atlas connection string
- `REDIS_URI` — Redis connection string
- `OPENAI_API_KEY` — OpenAI API key
- `FIRECRAWL_API_KEY` — Firecrawl API key
- `JWT_SECRET` — Secret for JWT signing
- `ALLOWED_ORIGINS` — Comma-separated allowed CORS origins
- `GROQ_API_KEY` — Groq API key (optional, for Groq provider)
- `OPENROUTER_API_KEY` — OpenRouter API key (optional, for OpenRouter provider)
- `DO_SPACES_ACCESS_KEY` — DigitalOcean Spaces access key (for PDF storage + conversation archival)
- `DO_SPACES_SECRET_KEY` — DigitalOcean Spaces secret key
- `DO_SPACES_ENDPOINT` — DigitalOcean Spaces endpoint URL (e.g. https://nyc3.digitaloceanspaces.com)
- `DO_SPACES_BUCKET` — DigitalOcean Spaces bucket name
