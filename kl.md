# Plan: Persistent Visitor ID + "New Chat" Button

## Goal

1. Uniquely identify a visitor across multiple sessions (persistent visitor_id).
2. Add a "New Chat" button in the widget that starts a fresh session under the same visitor.
3. Store every session's chat linked to that visitor in MongoDB.

---

## Architecture

### Current (broken)

- `visitor_id = session_id` (1:1, same UUID)
- Widget reads `session_id` from cookie → always returns `''` (cookie never set by WebSocket)
- Every WebSocket message generates a new UUID → zero conversation continuity
- No "New Chat" button

### New

```
Widget (browser)
  localStorage:   visitor_id = "abc-def-123"    ← generated once, persists forever
  sessionStorage: session_id = "xyz-789"         ← per tab / per "New Chat" click
                                              ↓
WebSocket sends: { query, session_id, visitor_id }
                                              ↓
Backend:
  _upsert_visitor(visitor_id, session_id)
    → visitors collection:  { visitor_id: "abc-def-123", conversation_ids: ["xyz-789", ...] }
  handle_message(session_id)
    → conversations collection: { session_id: "xyz-789", messages: [...] }

"New Chat" clicked:
  → resetSessionId() → "new-session-456"
  → messages cleared in UI
  → next WS message: { session_id: "new-session-456", visitor_id: "abc-def-123" }
  → new conversation created, linked to same visitor
```

---

## Widget Changes

### 1. `apps/widget/src/utils/constants.ts`

Add three functions:

```typescript
export const VISITOR_STORAGE_KEY = 'cw_visitor_id';
export const SESSION_STORAGE_KEY = 'cw_session_id';

export function generateId(): string {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
    const r = Math.random() * 16 | 0;
    return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
  });
}

export function getVisitorId(): string {
  let id = localStorage.getItem(VISITOR_STORAGE_KEY);
  if (!id) {
    id = generateId();
    localStorage.setItem(VISITOR_STORAGE_KEY, id);
  }
  return id;
}

export function getSessionId(): string {
  let id = sessionStorage.getItem(SESSION_STORAGE_KEY);
  if (!id) {
    id = generateId();
    sessionStorage.setItem(SESSION_STORAGE_KEY, id);
  }
  return id;
}

export function resetSessionId(): string {
  const id = generateId();
  sessionStorage.setItem(SESSION_STORAGE_KEY, id);
  return id;
}
```

Remove the old cookie-based `getSessionId()`. The new `getSessionId()` uses `sessionStorage` — persists per tab, clears on tab close or "New Chat".

---

### 2. `apps/widget/src/Widget.tsx`

**Imports:**
- Add `getVisitorId`, `resetSessionId` to the import from `./utils/constants`
- Remove `getSessionId` from import (it's still in constants, but we'll update the reference)

**New state:** (optional, visitor_id doesn't need to be React state since it never changes)
- Can call `getVisitorId()` directly wherever needed

**`handleNewSession()` callback:**

```typescript
const handleNewSession = useCallback(() => {
  resetSessionId();
  setMessages([]);
  sessionStorage.removeItem(`${HISTORY_STORAGE_KEY_PREFIX}${apiKey}`);
  // visitor_id stays the same — persistent across sessions
}, [apiKey]);
```

**WebSocket message payload** (line ~282):
Add `visitor_id: getVisitorId()`:

```typescript
ws.send(JSON.stringify({
  type: 'message',
  query: text,
  current_url: window.location.href,
  current_page_title: document.title,
  session_id: getSessionId(),
  visitor_id: getVisitorId(),   // ← NEW
}));
```

**Lead form submission** (line ~328):
Add `visitor_id: getVisitorId()` to the submit payload.

**Feedback submission** (line ~344):
Add `visitor_id: getVisitorId()` to the submit payload.

**Header usage** (line ~426):
Pass `onNewSession` prop:
```tsx
<Header palette={palette} onClose={() => setIsOpen(false)} onNewSession={handleNewSession} />
```

---

### 3. `apps/widget/src/components/Header.tsx`

**Props:** Add `onNewSession: () => void`

**Render:** Add a "New Chat" button before the close button:

```tsx
<button
  onClick={onNewSession}
  aria-label="New Chat"
  className="..."
  style={{ color: palette.headerText }}
>
  {/* Plus icon */}
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
    <line x1="12" y1="5" x2="12" y2="19" />
    <line x1="5" y1="12" x2="19" y2="12" />
  </svg>
</button>
```

Put it next to the close (X) button, same style.

---

## Backend Changes

### 4. `backend/models/requests.py`

Add `visitor_id` field to `ChatRequest`:

```python
class ChatRequest(BaseModel):
    query: str
    session_id: Optional[str] = None
    visitor_id: Optional[str] = None   # NEW
    current_url: str
    current_page_title: str
```

---

### 5. `backend/services/chat_service.py`

**`ChatTurnInput` dataclass** — add `visitor_id`:

```python
@dataclass
class ChatTurnInput:
    tenant: dict
    session_id: str
    visitor_id: str = ""     # NEW
    query: str
    current_url: str = ""
    current_page_title: str = ""
    message_id: str = ""
```

**`_track_visitor_message()`** — accept and use `visitor_id`:

```python
async def _track_visitor_message(self, session_id: str, visitor_id: str, tenant_id: str) -> None:
    await db.visitors.update_one(
        {"visitor_id": visitor_id, "tenant_id": tenant_id},
        {"$addToSet": {"conversation_ids": session_id}, "$inc": {"total_messages": 1}},
    )
```

**Callers** — thread `visitor_id`:
- `handle_message()` — pass `turn.visitor_id` to `_track_visitor_message`
- `handle_message_stream()` — same
- All `_handle_no_chunks` / `_handle_answer_with_chunks` calls — same

**Visitor profile classification lookups** — change from `turn.session_id` to `turn.visitor_id`:
- Lines ~170, ~259: `{"visitor_id": turn.session_id, ...}` → `{"visitor_id": turn.visitor_id, ...}`

**Identity context lookups** (`_get_visitor_identity_context`) — uses `session_id` to find visitor. This should also use `visitor_id`:
- Line ~352, ~447: change `turn.session_id` to `turn.visitor_id` when looking up visitor identity

---

### 6. `backend/controllers/chat.py`

**`_upsert_visitor()`** — add `visitor_id` parameter, use it as primary key:

```python
async def _upsert_visitor(
    session_id: str,
    tenant_id: str,
    current_url: str,
    current_page_title: str,
    client_ip: str,
    visitor_id: str = "",   # NEW
) -> None:
    try:
        now = datetime.now(timezone.utc)
        key = visitor_id or session_id  # fallback for backward compat
        visitor = await db.visitors.find_one(
            {"visitor_id": key, "tenant_id": tenant_id},
            {"ip_history": {"$slice": -1}, "page_views": {"$slice": -1}},
        )

        needs_ip = ...
        needs_page = ...

        update: dict[str, object] = {"$set": {"last_seen_at": now, "tenant_id": tenant_id}}
        push: dict[str, object] = {}
        if not visitor:
            update["$setOnInsert"] = {
                "visitor_id": key,
                "session_id": session_id,
                "first_seen_at": now,
                "conversation_ids": [session_id],   # start with first session
                "total_messages": 0,
            }
        else:
            update["$addToSet"] = {"conversation_ids": session_id}  # track this session

        if needs_ip:
            push["ip_history"] = ...
        if needs_page:
            push["page_views"] = ...
        if push:
            if "$push" not in update:
                update["$push"] = {}
            update["$push"].update(push)

        await db.visitors.update_one({"visitor_id": key, "tenant_id": tenant_id}, update, upsert=True)
    except Exception as e:
        print(f"[UPSERT] visitor error for visitor={key} session={session_id}: {e}")
```

Key changes:
- Lookup key is `visitor_id` (with `session_id` fallback)
- On update (existing visitor): `$addToSet` the new `session_id` into `conversation_ids`
- On insert: `conversation_ids` starts as `[session_id]`

**HTTP endpoint** — extract `visitor_id`:

```python
session_id = request.cookies.get("chat_session_id") or req.session_id or str(uuid.uuid4())
visitor_id = req.visitor_id or session_id   # NEW

await _upsert_visitor(
    session_id=session_id,
    visitor_id=visitor_id,   # NEW
    tenant_id=tenant_id,
    ...
)

result = await chat_service.handle_message(
    ChatTurnInput(
        tenant=current_tenant,
        session_id=session_id,
        visitor_id=visitor_id,   # NEW
        query=req.query,
        ...
    )
)
```

**WS endpoint** — extract `visitor_id` from message:

```python
visitor_id = data.get("visitor_id") or data.get("session_id") or ""
session_id = data.get("session_id") or str(uuid.uuid4())

await _upsert_visitor(
    session_id=session_id,
    visitor_id=visitor_id or session_id,
    ...
)

result = await chat_service.handle_message_stream(
    ChatTurnInput(
        tenant=tenant,
        session_id=session_id,
        visitor_id=visitor_id or session_id,
        ...
    ),
    ...
)
```

---

## Dashboard Impact

No dashboard changes needed. The existing `GET /api/dashboard/visitors/{visitor_id}` returns the full visitor document, which now includes `conversation_ids: ["session_1", "session_2", ...]`. The dashboard will naturally show all sessions linked to that visitor.

---

## Files Changed Summary

| File | Change |
|---|---|
| `apps/widget/src/utils/constants.ts` | Add `getVisitorId()`, `resetSessionId()`, `generateId()`; rewrite `getSessionId()` to use `sessionStorage` |
| `apps/widget/src/Widget.tsx` | Add `handleNewSession()`, send `visitor_id` in WS/lead/feedback payloads, pass `onNewSession` to Header |
| `apps/widget/src/components/Header.tsx` | Add `onNewSession` prop + "New Chat" button (plus icon) |
| `backend/models/requests.py` | Add `visitor_id: Optional[str]` to `ChatRequest` |
| `backend/controllers/chat.py` | `_upsert_visitor()`: accept `visitor_id`, use it as key; HTTP/WS handlers: parse and pass `visitor_id` |
| `backend/services/chat_service.py` | Add `visitor_id` to `ChatTurnInput`; update `_track_visitor_message()`; update all visitor document lookups |

---

## Backward Compatibility

- Old clients without `visitor_id` → backend falls back to using `session_id` as visitor key (existing behavior)
- Old visitor documents (`visitor_id = session_id`) remain accessible
- The change is additive: new fields are `Optional`, fallback logic exists everywhere
- Schema validation is `moderate` — extra fields are tolerated
