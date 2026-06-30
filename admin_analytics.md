# Admin Analytics — Complete System Documentation

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Data Model](#data-model)
4. [Usage Data Collection](#usage-data-collection)
5. [Cost Calculation](#cost-calculation)
6. [Backend API Reference](#backend-api-reference)
7. [Service Layer & Aggregation Pipelines](#service-layer--aggregation-pipelines)
8. [Frontend](#frontend)
9. [Key Gotchas & Edge Cases](#key-gotchas--edge-cases)
10. [File Reference](#file-reference)

---

## Overview

The Admin Analytics system provides the system administrator with visibility into:

- **Platform-wide KPIs**: total tenants, active tenants, conversations, messages, tokens, cost, leads, feedback
- **Per-model usage breakdown**: which LLM models are being used, how many tokens each consumes, and what it costs
- **Time-series trends**: daily messages, tokens, cost, and leads over a configurable period (7d / 30d / 90d / 1y)
- **Per-tenant usage table**: every tenant's messages, tokens, cost, model usage, leads, and feedback with pagination, sorting, and search
- **Tenant drill-down**: detailed KPIs, time-series, and model usage for a single tenant
- **Top tenants leaderboard**: ranked by messages, tokens, or cost
- **Jump to Tenant**: instant search bar to find and navigate to any tenant's analytics

All endpoints are admin-only (JWT cookie auth via `get_current_admin()`). No tenant access is needed.

---

## Architecture

```
Frontend (React / TypeScript / Vite / TailwindCSS)
  apps/dashboard/src/
    pages/AdminAnalytics.tsx       (platform overview page)
    pages/TenantAnalytics.tsx      (per-tenant drill-down page)
    components/analytics/
      KPICard.tsx                  (reusable KPI stat card)
      TimeSeriesChart.tsx          (recharts line chart wrapper)
      FeedbackBreakdown.tsx        (like/dislike pie chart)
      DateRangeFilter.tsx          (period selector dropdown)
      DataTable.tsx                (generic sortable/paginated table)
      ModelUsageTable.tsx          (per-model token/cost breakdown table)
    services/adminAnalytics.ts     (API client layer)
    interfaces/index.ts            (TypeScript type definitions)
         |
         | HTTP (admin JWT cookie via adminAxios)
         v
Backend (Python / FastAPI)
  backend/
    controllers/admin_analytics.py     (5 thin HTTP endpoints)
    services/admin_analytics_service.py (all MongoDB aggregation logic)
    services/llm/pricing.py            (centralized cost calculation)
    services/llm/factory.py            (extract_usage from LLM responses)
    services/chat_service.py           (persists usage per assistant message)
    core/auth.py                       (get_current_admin dependency)
    main.py                            (router registration + compound indexes)
         |
         | Motor (async MongoDB driver)
         v
MongoDB Collections
    conversations     (messages[].usage = token data, created_at, updated_at)
    tenants           (domain, plan, business_name)
    leads             (per-tenant lead count)
    message_feedback  (per-tenant like/dislike)
    visitors          (per-tenant visitor count)
```

---

## Data Model

### Conversations Collection

Each document represents one chat session. The key field for analytics is the embedded `messages[]` array.

```js
{
  _id: ObjectId,
  session_id: "sess_abc123",
  tenant_id: "tenant_xyz",
  current_url: "https://example.com/pricing",
  summary: "User asked about pricing tiers...",
  created_at: ISODate("2026-06-15T10:00:00Z"),   // set on first message via $setOnInsert
  updated_at: ISODate("2026-06-15T10:05:00Z"),   // set on every persist via $set
  messages: [
    { "role": "user", "content": "What are your pricing plans?" },
    {
      "role": "assistant",
      "content": "We offer three tiers: Free, Pro, and Enterprise...",
      "usage": {
        "prompt_tokens": 1234,
        "completion_tokens": 567,
        "total_tokens": 1801,
        "provider": "openai",
        "model": "gpt-4o-mini"
      }
    }
  ]
}
```

**Backward compatibility**:
- Old conversations without `created_at` are excluded from time-series queries (they simply never match `$match: {created_at: {$gte: start_date}}`)
- Messages without `usage` (user messages, old assistant messages) are aggregated as zeros via `$ifNull: ["$messages.usage.prompt_tokens", 0]`

### Compound Indexes (created on startup in main.py)

```python
db.conversations.create_index([("tenant_id", 1), ("created_at", -1)])
db.conversations.create_index([("tenant_id", 1), ("updated_at", -1)])
```

These support all analytics queries — every pipeline filters on `tenant_id` and sorts/filters by `created_at` or `updated_at`.

### Other Collections

| Collection | Key Fields | Used For |
|---|---|---|
| `tenants` | `tenant_id`, `domain`, `plan`, `business_name` | Tenant info lookup via `$lookup` |
| `leads` | `tenant_id`, `created_at` | Lead counts per tenant |
| `message_feedback` | `tenant_id`, `rating` ("like"/"dislike") | Feedback per tenant |
| `visitors` | `tenant_id`, `first_seen_at` | Visitor counts (tenant detail only) |

---

## Usage Data Collection

### Data Flow: LLM Call → MongoDB

```
LLM Provider API
       |
       v
services/llm/factory.py
  extract_usage(response, provider, model)    ← extracts tokens from LangChain metadata
  _LLMWrapper.astream()                       ← captures usage from stream chunks
       |
       v
services/chat_service.py
  _complete_answer() returns (answer, show_form, form_id, usage)
  _stream_answer() yields {answer, show_form, form_id, usage}
       |
       |  Every code path does:
       |  messages.append({"role": "assistant", "content": answer, "usage": usage})
       v
  _persist_conversation(turn, summary, messages)
       |
       |  db.conversations.update_one(
       |    {session_id: ...},
       |    {$set: {messages: messages, updated_at: now},
       |     $setOnInsert: {created_at: now}},
       |    upsert=True
       |  )
       v
MongoDB conversations collection
```

### extract_usage() — factory.py:15

Extracts token usage from a LangChain LLM response. Handles two formats:

1. **OpenAI format**: `response.response_metadata.token_usage` with keys `prompt_tokens`, `completion_tokens`, `total_tokens`
2. **Other providers**: `response.usage_metadata` with keys `input_tokens`, `output_tokens`, `total_tokens`

Always returns:
```python
{
    "prompt_tokens": int,
    "completion_tokens": int,
    "total_tokens": int,
    "provider": str,    # e.g. "openai", "groq", "openrouter"
    "model": str,       # e.g. "gpt-4o-mini", "llama-3.1-8b-instant"
}
```

Falls back to zeros if metadata is missing.

### Streaming Usage Capture — factory.py _LLMWrapper.astream()

In the streaming wrapper, the **final chunk** of the stream contains `usage_metadata`. This is captured and yielded in the last SSE event alongside the complete answer:

```python
# In _LLMWrapper.astream():
usage_meta = getattr(chunk, "usage_metadata", None)
if usage_meta:
    usage["prompt_tokens"] = getattr(usage_meta, "input_tokens", 0) or 0
    usage["completion_tokens"] = getattr(usage_meta, "output_tokens", 0) or 0
    usage["total_tokens"] = getattr(usage_meta, "total_tokens", 0) or 0
# ...
yield {"answer": full_answer, "show_form": show_form, "form_id": form_id, "usage": usage}
```

### Persistence — chat_service.py _persist_conversation()

```python
now = datetime.now(timezone.utc)
await db.conversations.update_one(
    {"session_id": turn.session_id},
    {"$set": {
        "tenant_id": turn.tenant["tenant_id"],
        "current_url": turn.current_url,
        "summary": summary,
        "messages": messages,        # ← full array with usage on assistant messages
        "updated_at": now,
    }, "$setOnInsert": {
        "created_at": now,           # ← only set on first insert
    }},
    upsert=True,
)
```

---

## Cost Calculation

### services/llm/pricing.py

Centralized pricing table. All prices are **USD per 1 million tokens**:

```python
PRICING = {
    # (provider, model): (prompt_price_per_1m, completion_price_per_1m)
    ("openai", "gpt-4o"):                    (2.50, 10.00),
    ("openai", "gpt-4o-mini"):               (0.15, 0.60),
    ("openai", "gpt-4o-turbo"):              (10.00, 30.00),
    ("openai", "gpt-3.5-turbo"):             (0.50, 1.50),
    ("groq", "llama-3.1-8b-instant"):        (0.05, 0.08),
    ("groq", "llama-3.1-70b-versatile"):     (0.59, 0.79),
    ("groq", "mixtral-8x7b-32768"):          (0.24, 0.24),
    ("openrouter", "anthropic/claude-3-haiku"):       (0.25, 1.25),
    ("openrouter", "meta-llama/llama-3.1-8b-instant"): (0.05, 0.08),
    ("openrouter", "google/gemini-2.0-flash-001"):     (0.10, 0.40),
}
DEFAULT_PRICING = (0.15, 0.60)  # fallback for unknown models
```

### calculate_cost(provider, model, prompt_tokens, completion_tokens) -> float

```python
cost = (prompt_tokens * prompt_price + completion_tokens * completion_price) / 1_000_000
return round(cost, 6)
```

Returns `0.0` if both token counts are zero or negative.

### How Cost Is Computed Per Endpoint

| Endpoint | Method |
|---|---|
| Platform overview | Sums `calculate_cost(provider, model, ...)` across all models in `model_usage[]` |
| Timeseries | Per-day cost = sum of `calculate_cost()` for each model's daily breakdown |
| Per-tenant usage | Per-tenant cost = sum of `calculate_cost()` across that tenant's `model_usage[]` |
| Tenant detail | Same as per-tenant |
| Top tenants | Uses `calculate_cost("openai", "gpt-4o-mini", ...)` as a rough estimate (acceptable for ranking only) |

All cost calculations use **actual provider/model** from the stored usage data, not hardcoded defaults (except top tenants ranking).

---

## Backend API Reference

All routes are prefixed with `/api` (set in main.py). All require admin JWT cookie auth via `Depends(get_current_admin)`.

### GET /api/admin/analytics/overview

**Purpose**: Platform-wide KPIs.

**No query params.**

**Response shape**:
```json
{
  "total_tenants": 25,
  "active_tenants": 12,
  "total_conversations": 1500,
  "total_messages": 8500,
  "total_tokens": 2450000,
  "prompt_tokens": 1800000,
  "completion_tokens": 650000,
  "estimated_cost": 0.89,
  "model_usage": [
    {
      "provider": "openai",
      "model": "gpt-4o-mini",
      "prompt_tokens": 1200000,
      "completion_tokens": 450000,
      "total_tokens": 1650000,
      "call_count": 3200,
      "cost": 0.45
    }
  ],
  "total_leads": 85,
  "lead_conversion": 5.7,
  "like_count": 320,
  "dislike_count": 45,
  "like_ratio": 87.7
}
```

**Note**: `active_tenants` counts tenants with `updated_at` in the last 30 days (always a fixed 30-day window, ignores period param). This is because we check tenant activity, not conversation activity.

**Aggregations (7 concurrent)**:
1. `db.tenants` → count all tenants
2. `db.conversations` → distinct `tenant_id` where `updated_at >= 30 days ago`
3. `db.conversations` → count all
4. `db.conversations` → unwind messages, match assistant role, sum tokens
5. `db.leads` → count all
6. `db.message_feedback` → group by rating, count likes/dislikes
7. `db.conversations` → unwind messages, group by (provider, model), sum tokens per model

---

### GET /api/admin/analytics/timeseries?period=30d

**Purpose**: Daily time-series for charting.

**Query params**:
- `period` (string, default `"30d"`): `7d`, `30d`, `90d`, `1y`, `custom`

**Response shape** (array):
```json
[
  {
    "date": "2026-06-01",
    "messages": 145,
    "conversations": 32,
    "tokens": 89000,
    "prompt_tokens": 67000,
    "completion_tokens": 22000,
    "cost": 0.0312,
    "leads": 5
  }
]
```

**Aggregations (3 concurrent)**:
1. Messages per day with model breakdown — two-stage `$group`:
   - Stage 1: group by `(date, provider, model)` → gets per-model daily tokens
   - Stage 2: group by `date` → sums messages/tokens, pushes `model_details[]`
   - Cost is calculated in Python from `model_details` (accurate per-model)
2. Conversations per day
3. Leads per day

The three result sets are merged into daily buckets in Python. Days with no data in one source get zeros for that field.

**Important**: Only conversations with `created_at` field are included. Conversations created before the analytics feature was deployed will not appear.

---

### GET /api/admin/analytics/tenants?page=1&limit=10&search=&sort=messages&order=desc&period=30d

**Purpose**: Paginated, sortable, searchable per-tenant usage table.

**Query params**:
- `page` (int, min 1, default 1)
- `limit` (int, 1-100, default 10)
- `search` (string, optional): regex search against `domain` and `business_name` (case-insensitive)
- `sort` (string, default `"messages"`): `messages`, `tokens`, `cost`, `leads`, `last_activity`
- `order` (string, default `"desc"`): `desc` or `asc`
- `period` (string, default `"30d"`)

**Response shape**:
```json
{
  "items": [
    {
      "tenant_id": "abc123",
      "domain": "example.com",
      "plan": "pro",
      "created_at": "2026-01-15T00:00:00Z",
      "conversations": 450,
      "visitors": 0,
      "messages": 2800,
      "prompt_tokens": 890000,
      "completion_tokens": 310000,
      "total_tokens": 1200000,
      "estimated_cost": 0.3185,
      "model_usage": [
        {
          "provider": "openai",
          "model": "gpt-4o-mini",
          "prompt_tokens": 750000,
          "completion_tokens": 260000,
          "total_tokens": 1010000,
          "call_count": 2100,
          "cost": 0.2685
        }
      ],
      "leads": 12,
      "likes": 45,
      "dislikes": 3,
      "like_ratio": 93.8,
      "last_activity": "2026-06-30T10:30:00Z"
    }
  ],
  "total": 25,
  "page": 1,
  "page_size": 10,
  "total_pages": 3
}
```

**Aggregations (5 concurrent)**:
1. Main pipeline: group conversations by `tenant_id`, sum tokens using `$map` + `$ifNull`, then `$lookup` tenants for domain/plan, then sort/paginate
2. Count pipeline: same as main + `$count`
3. Leads pipeline: group leads by `tenant_id`
4. Feedback pipeline: group by `(tenant_id, rating)`
5. Model pipeline: unwind messages, group by `(tenant_id, provider, model)`, sum tokens

Results are merged in Python: leads_map, feedback_map, and tenant_model_map are built from their respective pipelines, then combined into the final items array.

**Token summation pattern** (used in main pipeline to sum tokens across all messages in a conversation without unwinding):
```python
"prompt_tokens": {"$sum": {"$sum": {"$map": {
    "input": "$messages",
    "as": "m",
    "in": {"$ifNull": ["$$m.usage.prompt_tokens", 0]}
}}}}
```
This is more efficient than `$unwind` because it processes each conversation as one document.

---

### GET /api/admin/analytics/tenant/{tenant_id}?period=30d

**Purpose**: Deep drill-down for a single tenant.

**Path params**: `tenant_id` (string)

**Query params**: `period` (string, default `"30d"`)

**Returns 404** if tenant does not exist (checked via `db.tenants.find_one`).

**Response shape**:
```json
{
  "tenant": {
    "tenant_id": "abc123",
    "domain": "example.com",
    "plan": "pro",
    "business_name": "Example Corp",
    "created_at": "2026-01-15T00:00:00Z"
  },
  "kpi": {
    "conversations": 450,
    "visitors": 120,
    "messages": 2800,
    "prompt_tokens": 890000,
    "completion_tokens": 310000,
    "total_tokens": 1200000,
    "estimated_cost": 0.3185,
    "model_usage": [
      {
        "provider": "openai",
        "model": "gpt-4o-mini",
        "prompt_tokens": 750000,
        "completion_tokens": 260000,
        "total_tokens": 1010000,
        "call_count": 2100,
        "cost": 0.2685
      }
    ],
    "leads": 12,
    "lead_conversion": 2.7,
    "likes": 45,
    "dislikes": 3,
    "like_ratio": 93.8,
    "last_activity": "2026-06-30T10:30:00Z"
  },
  "timeseries": [
    {
      "date": "2026-06-01",
      "messages": 45,
      "tokens": 28000,
      "leads": 2
    }
  ]
}
```

**Aggregations (7 concurrent)**:
1. Conversation stats for this tenant (conversations, messages, tokens, last_activity)
2. Leads count for this tenant
3. Feedback for this tenant
4. Visitors count for this tenant
5. Model usage for this tenant
6. Time-series messages for this tenant
7. Time-series leads for this tenant

All pipelines are filtered to the single `tenant_id`.

---

### GET /api/admin/analytics/top-tenants?sort=messages&limit=10

**Purpose**: Top tenants leaderboard for the platform overview page.

**Query params**:
- `sort` (string, default `"messages"`): `messages`, `tokens`, or `cost`
- `limit` (int, 1-50, default 10)

**Response**: Array of tenant objects (same shape as `items[]` in the tenants endpoint, but simpler — no `model_usage`, `likes`, `dislikes`, `like_ratio`, `visitors`).

**Aggregations (2 concurrent)**:
1. Main pipeline: group by `tenant_id`, sum messages/tokens, `$lookup` tenants. If sorting by cost, adds `$addFields` with inline cost calculation using default mini pricing.
2. Leads pipeline: group leads by `tenant_id`

Final sort is done in Python (not MongoDB) because the cost field is calculated after the pipeline.

---

## Service Layer & Aggregation Pipelines

### services/admin_analytics_service.py

All functions are `async` and use `asyncio.gather()` to run independent MongoDB aggregations concurrently for maximum performance.

### Helper Functions

| Function | Purpose |
|---|---|
| `_parse_period(period)` | Converts `"7d"` -> `datetime` (7 days ago). Falls back to 30d for invalid/custom/empty. |
| `_model_usage_pipeline(tenant_id=None)` | Returns a MongoDB aggregation pipeline that groups messages by `(provider, model)` and sums tokens. Optional `tenant_id` filter. |
| `_build_model_usage(res)` | Transforms raw aggregation results into clean dicts with cost calculated via `calculate_cost()`. |

### _model_usage_pipeline (reused across 3 endpoints)

This pipeline is used by platform overview, per-tenant usage, and tenant detail:

```python
[
    {"$unwind": "$messages"},
    {"$match": {
        "messages.role": "assistant",
        "messages.usage.model": {"$ne": None}     # skip old messages without usage
    }},
    {"$group": {
        "_id": {
            "provider": {"$ifNull": ["$messages.usage.provider", "unknown"]},
            "model": {"$ifNull": ["$messages.usage.model", "unknown"]},
        },
        "prompt_tokens": {"$sum": {"$ifNull": ["$messages.usage.prompt_tokens", 0]}},
        "completion_tokens": {"$sum": {"$ifNull": ["$messages.usage.completion_tokens", 0]}},
        "total_tokens": {"$sum": {"$ifNull": ["$messages.usage.total_tokens", 0]}},
        "call_count": {"$sum": 1},
    }},
    {"$sort": {"total_tokens": -1}},
]
```

When `tenant_id` is provided, adds `"tenant_id": tenant_id` to the match stage.

### MongoDB Aggregation Patterns Used

| Pattern | Where Used | Purpose |
|---|---|---|
| `$unwind` | All model usage pipelines, timeseries | Flatten `messages[]` to process each message individually |
| `$match` | Everywhere | Filter by `role`, `usage.model`, `tenant_id`, `created_at` |
| `$group` | Everywhere | Aggregate by composite `_id` (date, tenant_id, provider+model) |
| `$lookup` | Tenants table, top tenants | Join `tenants` collection for domain/plan info |
| `$project` | Tenants table | Reshape documents, handle missing fields with `$ifNull` |
| `$map` + `$ifNull` | Token summation in tenants/detail | Sum tokens across messages without unwinding (more efficient) |
| `$addFields` + `$let` | Top tenants (cost sort) | Calculate cost in MongoDB for sorting |
| `$dateToString` | Timeseries | Convert `created_at` to `"YYYY-MM-DD"` string for daily grouping |
| `$setOnInsert` | Persistence | Set `created_at` only on first insert |
| `$count` | Count pipelines | Simple document counting |
| `$size` | Messages count | Count messages in array without unwinding |

### Key Design Decisions

1. **`$ifNull` everywhere**: Handles old messages without `usage` gracefully — aggregated as zeros
2. **Two-stage `$group` for timeseries**: First groups by `(date, provider, model)`, then groups by `date` to merge models back. This lets us calculate accurate per-model cost in Python.
3. **`$map` + `$ifNull` for token sums**: More efficient than `$unwind` for counting tokens across all messages in a conversation
4. **`asyncio.gather()`**: All independent aggregations run concurrently (e.g., 7 pipelines in platform overview)
5. **Python-side merging**: After aggregation, results are merged in Python (lookup maps, cost calculation) rather than complex MongoDB pipelines

---

## Frontend

### TypeScript Interfaces (interfaces/index.ts)

```typescript
interface ModelUsage {
  provider: string;        // "openai" | "groq" | "openrouter"
  model: string;           // "gpt-4o-mini" | "llama-3.1-8b-instant" | etc.
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  call_count: number;
  cost: number;            // USD, calculated from pricing table
}

interface PlatformOverview {
  total_tenants: number;
  active_tenants: number;
  total_conversations: number;
  total_messages: number;
  total_tokens: number;
  prompt_tokens: number;
  completion_tokens: number;
  estimated_cost: number;
  model_usage: ModelUsage[];
  total_leads: number;
  lead_conversion: number;  // percentage
  like_count: number;
  dislike_count: number;
  like_ratio: number;       // percentage
}

interface TimeSeriesPoint {
  date: string;             // "YYYY-MM-DD"
  messages: number;
  conversations: number;
  tokens: number;
  prompt_tokens: number;
  completion_tokens: number;
  cost: number;
  leads: number;
}

interface TenantUsage {
  tenant_id: string;
  domain: string;
  plan: string;
  created_at: string;
  conversations: number;
  visitors: number;
  messages: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  estimated_cost: number;
  model_usage: ModelUsage[];
  leads: number;
  likes: number;
  dislikes: number;
  like_ratio: number;
  last_activity: string | null;
}

interface TenantAnalyticsDetail {
  tenant: {
    tenant_id: string;
    domain: string;
    plan: string;
    business_name: string;
    created_at: string;
  };
  kpi: {
    conversations: number;
    visitors: number;
    messages: number;
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
    estimated_cost: number;
    model_usage: ModelUsage[];
    leads: number;
    lead_conversion: number;
    likes: number;
    dislikes: number;
    like_ratio: number;
    last_activity: string | null;
  };
  timeseries: TimeSeriesPoint[];
}
```

### API Client (services/adminAnalytics.ts)

| Function | Endpoint | Returns |
|---|---|---|
| `fetchOverview()` | `GET /admin/analytics/overview` | `PlatformOverview` |
| `fetchTimeseries(period)` | `GET /admin/analytics/timeseries` | `TimeSeriesPoint[]` |
| `fetchTenantsUsage(params)` | `GET /admin/analytics/tenants` | `PaginatedResponse<TenantUsage>` |
| `fetchTenantAnalytics(tenantId, period)` | `GET /admin/analytics/tenant/:id` | `TenantAnalyticsDetail` |
| `fetchTopTenants(sort, limit)` | `GET /admin/analytics/top-tenants` | `TenantUsage[]` |

All use `adminAxios` which sends JWT cookie for auth.

### Pages

**AdminAnalytics.tsx** — Platform overview page:
- 8 KPI cards in two rows (Tenants, Active, Messages, Tokens, Cost, Leads, Conversion, Like Ratio)
- 4 time-series charts (Messages, Tokens, Cost, Leads) via recharts
- Model Usage table showing per-model breakdown with provider badges
- Feedback breakdown (pie chart)
- Top Tenants table (clickable rows → navigate to tenant detail)
- Jump to Tenant search bar (debounced, dropdown with results)

**TenantAnalytics.tsx** — Per-tenant drill-down page:
- Back button → /admin/analytics
- Tenant header with domain, plan badge, join date
- 8 KPI cards (same structure as platform)
- 2 time-series charts (Messages, Tokens)
- Model Usage table
- Feedback breakdown
- Last activity timestamp

### Components

| Component | Purpose |
|---|---|
| `KPICard` | Reusable stat card with icon, value, subtitle, color class |
| `TimeSeriesChart` | Recharts `ResponsiveContainer` + `LineChart` wrapper with tooltip, axis formatting |
| `FeedbackBreakdown` | Like/dislike donut chart via recharts `PieChart` |
| `DateRangeFilter` | Dropdown with preset periods (7d, 30d, 90d, 1y) |
| `DataTable` | Generic sortable/paginated table with column definitions |
| `ModelUsageTable` | Specialized table for per-model token/cost breakdown with provider color badges and totals footer |

### Code Splitting

Routes use `React.lazy()` + `Suspense`. Recharts is split into its own chunk via Vite `manualChunks`:
- Main bundle: ~235KB (was 798KB before splitting)
- Recharts chunk: ~385KB (only loads on analytics pages)

---

## Key Gotchas & Edge Cases

1. **`$match` cannot use `$` prefix**: In MongoDB aggregation, `$match` stages use field names without `$` prefix. Using `$created_at` in `$match` causes `unknown top level operator` error. Always use `"created_at"` in `$match` and `"$created_at"` in `$group`/`$dateToString` expressions.

2. **Old conversations lack `created_at`**: Conversations created before the analytics feature was deployed do not have `created_at` or `updated_at` fields. They are excluded from all time-series and period-filtered queries. This is by design.

3. **Old assistant messages lack `usage`**: Messages created before usage tracking was implemented have no `usage` field. All aggregation pipelines use `$ifNull` to treat these as zero tokens.

4. **`active_tenants` uses fixed 30-day window**: The overview endpoint's `active_tenants` always counts the last 30 days regardless of the `period` param. This is intentional — it shows recent platform activity, not period-filtered activity.

5. **FastAPI `regex` deprecation**: The `regex` parameter in `Query()` is deprecated in favor of `pattern`. The tenants search endpoint does not use regex validation on the period param — `_parse_period()` handles invalid values gracefully.

6. **Top tenants cost is approximate**: When sorting by cost, the top-tenants endpoint uses `calculate_cost("openai", "gpt-4o-mini", ...)` as a rough estimate. This is acceptable because it only affects sort order, not displayed values.

7. **`visitors` is always 0 in tenants table**: The per-tenant usage table shows `visitors: 0`. Visitor data is only populated in the tenant detail endpoint (via a separate `db.visitors` aggregation).

---

## File Reference

| File | Lines | Purpose |
|---|---|---|
| `backend/services/admin_analytics_service.py` | ~733 | All MongoDB aggregation pipelines and business logic |
| `backend/controllers/admin_analytics.py` | ~63 | 5 thin FastAPI endpoints with admin auth |
| `backend/services/llm/pricing.py` | ~46 | Centralized pricing table and `calculate_cost()` |
| `backend/services/llm/factory.py` | ~176 | `extract_usage()` and streaming usage capture |
| `backend/services/chat_service.py` | ~784 | Usage persistence in `_persist_conversation()` |
| `backend/main.py` | — | Router registration (`admin_analytics.router`) and compound indexes |
| `apps/dashboard/src/interfaces/index.ts` | ~211 | All TypeScript type definitions |
| `apps/dashboard/src/services/adminAnalytics.ts` | ~55 | API client functions |
| `apps/dashboard/src/pages/AdminAnalytics.tsx` | ~341 | Platform analytics overview page |
| `apps/dashboard/src/pages/TenantAnalytics.tsx` | ~215 | Per-tenant analytics drill-down page |
| `apps/dashboard/src/components/analytics/ModelUsageTable.tsx` | ~83 | Per-model usage breakdown table component |
| `apps/dashboard/src/components/analytics/KPICard.tsx` | — | Reusable KPI stat card |
| `apps/dashboard/src/components/analytics/TimeSeriesChart.tsx` | — | Recharts line chart wrapper |
| `apps/dashboard/src/components/analytics/FeedbackBreakdown.tsx` | — | Like/dislike pie chart |
| `apps/dashboard/src/components/analytics/DateRangeFilter.tsx` | — | Period selector dropdown |
| `apps/dashboard/src/components/analytics/DataTable.tsx` | ~155 | Generic sortable/paginated table |
