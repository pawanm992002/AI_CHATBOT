"""Quick test for archival threshold + visitor_id."""
import asyncio, httpx, uuid

BASE = "http://127.0.0.1:8000"
UID = uuid.uuid4().hex[:8]

async def main():
    c = httpx.AsyncClient(base_url=BASE, timeout=30.0)

    r = await c.post("/api/admin/login", json={"username": "admin", "password": "admin123"})
    print(f"admin login: {r.status_code}")

    r = await c.post("/api/tenants/register", json={
        "business_name": f"arch_{UID}", "domain": f"{UID}.local",
        "email": f"arch_{UID}@t.com", "password": "test123"
    })
    print(f"register: {r.status_code}")
    if r.status_code != 200:
        print(f"  {r.text[:200]}")
        await c.aclose()
        return

    r = await c.get("/api/admin/tenants?limit=100")
    tenants = r.json().get("items", r.json()) if isinstance(r.json(), dict) else r.json()
    tid = None
    for t in tenants:
        if t.get("domain") == f"{UID}.local":
            tid = t["tenant_id"]
            break
    if not tid:
        print("FAIL: tenant not found")
        await c.aclose()
        return

    r = await c.post(f"/api/admin/tenants/{tid}/approve")
    print(f"approve: {r.status_code}")
    await c.aclose()

    # Tenant login
    t = httpx.AsyncClient(base_url=BASE, timeout=30.0)
    r = await t.post("/api/tenants/login", json={"domain": f"{UID}.local", "password": "test123"})
    print(f"login: {r.status_code}")
    r = await t.get("/api/tenants/me")
    api_key = r.json()["api_key"]

    # Batch 1: 19 messages — 1s between to avoid lost updates from concurrent $set
    sid = f"arch_test_{UID}"
    sent = 0
    for i in range(19):
        r = await t.post("/api/chat", json={
            "query": f"Test msg {i}", "session_id": sid,
            "current_url": "https://example.com", "current_page_title": "T"
        }, headers={"Authorization": f"Bearer {api_key}"})
        if r.status_code == 200:
            sent += 1
        else:
            print(f"  msg {i}: {r.status_code}")
        await asyncio.sleep(1.0)
    print(f"batch 1: {sent}/19")

    print("waiting 62s for rate limit...")
    await asyncio.sleep(62)

    # Batch 2: 6 messages
    for i in range(19, 25):
        r = await t.post("/api/chat", json={
            "query": f"Test msg {i}", "session_id": sid,
            "current_url": "https://example.com", "current_page_title": "T"
        }, headers={"Authorization": f"Bearer {api_key}"})
        if r.status_code == 200:
            sent += 1
        else:
            print(f"  msg {i}: {r.status_code}")
        await asyncio.sleep(1.0)
    print(f"total: {sent}/25")
    await asyncio.sleep(3)

    # Check visitor
    r = await t.get(f"/api/dashboard/visitors?search={sid}")
    items = r.json().get("items", [])
    if not items:
        print("FAIL: no visitor found")
        await t.aclose()
        return

    cids = items[0].get("conversation_ids", [])
    vid = items[0].get("visitor_id", "MISSING")
    print(f"visitor_id: {vid}")
    print(f"conversation_ids: {cids}")

    if not cids:
        print("FAIL: no conversations")
        await t.aclose()
        return

    r2 = await t.get(f"/api/dashboard/conversations/{cids[-1]}")
    conv = r2.json()
    msgs = len(conv.get("messages", []))
    arch = conv.get("archived", False)
    arch_cnt = conv.get("archived_turn_count", 0)
    print(f"msgs={msgs}, archived={arch}, archived_turns={arch_cnt}")

    if arch and arch_cnt > 0:
        print("PASS: Archival triggered")
        r3 = await t.get(f"/api/dashboard/conversations/{cids[-1]}/full")
        total = len(r3.json().get("messages", []))
        print(f"full history: {total} messages")
    else:
        print(f"FAIL: Archival NOT triggered (msgs={msgs})")
    await t.aclose()

asyncio.run(main())
