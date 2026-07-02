# Visitor Categorization & Profiling System

## Overview

The visitor categorization system automatically classifies website visitors into predefined profiles based on their behavior, engagement patterns, and interaction data. It uses a two-tier approach: deterministic rule-based matching first, then an LLM-powered fallback for ambiguous cases.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Classification Engine                  │
│                                                           │
│  ┌─────────────┐    No Match    ┌──────────────────┐     │
│  │ Rule Engine  │ ─────────────►│  LLM Fallback    │     │
│  │ (5 rule types)│              │  (gpt-4o-mini)    │     │
│  └──────┬──────┘               └────────┬─────────┘     │
│         │ Match                          │ Match/None     │
│         ▼                                ▼                │
│  ┌─────────────────────────────────────────────┐         │
│  │           Visitor Document Updated           │         │
│  │  profile_id / profile_label / confidence     │         │
│  │  + profile_history (append-only audit log)   │         │
│  └─────────────────────────────────────────────┘         │
└─────────────────────────────────────────────────────────┘

Triggered by:
  - Auto-classification sweep (every 5 min, post-inactivity)
  - Manual reclassification (dashboard button)
```

---

## Profile Model

Each tenant defines a set of **visitor profiles** (e.g., "Ready to Buy", "Support Seeker", "Returning Customer"). A profile has:

| Field | Type | Description |
|---|---|---|
| `name` | string | Human-readable label (1–100 chars) |
| `description` | string | Optional description (up to 500 chars) |
| `color` | string | Hex color code for UI display (e.g. `#6366f1`) |
| `rules` | array | Ordered list of classification rules (see below) |
| `llm_criteria` | string | Free-text prompt for LLM fallback (up to 2000 chars) |
| `enabled` | bool | Whether the profile is active for classification |

---

## Rule Types

Each profile contains one or more rules. Rules are evaluated top-to-bottom; the first rule that matches wins for that profile.

### 1. Page Visited

Matches when the visitor has viewed a URL matching a pattern.

- **Field**: `pattern` — URL with wildcard support
- **Wildcard modes**:
  - `prefix*` — URL starts with prefix
  - `*suffix` — URL ends with suffix
  - `*contains*` — URL contains the substring
  - Exact match — URL equals pattern exactly
- **Example**: `/pricing*` matches `/pricing`, `/pricing/enterprise`, `/pricing?plan=pro`

### 2. Lead Form Field

Matches when a lead form submission contains a specific field value.

- **Fields**: `field_key` (form field name), `pattern` (case-insensitive substring)
- **Example**: `field_key: "company"`, `pattern: "acme"` — matches if any lead has `custom_fields.company` containing "acme"

### 3. Message Count (>=)

Matches when the visitor's total message count across all sessions meets or exceeds a threshold.

- **Field**: `count` (minimum message count)
- **Example**: `count: 5` — classifies visitors who have sent 5+ messages

### 4. Keyword Match

Matches when any of the visitor's messages contain a keyword (supports regex).

- **Field**: `keywords` — list of strings; each is tried as regex first, falls back to plain substring
- **Example**: `["enterprise", "discount", "pricing.*question"]` — matches messages containing any of these

### 5. UTM Source

Matches when the visitor's `utm_source` parameter matches one of the specified sources.

- **Field**: `sources` — list of UTM source values (case-insensitive)
- **Example**: `["google", "linkedin"]` — classifies visitors arriving from these channels

---

## Classification Flow

### Step 1: Rule-Based Evaluation

1. Load all enabled profiles for the tenant.
2. Sort profiles by highest rule priority (descending) — profiles with higher-priority rules are evaluated first.
3. For each profile, evaluate its rules in order.
4. **First match wins** — once a profile matches, stop immediately.
5. If matched, assign:
   - `profile_id` → the profile's UUID
   - `profile_label` → the profile's name
   - `profile_confidence` → **1.0** (deterministic)
   - `profile_history` entry with `source: "rule"`

### Step 2: LLM Fallback (if no rule match)

If no rules match any profile, the system falls back to LLM-based classification:

1. Only considers profiles that have `llm_criteria` set.
2. Builds a structured prompt containing:
   - Candidate profile names and their `llm_criteria` descriptions
   - Conversation summary (session count, message count, page views, lead count)
   - Full conversation transcript (last 30 messages, capped at 3000 chars)
   - Page views (last 10, capped at 1000 chars)
   - Lead submissions (last 5, capped at 1000 chars)
   - UTM source
3. Sends the prompt to `gpt-4o-mini`.
4. If the LLM returns a profile name (case-insensitive match), assigns it with:
   - `profile_confidence` → **0.85** (probabilistic)
   - `profile_history` entry with `source: "llm"`
5. If the LLM returns "NONE" or no match, the visitor stays unclassified.

### Step 3: Update Visitor Document

The visitor document in MongoDB is updated with:
- `profile_id`, `profile_label`, `profile_confidence`
- `last_classified_at` timestamp
- `profile_history` array — append-only audit log entry

---

## Auto-Classification Sweep

A background task runs every 5 minutes on server startup:

```
SWEEP_INTERVAL:   5 minutes
INACTIVITY_TIMEOUT: 5 minutes
```

**How it works**:

1. Every 5 minutes, queries MongoDB for visitors matching:
   - `last_seen_at < (now - 5 minutes)` — visitor has been inactive for 5+ minutes
   - `last_classified_at` is NULL **or** `last_classified_at < last_seen_at` — visitor has new activity since last classification
2. For each matching visitor, fires `classify_visitor(visitor_id, tenant_id, trigger="auto")` as a fire-and-forget async task.
3. Maximum delay before classification: **10 minutes** (5 min inactivity + 5 min sweep interval).

**Manual trigger**: Dashboard has a "Reclassify" button that calls the same function with `trigger="manual"`.

---

## Audit Trail

Every classification event appends to the visitor's `profile_history` array:

```json
{
  "profile_id": "uuid",
  "profile_label": "Ready to Buy",
  "assigned_at": "2026-07-02T10:30:00Z",
  "reason": "Page visited pattern matched: /pricing*",
  "source": "rule",
  "trigger": "auto"
}
```

| Field | Values | Description |
|---|---|---|
| `source` | `"rule"` / `"llm"` | How the classification was determined |
| `trigger` | `"auto"` / `"manual"` | Whether the sweep or a user triggered it |

---

## Confidence Scores

| Source | Confidence | Meaning |
|---|---|---|
| Rule match | 1.0 | Deterministic — visitor definitively matches |
| LLM match | 0.85 | Probabilistic — LLM inferred the profile |

This distinction allows downstream logic to weigh classifications differently if needed.

---

## Profile Usage in Chat

### Personalized Greetings

When a visitor sends a greeting query, the chat service checks `visitor.identity.name`:

- **Name known**: `"Hi {name}, welcome back to {business_name}! How can I help you today?"`
- **Name unknown**: `"Hello! Welcome to {business_name}. How can I help you today?"`

### Identity Context in System Prompt

If the visitor has a known identity (name), the system prompt includes:
> "The visitor's name is {name}. Naturally use their name in conversation when appropriate."

---

## Visitor Identity

Visitor identity (name, email, phone) can be set via:

1. **Lead form submissions** — automatically synced from lead `custom_fields` with `source_lead_id` tracking
2. **Dashboard manual entry** — PUT `/visitors/{visitor_id}/identity`
3. **Dashboard clear** — DELETE `/visitors/{visitor_id}/identity`

Identity is separate from profile classification but complements personalization.

---

## Dashboard UI

### Profile Management Page (`/visitor-profiles`)

Route: `PrivateRoute` (requires JWT auth via `/api/dashboard/tenants/me`).
Navigation: Listed as "Visitor Profiles" in sidebar with `Tag` icon from lucide-react.

#### Layout

Two-column layout: fixed-width sidebar (`w-72`) + scrollable editor panel.

#### Sidebar — Profile List

**"New Profile" button** at the top. Clicking sets `selectedId = 'new'`.

**Per-profile items** display:
1. **Color dot** — 2.5x2.5 rounded circle using the profile's `color` hex value
2. **Profile name** — truncated, styled violet when selected, slate otherwise
3. **Rule count + LLM indicator** — e.g. `"3 rules + LLM"` or `"2 rules"` (LLM shown only if `llm_criteria` is truthy)
4. **Enabled indicator dot** — `bg-emerald-400` (enabled) or `bg-slate-600` (disabled)
5. **Hover actions** (visible on group hover):
   - **Toggle** — `ToggleRight`/`ToggleLeft` icon, calls `PUT /visitor-profiles/{id}` with `{ enabled: !current }`
   - **Delete** — `Trash2` icon, requires `window.confirm()`, calls `DELETE /visitor-profiles/{id}`

**No search, filter, or sort controls** — all profiles are loaded and displayed as-is.

**Empty state**: Shows `Users` icon + "No profiles yet — click 'New Profile' to create one".

#### Editor Panel

**When no profile is selected**: Shows a placeholder "Select a profile to edit, or create a new one."

**When a profile is selected or "New Profile" is clicked**, the editor shows 5 sections:

##### Section 1: Profile Details
| Input | Type | Details |
|---|---|---|
| Name | text | Placeholder "Ready to buy", required |
| Color | color picker | Native `<input type="color">`, hex displayed next to it |
| Description | text | Placeholder "Visitors who are likely to purchase" |

##### Section 2: Profile Status Toggle
- Toggle button (`ToggleRight`/`ToggleLeft` icon, size 36)
- Label: "Active and used for visitor classification" / "Disabled and will not be assigned"
- Sends partial update: `{ enabled: !current }` (no other fields required)

##### Section 3: Rules Builder

Header: "Rules (first match wins)" + "Add Rule" button.

Each rule renders as a card with:
- Rule number ("Rule #1") + priority badge ("Priority: 0")
- Delete button (trash icon)
- Type dropdown (5 options):
  - Page Visited
  - Lead Form Field
  - Message Count >=
  - Keyword Match
  - UTM Source
- Priority number input (min 0)

**Type-specific fields:**

| Rule Type | Fields Displayed |
|---|---|
| `page_visited` | Single text input: "URL Pattern (supports wildcards)" — placeholder `/pricing*` |
| `lead_form_field` | Two-column grid: "Field Key" (placeholder "budget") + "Value Pattern" (placeholder "enterprise") |
| `message_count_gte` | Number input: "Minimum Message Count" — min 1, default 1 |
| `keyword_match` | Textarea (3 rows): "Keywords (one per line) regex supported" — placeholder: `pricing\ncost\nhow much` |
| `utm_source` | Textarea (3 rows): "UTM Sources (one per line)" — placeholder: `google\nfacebook\nlinkedin` |

**Data conversion**: `keywords` and `sources` arrays are joined with `\n` for textarea display on load, and split back to arrays on save.

**Empty rules state**: "No rules defined. Add rules or use LLM criteria below."

##### Section 4: LLM Criteria (Fallback)

Header: "LLM Criteria (fallback)" + help icon with tooltip:
> "Free-text description used for LLM-based fallback classification when no rules match. Describe the visitor behavior that fits this profile."

- Textarea (4 rows): placeholder "Visitors who ask about pricing, request demos, or inquire about enterprise plans..."
- Value is trimmed on save; empty string sent as `null`

##### Section 5: Save Button
- "Create Profile" (new) or "Update Profile" (existing)
- Shows spinner "Saving..." during API call
- Disabled when `saving` is true or `name.trim()` is empty

#### API Operations

| Operation | Endpoint | Payload |
|---|---|---|
| Fetch all | `GET /api/dashboard/visitor-profiles` | — |
| Create | `POST /api/dashboard/visitor-profiles` | `{ name, description, color, rules, llm_criteria, enabled }` |
| Update | `PUT /api/dashboard/visitor-profiles/{id}` | Same as create (partial updates supported) |
| Toggle | `PUT /api/dashboard/visitor-profiles/{id}` | `{ enabled: !current }` (partial) |
| Delete | `DELETE /api/dashboard/visitor-profiles/{id}` | — |

All requests go through `privateAxios` (JWT in HttpOnly cookie). The axios interceptor automatically prefixes `/api`.

After every create/update/delete/toggle, the full profile list is re-fetched.

**Delete cascade**: Deleting a profile clears `profile_id`/`profile_label`/`profile_confidence` from all visitors that had it assigned. The `profile_history` entries are preserved.

---

### Visitor Management Endpoints (Backend Only — No Frontend Page Yet)

The backend exposes full visitor CRUD but **no dashboard page currently consumes these endpoints**:

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/dashboard/visitors` | GET | Paginated list, filterable by `profile_id`, searchable by visitor_id/name/email |
| `/api/dashboard/visitors/{visitor_id}` | GET | Single visitor detail with leads |
| `/api/dashboard/visitors/{visitor_id}/reclassify` | POST | Manually trigger reclassification (`trigger="manual"`) |
| `/api/dashboard/visitors/{visitor_id}/profile` | PUT | Manually assign/unassign a profile (override) |
| `/api/dashboard/visitors/{visitor_id}/identity` | PUT | Set visitor identity (name, email, phone) |
| `/api/dashboard/visitors/{visitor_id}/identity` | DELETE | Clear visitor identity |

---

### Analytics — Profile Distribution

#### Tenant Analytics Page (`/admin/analytics/tenant/{tenantId}`)

**ProfileDistribution component** is rendered alongside other analytics widgets (model usage, feedback breakdown).

**Data fetching**:
- Secondary request after main analytics load: `GET /api/admin/analytics/tenant/{tenantId}/profile-stats`
- Uses `adminAxios` (separate admin JWT cookie, not tenant JWT)
- Failure is silently caught — profile stats are optional

**Response shape**:
```json
{
  "items": [
    { "profile_id": "uuid", "label": "Ready to Buy", "count": 42, "percentage": 35.2 },
    { "profile_id": null, "label": "Unclassified", "count": 15, "percentage": 12.5 }
  ],
  "total": 120
}
```

#### ProfileDistribution Component

Custom horizontal bar chart (pure HTML/CSS, no charting library).

**Per-item rendering**:
1. **Label + count/percentage**: `"Ready to Buy — 42 (35.2%)"`
2. **Progress bar**: `h-2` rounded bar with width set to `{percentage}%`

**Color logic**:
- **Unclassified** (`profile_id` is null): Static slate gray (`#475569`)
- **Classified profiles**: Cyclic HSL colors — `hsl(i * 60, 70%, 50%)` where `i` is the array index. This means the profile's configured `color` field is **not** used in the chart; colors are auto-assigned by position.

**Empty state**: Card with `Tag` icon + "No visitor profile data yet."

#### Profile Stats Endpoint (Duplicate)

Two backend endpoints serve profile distribution:
1. `GET /api/dashboard/visitor-profiles/stats` — tenant-authenticated (JWT cookie). **Not used by any frontend.**
2. `GET /api/admin/analytics/tenant/{id}/profile-stats` — admin-authenticated (admin JWT cookie). **Used by TenantAnalytics page.**

---

### Type Definitions

**Dashboard interfaces** (`apps/dashboard/src/interfaces/index.ts`):

```ts
interface VisitorProfile {
  profile_id: string;
  name: string;
  description: string;
  color: string;
  rules: ProfileRule[];
  llm_criteria?: string | null;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

interface ProfileRule {
  type: 'page_visited' | 'lead_form_field' | 'message_count_gte' | 'keyword_match' | 'utm_source';
  priority: number;
  pattern?: string;
  field_key?: string;
  count?: number;
  keywords?: string[];
  sources?: string[];
}

interface Visitor {
  visitor_id: string;
  name?: string | null;
  email?: string | null;
  phone?: string | null;
  profile_id?: string | null;
  profile_label?: string | null;
  profile_confidence?: number | null;
}
```

**Shared package** (`packages/shared/src/types.ts`):
- `Visitor` includes additional fields: `profile_history?: ProfileHistoryEntry[]`, `last_classified_at?: string | null`, `ip_history`, `page_views`
- `ProfileHistoryEntry`: `{ profile_id, profile_label, assigned_at, reason, source: 'rule' | 'llm', trigger?: 'auto' | 'manual' }`

---

## Multi-Tenant Isolation

All queries include `tenant_id` alongside `visitor_id` or `profile_id`. Profiles, visitors, and classification results are fully scoped per tenant — no cross-tenant data leakage is possible.

---

## Key Design Decisions

1. **Rule-first, LLM-fallback**: Deterministic rules are fast and cheap; LLM is reserved for ambiguous cases.
2. **First match wins**: Simplifies evaluation — no scoring or weighting across rules.
3. **Deferred classification**: Runs after inactivity, not during active chat, to avoid LLM costs and ensure sufficient data has accumulated.
4. **Append-only history**: Classification history is never overwritten — every assignment is preserved for auditing.
5. **Confidence encoding**: 1.0 vs 0.85 cleanly distinguishes deterministic from probabilistic classification.
6. **Profile deletion doesn't corrupt history**: Deleting a profile removes current assignment but keeps the audit trail intact.
