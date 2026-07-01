# AGENTS.md

Instructions for AI coding agents working on this codebase.

## Project Overview

Multi-tenant SaaS platform that lets clients crawl their websites, upload knowledge, and embed an AI-powered chat widget on their site. Uses RAG (Retrieval-Augmented Generation) with hybrid vector + BM25 search.

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

### Testing Widget Locally
Open `backend/templates/test_page.html` in a browser to test the embedded widget.

## Code Conventions

### Backend (Python)
- Follow layered architecture: Controllers -> Services -> Repositories
- All routes use async/await with Motor for MongoDB operations
- Pydantic v2 for all request/response validation
- Auth: JWT in HttpOnly cookies for tenants, API key (Bearer) for widget
- Rate limiting: 3 layers — per-IP, per-tenant, per-session (Redis sorted sets, sliding window)
- Schema validation enforced on startup via JSON Schema in `core/schema_validator.py`

### Frontend (TypeScript/React)
- Dashboard: SPA with react-router-dom, private/admin routes, TailwindCSS dark theme (slate-950)
- Widget: IIFE self-executing bundle, auto-initializes from `data-api-key` attribute
- Shared types and hooks via `@chatbot/shared` workspace package
- Widget auth via `Authorization: Bearer <api_key>` header; WebSocket uses SHA-256 hashed key as query param

### Git
- `master` is the production branch (triggers EC2 deploy via GitHub Actions)
- Write concise commit messages matching repo style
- Never commit `.env` files or secrets

## Key Files

| File | Purpose |
|---|---|
| `backend/core/config.py` | Pydantic Settings, env variable loading |
| `backend/core/auth.py` | JWT creation/verification, API key auth, rate limiter |
| `backend/services/chat_service.py` | Core chat pipeline (classify, search, answer, tool calling for lead forms, log gaps, personalized greeting) |
| `backend/services/vector_search.py` | Hybrid vector + BM25 search |
| `backend/services/ingestion.py` | Document chunking/embedding pipeline |
| `backend/services/embedder.py` | OpenAI embeddings via LangChain `OpenAIEmbeddings` |
| `backend/services/llm/factory.py` | Provider-agnostic LLM factory (OpenAI, Groq, OpenRouter) — `get_llm()`, `get_llm_raw()`, `_to_lc_messages()`, `extract_usage()` |
| `backend/services/llm/pricing.py` | Centralized LLM pricing table and `calculate_cost()` for cost estimation |
| `backend/services/admin_analytics_service.py` | MongoDB aggregation pipelines for platform-wide analytics (overview, timeseries, per-tenant, model leaderboard) |
| `backend/services/archival_service.py` | Hot/cold conversation storage — archives old turns to DO Spaces, retrieves full history |
| `backend/services/visitor_profile_service.py` | Visitor classification (rule-based + LLM fallback) |
| `backend/core/rate_limiter.py` | Redis-based sliding window rate limiter (per-IP, per-tenant, per-session) |
| `apps/widget/src/components/ErrorBoundary.tsx` | React error boundary preventing widget crashes from killing WebSocket |
| `backend/core/schema_validator.py` | MongoDB JSON schema validators (18 collections) |
| `apps/widget/src/Widget.tsx` | Main widget component (WebSocket streaming) |
| `apps/widget/src/index.tsx` | Widget bootstrapper (reads `data-api-key` from script tag) |
| `apps/dashboard/src/App.tsx` | Dashboard router with private/admin routes |
| `apps/dashboard/src/pages/AdminAnalytics.tsx` | Platform-wide analytics page (KPIs, charts, model leaderboard, tenant search) |
| `apps/dashboard/src/pages/TenantAnalytics.tsx` | Per-tenant analytics drill-down page (includes profile distribution widget) |
| `apps/dashboard/src/pages/VisitorProfiles.tsx` | CRUD UI for visitor profiles with rule builder and LLM criteria |
| `apps/dashboard/src/components/analytics/TenantSelector.tsx` | Reusable tenant search dropdown component |
| `apps/dashboard/src/components/analytics/ModelUsageTable.tsx` | Per-model token/cost/latency breakdown table |
| `apps/dashboard/src/components/analytics/ProfileDistribution.tsx` | Visitor profile distribution bar chart widget |
| `backend/models/visitor_profile.py` | Pydantic v2 schemas for visitor profiles (create/update/response, rule discriminated unions) |
| `backend/repositories/visitor_profile_repository.py` | CRUD for `visitor_profiles` collection |
| `backend/controllers/visitor_profiles.py` | Dashboard JWT-authenticated routes for profiles, visitors, identity management |
| `backend/controllers/conversations.py` | Dashboard JWT-authenticated full conversation history endpoint |
| `packages/shared/src/types.ts` | Shared TypeScript interfaces (includes VisitorProfile, Visitor, LeadFormField with field_role)

## Database Collections

`tenants`, `sources`, `crawl_jobs`, `source_jobs`, `faqs`, `documents`, `chunks`, `parents`, `pages`, `leads`, `lead_form_configs`, `conversations`, `visitors`, `message_feedback`, `knowledge_gaps`, `visitor_profiles`

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
- `DO_SPACES_KEY` — DigitalOcean Spaces access key (for PDF storage + conversation archival)
- `DO_SPACES_SECRET` — DigitalOcean Spaces secret key
- `DO_SPACES_ENDPOINT` — DigitalOcean Spaces endpoint URL (e.g. https://nyc3.digitaloceanspaces.com)
- `DO_SPACES_BUCKET` — DigitalOcean Spaces bucket name
- `DO_SPACES_REGION` — DigitalOcean Spaces region (e.g. nyc3)
