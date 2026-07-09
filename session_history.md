# Session History — Architecture & Approaches

## 1. Current Architecture

### Storage Layers

| Layer | Purpose | TTL / Persistence |
|---|---|---|
| **Redis** (`chat_session:<session_id>`)| Active conversation context (summary + last ~30-60 messages) | 1 hour |
| **MongoDB** (`conversations` collection)| Persistent conversation storage with `summary`, `messages[]` array, and archive metadata | Permanent (until archived) |
| **DO Spaces** (JSONL parts, `conversations/<tenant>/<session>/archive_NNNN.jsonl`) | Cold storage for old turns | Permanent |

### Archival Triggers

1. **Overflow trigger** — When a single session exceeds 60 messages (30 turns * 2), the oldest messages are moved to DO Spaces as a new JSONL part. MongoDB keeps the most recent 60 messages. Compaction (summary LLM call) runs first when messages > 32, summarizing old ones into the `summary` field. Archival is a safety net when compaction hasn't been running enough and messages exceed 60.

   File: `archival_service._archive_overflow_inner()`

2. **Session-completion trigger** — When a visitor starts a new chat session (detected in `_upsert_visitor()`), old session IDs found in the visitor's `conversation_ids` are fully archived: all messages moved to DO Spaces, MongoDB `messages[]` set to `[]`, `archived=True`.

   File: `archival_service.archive_entire_session()`

### Full Conversation Reconstruction

`archival_service.get_full_conversation()` reads all JSONL parts sequentially from DO Spaces, reconstructs a flat `full_messages[]` array, and prepends it to any remaining in-db messages.

---

## 2. What Happens When a User Resumes an Archived Session

The widget's session history flow:

```
User clicks session in history
  → GET /widget/conversations/{session_id}
    → archival_service.get_full_conversation()
      → Read DO Spaces parts (JSONL) → archived_turns[]
      → Read MongoDB messages[] (likely empty if fully archived)
      → Return { full_messages: archived_turns + db_messages, summary }
  → Client sets sessionStorage (cw_session_id = old_session_id)
  → Client sets messages[] = full_messages from API
```

When user sends a new message in the resumed session:

```
Client → WS { session_id: <old_id>, query, ... }
  → _load_conversation_context(old_id, tenant)
    → Redis miss (expired) → MongoDB find → returns { summary, messages: [] }
  → _process_turn() runs with the summary only (no message history)
  → _persist_conversation() upserts the full messages array (accumulated by _process_turn):
    $set: { messages: [...all_messages], summary, updated_at }
    $setOnInsert: { created_at, archived: True, archive_key, archived_turn_count }
  → _track_visitor_message() adds session_id to visitor.conversation_ids
```

**Result**: Old messages stay in DO Spaces. New messages go into MongoDB `messages[]`. The LLM has access to the `summary` for context but not the raw old messages. `get_full_conversation()` returns both sources merged.

---

## 3. Approaches for Handling Continued Conversations on Archived Sessions

### A. Status Quo (Current)

**Mechanism**: New messages go to MongoDB `messages[]`, old stays in DO Spaces. `get_full_conversation()` merges on every read.

**Pros**:
- Zero additional implementation cost
- Writes stay fast and cheap (MongoDB local)
- DO Spaces reads are infrequent (only on history view)

**Cons**:
- Two sources of truth for a single conversation
- LLM only sees the `summary`, not raw old messages (could lose detail)
- If the user resumes a fully-archived session, the new conversation fragment lives in MongoDB, making future reads always hit DO Spaces + MongoDB

**Latency**: Write: ~10ms (MongoDB). Read: ~10-50ms (DO Spaces) + ~5ms (MongoDB).

---

### B. Append New Turns to DO Spaces

**Mechanism**: On each new turn in an archived session, write the new user+assistant messages as a new JSONL part in DO Spaces instead of storing in MongoDB.

On resume detection: check `conv.get("archived")`. If `True`, append new turns to DO Spaces as a new numbered part. MongoDB `messages[]` stays empty.

**Pros**:
- Single source of truth (DO Spaces)
- MongoDB stays lean
- Full raw message history always available for LLM context

**Cons**:
- DO Spaces has no atomic append — you must read-modify-write or use rolling numbered parts (already implemented)
- Each write involves a PUT request to DO Spaces (~20-50ms)
- If the session was only partially archived (overflow, not full), you'd need to flush the remaining MongoDB messages to DO Spaces first

**Latency**: Write: ~20-50ms (DO Spaces PUT). Read: same as current.

---

### C. De-archive on Resume

**Mechanism**: When a user sends a new message in a fully-archived session, pull the full history from DO Spaces, write it all back to MongoDB `messages[]`, and clear the archive (set `archived=False`, `archive_key=None`).

**Pros**:
- Single source of truth (MongoDB)
- No changes to the existing persistence/write path
- Full raw history available for LLM context

**Cons**:
- Expensive for long conversations (download + rewrite all archive parts)
- Defeats the purpose of archival (re-hydrates cold data to hot storage)
- Only helps if the user actually resumes; most sessions are never resumed

**Latency**: Write: ~100ms-2s (download + parse all archive parts + MongoDB update, depending on archive size). Subsequent writes: ~10ms (normal MongoDB).

---

### D. Hybrid: Archive-Only with Summary

**Mechanism**: MongoDB never stores `messages[]` for archived sessions — only `summary`. All turns (old + new) are written to DO Spaces as JSONL parts. The `summary` is updated via compaction LLM call and stored in MongoDB for fast context loading.

On session completion: archive all messages to DO Spaces. On resume: new turns append as new DO Spaces part. MongoDB only stores `summary` + `archived_turn_count`.

**Pros**:
- Single source of truth (DO Spaces)
- MongoDB stays small regardless of conversation length
- LLM always has `summary` for context (fast, no DO Spaces read needed for chat)

**Cons**:
- Every write is a DO Spaces PUT (~20-50ms)
- Summary may lose detail over time (same limitation as current compaction)
- Reading full history requires DO Spaces (same as current)

**Latency**: Write: ~20-50ms (DO Spaces PUT). Context load: ~5ms (MongoDB summary, no DO Spaces). Full read: ~10-50ms (DO Spaces).

---

### E. No Full Archival on Session End

**Mechanism**: Keep the overflow-only archival (for sessions > 60 messages), but remove the session-completion trigger (`_archive_old_sessions_bg`). Never fully empty MongoDB `messages[]` — only trim the oldest when overflowing.

**Pros**:
- Sessions always resume with full message context (no DO Spaces read needed)
- No two-source-of-truth problem
- Simplest mental model
- DO Spaces only used for extreme overflow cases

**Cons**:
- MongoDB `conversations` collection grows unboundedly per visitor
- Visitors with 100+ sessions each have 60 messages in hot storage
- Dashboard queries and aggregations become slower over time
- More expensive MongoDB Atlas storage

**Latency**: Write: ~10ms (MongoDB). Context load: ~5ms (MongoDB, no DO Spaces). Full read: ~5ms (MongoDB, no DO Spaces).

---

## 4. Summary Comparison

| Approach | Write Latency | Read Latency | Source of Truth | LLM Context Quality | Storage Cost | Complexity |
|---|---|---|---|---|---|---|
| **A. Status Quo** | 10ms | 10-50ms | Two (DO + Mongo) | Summary-only for archived | Low | None |
| **B. Append to DO Spaces** | 20-50ms | 10-50ms | DO Spaces only | Full raw history | Low | Medium |
| **C. De-archive on Resume** | 100ms-2s (first) / 10ms | 5ms | MongoDB only | Full raw history | Medium (re-hydrates) | Low |
| **D. Archive-Only + Summary** | 20-50ms | 10-50ms (full) / 5ms (context) | DO Spaces only | Summary-only (could augment) | Lowest | Medium |
| **E. No Full Archival** | 10ms | 5ms | MongoDB only | Full raw history | Highest | None |

## 5. Implementation (Chosen: De-archive Once on First Resume)

For a SaaS product where:
- Most users never revisit old sessions (<5% resume rate)
- MongoDB Atlas storage costs scale with document size
- Chat UX is the priority (low latency, complete context)

**Chosen approach: lazy de-archive-on-first-resume** — When a user resumes an archived session, the first `_load_conversation_context()` call pulls the full history from DO Spaces, writes it back to MongoDB `messages[]`, clears the archive flags (`archived=False`, `archive_key=None`), and caches in Redis. `archived_turn_count` is **preserved** at its prior value to prevent archive part numbering collisions on future re-archival. Subsequent turns behave as a normal live MongoDB-backed session until the next archival trigger (>60 messages or session-completion on a newer session).

This is effectively approach C (de-archive on resume) but scoped *only* to sessions that actually get resumed. Key properties:
- **One-time DO Spaces read per resumed session** — the read happens on the first turn; all subsequent turns read from Redis/MongoDB.
- **No repeated-read tax** — unlike the naive "read DO Spaces on every turn" variant, which would fire `get_full_conversation()` on turn 2, 3, 4... because `archived=True` persists via `$setOnInsert`.
- **Session re-archives naturally** — if the visitor later starts another new session, `_upsert_visitor()` will detect this session in `conversation_ids` and re-archive it. Or if the resumed session grows beyond 60 messages, the overflow trigger re-engages.

### Implementation

File: `chat_service._load_conversation_context()` (`backend/services/chat_service.py:623`)

```python
MAX_DEARCHIVE_MESSAGES = 120

if session.get("archived"):
    full = await archival_service.get_full_conversation(session_id, tenant_id)
    if full and full.get("full_messages"):
        full_messages = full["full_messages"]

        # Cap before the MongoDB write: the BSON 16MB limit applies at
        # find_one_and_update below. Compaction runs later, so it cannot
        # rescue a write that fails here.
        if len(full_messages) > MAX_DEARCHIVE_MESSAGES:
            full_messages = full_messages[-MAX_DEARCHIVE_MESSAGES:]

        result = await db.conversations.find_one_and_update(
            {"session_id": session_id, "tenant_id": tenant_id, "archived": True},
            {"$set": {
                "messages": full_messages,
                "archived": False,
                "archive_key": None,
                "updated_at": now,
            }},
        )
        if result is None:
            # Another request already de-archived — reload from Mongo
            session = await db.conversations.find_one(
                {"session_id": session_id, "tenant_id": tenant_id},
                {"messages": 1, "summary": 1},
            )
            messages = session.get("messages", []) if session else []
            summary = session.get("summary", "") if session else ""
        else:
            session["messages"] = full_messages
            session["archived"] = False
```

Key design choices:
- **120-message cap before write** — the cap guards the `find_one_and_update` against BSON 16MB limit. Compaction (`_compact_if_needed`) runs later in `_process_turn` and trims to 30, keeping the MongoDB doc small for ongoing turns.
- **No `archived_turn_count` reset** — preserved so overflow archival computes correct part numbers and never overwrites pre-resume JSONL parts.
- **`find_one_and_update` with `{archived: True}` filter** — atomic concurrency guard. If two requests race, only one writes; the loser re-reads from MongoDB.

---

## 6. Hardening the Implementation

Four real risks were identified in the as-implemented de-archive logic:

### 6.1 BSON 16MB Document Limit

MongoDB caps a single document at 16MB. A long-running conversation with 1000+ turns, especially with long assistant responses, tool calls, or embedded content, could plausibly hit this.

**Critical sequencing detail**: The `find_one_and_update` in the de-archive block writes to MongoDB **before** `_compact_if_needed` ever runs. Compaction only fires later inside `_process_turn`'s handler methods (after classification, search, and answer generation). A downstream safety net cannot rescue a write that already failed upstream.

**Fix**: Cap the restored message array at 120 messages **immediately before** the `find_one_and_update` call. This guarantees the MongoDB write stays well under 1MB regardless of conversation length. After the cap, the subsequent `_compact_if_needed` (fires at >32 messages in `_process_turn`) further trims to 30 messages for ongoing turns.

**Tradeoff**: The oldest messages beyond the 120 cap are dropped from MongoDB. They remain in DO Spaces (pre-resume archive parts are never deleted), but are not read for LLM context or display after de-archive. The existing `summary` field captures the gist of older context. For <5% resume rate, this is acceptable.

### 6.2 Concurrency Guard

Two concurrent WebSocket messages for the same resumed session (double-click send, retry after timeout, reconnect race) can both enter the de-archive branch before either write lands. Both do the DO Spaces read, both issue an `update_one`, and one turn's data can be silently lost.

**Fix**: Use `find_one_and_update` with `{archived: True}` as the filter predicate — atomically claims the de-archive. If it returns `None`, another request already handled it; re-read from MongoDB rather than re-writing. See the final implementation in Section 5.

If we lose the race, we did a redundant DO Spaces read (~200ms). That's acceptable — the LLM call (2-5s) dominates either way. The safety gain (no silent data loss) is worth the occasional duplicate read.

### 6.3 Archive Part Numbering Collision (Silent Data Loss)

After de-archiving, the original implementation reset `archived_turn_count` to `0`. When the session later re-archives (overflow trigger or new session-completion), the archival service computes:

```python
archive_part = conv.get("archived_turn_count", 0) // (MAX_TURNS * 2) + 1
```

With `archived_turn_count=0`, this produces `archive_part=1`, writing to `archive_0001.jsonl` — directly **overwriting** the original pre-resume archive part. All messages beyond the rehydration window are permanently lost.

**Fix**: Do **not** reset `archived_turn_count` during de-archive. Preserve its prior value. If a session had `archived_turn_count=500` before resume, overflow archival after resume computes `archive_part = 500 // 60 + 1 = 9`, safely writing to `archive_0009.jsonl` without colliding with pre-resume parts (`archive_0001` through `archive_0005`).

This is a one-line change: remove `archived_turn_count` from the de-archive `$set`. See the final implementation in Section 5.

### 6.4 Duplicate Messages in History After Re-archive (Accept as Display Artifact)

After de-archiving, the last 120 messages exist in two places: MongoDB `messages[]` and the untouched DO Spaces JSONL parts. This creates a window for duplicate messages in the display.

**During the de-archived window** (archived=False): no duplicates. `get_full_conversation()` returns the MongoDB doc directly at line 216 (`if not conv.get("archived"): return conv`), skipping the DO Spaces read entirely. The read-path filter already handles this case. This is the common path — user views history, chats a bit, closes the widget.

**After re-archival** (archived=True + overflow/session-completion fires): `get_full_conversation()` reads all pre-resume DO Spaces parts (which still contain the last 120) plus the post-resume data (MongoDB + new archive parts). The last ~60 messages appear twice in a 560+ message transcript. This is a display artifact affecting a fraction of a fraction of sessions (<5% resume × even fewer re-archive).

**Decision**: Accept this. The duplicate is minor (60 out of 560+), limited to display, and rare. Deleting the DO Spaces parts would fix it but permanently discards pre-resume conversation history — a worse outcome than a cosmetic display artifact for compliance, audit, and support-escalation use cases. The read-path filter already covers the common case.

A future enhancement could track a `de_archive_watermark` to skip pre-resume parts in `get_full_conversation()` after re-archival, eliminating the duplicate without deleting data. Not worth implementing now.

### 6.5 Redis Caching (Already Handled)

The doc prose says the rehydrated session "caches in Redis" but the code snippet only shows the MongoDB write. In the actual implementation, the existing `redis_client.setex` at the bottom of `_load_conversation_context` runs after the de-archive block and stores the restored `(summary, messages)` in Redis with a 1-hour TTL. Subsequent turns hit Redis, not MongoDB. No change needed.

---

## 7. Summary

| Risk | Severity | Fix | Status |
|---|---|---|---|
| BSON 16MB limit on de-archive write | **High (hard failure)** | 120-message cap before `find_one_and_update` | Pending |
| De-archive race | High (silent data loss) | `findOneAndUpdate` with `{archived: True}` filter | Pending |
| Archive part numbering collision | **High (silent permanent loss)** | Preserve `archived_turn_count` (don't reset) | Pending |
| Duplicate messages in history after re-archive | Medium (display artifact) | Accept; read-path filter covers common case. Low-severity display bug on fraction-of-fraction of sessions | Accept |
| ~90-message gap between cap and compaction | Medium (LLM context gap) | Captured by `summary` field | Accept |
| Compaction cost on very large histories | Medium (perf) | Capped at 120, handles 90ish messages | Accept |
| Orphaned DO Spaces parts | Low (storage) | Accept; parts preserved for retention policy | Accept |
| Redis caching | None (already done) | No change needed | Done |
