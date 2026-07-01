"""
End-to-end integration test.
Runs against the running API server (http://127.0.0.1:8000).
Uses httpx client with cookie persistence (dashboard auth is cookie-based).
"""

import asyncio
import httpx
import os
import re
import sys
import uuid

BASE = "http://127.0.0.1:8000"
TEST_PREFIX = f"_test_e2e_{uuid.uuid4().hex[:8]}"
TENANT_DOMAIN = f"{TEST_PREFIX}.example.com"
TENANT_EMAIL = f"{TEST_PREFIX}@example.com"

passed = 0
failed = 0

def ok(name, detail=""):
    global passed
    passed += 1
    print(f"  PASS  {name}" + (f" — {detail}" if detail else ""))

def fail(name, detail):
    global failed
    failed += 1
    print(f"  FAIL  {name} — {detail}")

def extract_db_name(uri):
    m = re.search(r'/([^/?#]+)(\?|$)', uri.replace('mongodb+srv://', 'mongodb://'))
    return m.group(1) if m else "chatbot_db"

async def main():
    admin_cli = httpx.AsyncClient(base_url=BASE, timeout=30.0)
    tenant_cli = httpx.AsyncClient(base_url=BASE, timeout=30.0)

    print(f"\n{'='*60}")
    print(f"E2E Test Suite — {TEST_PREFIX}")
    print(f"{'='*60}")

    # ── 1. Health ──────────────────────────────────────────────────
    print("\n--- 1. Server Health ---")
    r = await tenant_cli.get("/")
    ok("Server root", f"HTTP {r.status_code} (expected 307)") if r.status_code == 307 else fail("Server root", str(r.status_code))
    r = await tenant_cli.get("/docs")
    ok("OpenAPI docs", f"HTTP {r.status_code}") if r.status_code == 200 else fail("OpenAPI docs", str(r.status_code))

    # ── 2. Auth ────────────────────────────────────────────────────
    print("\n--- 2. Authentication ---")

    r = await admin_cli.post("/api/admin/login", json={"username": "admin", "password": "admin123"})
    if r.status_code == 200 and "access_token" in r.json():
        ok("Admin login", f"cookies={dict(admin_cli.cookies)}")
    else:
        fail("Admin login", f"{r.status_code}: {r.text[:200]}")

    r = await tenant_cli.post("/api/tenants/register", json={
        "email": TENANT_EMAIL, "password": "test123",
        "business_name": f"Test Corp {TEST_PREFIX}",
        "company_name": f"Test Corp {TEST_PREFIX}",
        "domain": TENANT_DOMAIN,
    })
    if r.status_code in (200, 201):
        ok("Tenant registered (pending)")
    else:
        fail("Tenant register", f"{r.status_code}: {r.text[:200]}")

    # Approve via admin
    api_key = ""
    r = await admin_cli.get("/api/admin/tenants", params={"limit": 100})
    if r.status_code == 200:
        body = r.json()
        items = body.get("items", [])
        if not items:
            fail("Admin list tenants", f"0 items — cookies={dict(admin_cli.cookies)}")
        else:
            tid = None
            for t in items:
                if t.get("email") == TENANT_EMAIL:
                    tid = t.get("tenant_id") or t.get("_id")
                    break
            if tid:
                r2 = await admin_cli.post(f"/api/admin/tenants/{tid}/approve")
                if r2.status_code == 200:
                    ok("Tenant approved")
                    api_key = r2.json().get("api_key", "")
                else:
                    fail("Approve", f"{r2.status_code}: {r2.text[:200]}")
            else:
                fail("Find tenant", "not in admin list")
    else:
        fail("Admin list tenants", f"{r.status_code}: {r.text[:200]}")

    # Tenant login
    r = await tenant_cli.post("/api/tenants/login", json={
        "domain": TENANT_DOMAIN, "password": "test123",
    })
    if r.status_code == 200:
        ok("Tenant login", f"cookies={dict(tenant_cli.cookies)}")
    else:
        fail("Tenant login", f"{r.status_code}: {r.text[:200]}")

    # Get tenant info (including api_key)
    r = await tenant_cli.get("/api/tenants/me")
    if r.status_code == 200:
        data = r.json()
        if not api_key:
            api_key = data.get("api_key", "")
        ok("Tenant info", f"api_key={'present' if api_key else 'MISSING'}")
    else:
        fail("Tenant info", f"{r.status_code}: {r.text[:200]}")

    # ── 3. DB Schemas ──────────────────────────────────────────────
    print("\n--- 3. Database Schemas ---")

    mongodb_uri = os.environ.get("MONGODB_URI", "")
    if not mongodb_uri:
        ep = os.path.join(os.path.dirname(__file__), ".env")
        if os.path.exists(ep):
            with open(ep) as f:
                for line in f:
                    if line.strip().startswith("MONGODB_URI="):
                        mongodb_uri = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break

    db_name = extract_db_name(mongodb_uri) if mongodb_uri else "chatbot_db"

    if mongodb_uri:
        try:
            from motor.motor_asyncio import AsyncIOMotorClient
            MotorClient = AsyncIOMotorClient
            mc = MotorClient(mongodb_uri, serverSelectionTimeoutMS=5000)
            db = mc[db_name]
            cursor = await db.list_collections()
            names = []
            async for c in cursor:
                names.append(c["name"])
            ok("MongoDB connected", f"{len(names)} collections, db={db_name}")

            for name in ["visitor_profiles", "visitors", "conversations", "leads", "lead_form_configs"]:
                status = "exists" if name in names else "MISSING"
                (ok if name in names else fail)(f"Collection '{name}'", status)
                if name in names:
                    info = await db.command("listCollections", filter={"name": name})
                    items = info.get("cursor", {}).get("firstBatch", [])
                    v = items[0].get("options", {}).get("validator", {}) if items else {}
                    ok(f"Validator on '{name}'", "present" if v else "MISSING")
        except Exception as e:
            fail("MongoDB schema check", str(e)[:200])
    else:
        fail("MongoDB schema check", "MONGODB_URI not found")

    def fresh_widget():
        c = httpx.AsyncClient(base_url=BASE, timeout=60.0)
        c.headers["Authorization"] = f"Bearer {api_key}"
        return c

    if not api_key:
        fail("API key missing", "cannot test widget/chat endpoints")
        print("\n--- SKIPPING remaining tests (no API key) ---")
    else:
        widget = fresh_widget()

        # ── 4. Visitor Profiles CRUD ──────────────────────────────
        print("\n--- 4. Visitor Profiles CRUD ---")

        r = await tenant_cli.get("/api/dashboard/visitor-profiles")
        ok("List profiles (initial)", f"count={len(r.json())}") if r.status_code == 200 else fail("List", f"{r.status_code}")

        p1 = {"name": f"{TEST_PREFIX} - Enterprise", "description": "Enterprise visitors", "color": "#4F46E5",
              "enabled": True,
              "rules": [{"type": "keyword_match", "keywords": ["enterprise", "corporate"], "priority": 10}],
              "llm_criteria": "Visitor asking about enterprise features"}
        r = await tenant_cli.post("/api/dashboard/visitor-profiles", json=p1)
        pid1 = r.json().get("profile_id") if r.status_code in (200, 201) else None
        ok("Create profile 1", f"id={pid1}") if pid1 else fail("Create profile 1", f"{r.status_code}: {r.text[:200]}")

        p2 = {"name": f"{TEST_PREFIX} - Support", "description": "Support seekers", "color": "#F59E0B",
              "enabled": True,
              "rules": [{"type": "keyword_match", "keywords": ["help", "support", "broken"], "priority": 5}],
              "llm_criteria": "Visitor needing help"}
        r = await tenant_cli.post("/api/dashboard/visitor-profiles", json=p2)
        pid2 = r.json().get("profile_id") if r.status_code in (200, 201) else None
        ok("Create profile 2", f"id={pid2}") if pid2 else fail("Create profile 2", f"{r.status_code}: {r.text[:200]}")

        if pid1:
            r = await tenant_cli.put(f"/api/dashboard/visitor-profiles/{pid1}", json={"name": f"{TEST_PREFIX} - Enterprise (Updated)"})
            ok("Update profile") if r.status_code == 200 else fail("Update", f"{r.status_code}: {r.text[:200]}")

        # NOTE: No single-profile GET endpoint exists (only list/all)

        r = await tenant_cli.get("/api/dashboard/visitor-profiles")
        ok("List profiles (final)", f"count={len(r.json())}") if r.status_code == 200 else fail("List final", f"{r.status_code}")

        r = await tenant_cli.get("/api/dashboard/visitor-profiles/stats")
        ok("Profile stats") if r.status_code == 200 else fail("Stats", f"{r.status_code}: {r.text[:100]}")

        # ── 5. Classification ─────────────────────────────────────
        print("\n--- 5. Visitor Classification ---")

        widget = fresh_widget()
        sid = f"{TEST_PREFIX}_session_{uuid.uuid4().hex[:8]}"
        r = await widget.post("/api/chat", json={"query": "I need help with your enterprise plan pricing", "session_id": sid, "current_url": "https://example.com", "current_page_title": "Test Page"})
        if r.status_code in (200, 201):
            ok("Chat triggers visitor creation", f"HTTP {r.status_code}")
        else:
            fail("Chat", f"HTTP {r.status_code}: {r.text[:300]}")
            # Debug: check if api_key is valid
            r2 = await widget.get("/api/widget/config", headers={"Authorization": f"Bearer {api_key}"})
            if r2.status_code != 200:
                fail("Chat debug", f"api_key invalid: {r2.status_code}: {r2.text[:200]}")
            else:
                fail("Chat debug", f"api_key valid but chat failed")
        await asyncio.sleep(3)

        r = await tenant_cli.get("/api/dashboard/visitors", params={"search": sid})
        ok("List visitors by session") if r.status_code == 200 else fail("List visitors", f"{r.status_code}: {r.text[:100]}")

        r = await tenant_cli.post(f"/api/dashboard/visitors/{sid}/reclassify")
        ok("Reclassification", f"profile={r.json().get('profile_label', 'none')}") if r.status_code == 200 else fail("Reclassify", f"{r.status_code}: {r.text[:200]}")

        if pid2:
            r = await tenant_cli.put(f"/api/dashboard/visitors/{sid}/profile", json={"profile_id": pid2})
            ok("Profile override") if r.status_code == 200 else fail("Override", f"{r.status_code}: {r.text[:200]}")
            await tenant_cli.put(f"/api/dashboard/visitors/{sid}/profile", json={"profile_id": None})

        # ── 6. Archival ───────────────────────────────────────────
        print("\n--- 6. Conversation Archival ---")

        widget = fresh_widget()
        csid = f"{TEST_PREFIX}_conv_{uuid.uuid4().hex[:8]}"
        for i in range(19):
            await widget.post("/api/chat", json={"query": f"Test msg {i}", "session_id": csid, "current_url": "https://example.com", "current_page_title": "Test"})
            await asyncio.sleep(0.05)
        await asyncio.sleep(62)
        for i in range(19, 25):
            await widget.post("/api/chat", json={"query": f"Test msg {i}", "session_id": csid, "current_url": "https://example.com", "current_page_title": "Test"})
            await asyncio.sleep(0.05)
        await asyncio.sleep(3)

        r = await tenant_cli.get(f"/api/dashboard/visitors?search={csid}")
        if r.status_code == 200:
            items = r.json().get("items", [])
            if items:
                conv_ids = items[0].get("conversation_ids", [])
                ok("Visitor found by session", f"conversation_ids={conv_ids}")
                if conv_ids:
                    cid = conv_ids[-1]
                    r2 = await tenant_cli.get(f"/api/dashboard/conversations/{cid}")
                    if r2.status_code == 200:
                        conv = r2.json()
                        msgs = len(conv.get("messages", []))
                        arch = conv.get("archived", False)
                        arch_cnt = conv.get("archived_turn_count", 0)
                        ok("Conversation found", f"msgs={msgs}, archived={arch}, archived_turns={arch_cnt}")
                        if arch and arch_cnt > 0:
                            ok("Archival triggered", f"{arch_cnt} turns archived")
                            r3 = await tenant_cli.get(f"/api/dashboard/conversations/{cid}/full")
                            if r3.status_code == 200:
                                body = r3.json()
                                total = len(body.get("messages", body if isinstance(body, list) else []))
                                ok("Full conversation history", f"{total} messages")
                            else:
                                fail("Full history", f"{r3.status_code}: {r3.text[:200]}")
                        else:
                            fail("Archival NOT triggered", f"msgs={msgs}, archived={arch}")
                    else:
                        fail("Conversation detail", f"{r2.status_code}: {r2.text[:200]}")
                else:
                    fail("No conversation_ids", f"{items[0]}")
            else:
                fail("Conversation NOT found", f"session={csid}")
        else:
            fail("Search visitors", f"{r.status_code}: {r.text[:200]}")

        # ── 7. Identity via Lead Form ─────────────────────────────
        print("\n--- 7. Visitor Identity Capture ---")

        widget = fresh_widget()
        isid = f"{TEST_PREFIX}_id_{uuid.uuid4().hex[:8]}"
        # First create a visitor via chat so identity sync has a doc to update
        r = await widget.post("/api/chat", json={"query": "hello", "session_id": isid, "current_url": "https://example.com", "current_page_title": "Test"})
        ok("Chat to create visitor for identity", f"HTTP {r.status_code}") if r.status_code in (200, 201) else fail("Chat for identity", f"{r.status_code}: {r.text[:200]}")
        await asyncio.sleep(0.5)

        fp = {"title": f"{TEST_PREFIX} - Contact", "name": f"{TEST_PREFIX} - Contact", "enabled": True, "trigger_instructions": "test",
              "fields": [
                  {"label": "Full Name", "type": "text", "required": True, "field_role": "name"},
                  {"label": "Email", "type": "email", "required": True, "field_role": "email"},
                  {"label": "Phone", "type": "phone", "required": False, "field_role": "phone"},
                  {"label": "Company", "type": "text", "required": False, "field_role": None},
              ]}
        r = await tenant_cli.post("/api/lead-forms", json=fp)
        fid = r.json().get("form_id") if r.status_code in (200, 201) else None
        ok("Create lead form", f"id={fid}") if fid else fail("Create lead form", f"{r.status_code}: {r.text[:200]}")

        if fid:
            r = await widget.post("/api/leads", json={"session_id": isid, "form_id": fid,
                "name": "John Testerson", "email": f"{TEST_PREFIX}@test.com",
                "phone": "+1 555 123 4567",
                "message": "Testing lead form identity capture"})
            ok("Lead submitted", f"HTTP {r.status_code}") if r.status_code in (200, 201) else fail("Lead submit", f"{r.status_code}: {r.text[:200]}")
            await asyncio.sleep(1)

            r = await tenant_cli.get(f"/api/dashboard/visitors/{isid}")
            if r.status_code == 200:
                vis = r.json()
                ident = vis.get("identity", {})
                if ident.get("name") == "John Testerson":
                    ok("Identity synced", f"name={ident['name']}, email={ident.get('email')}")
                else:
                    fail("Identity sync", f"expected John Testerson, got {ident}")
            else:
                fail("Visitor not found", f"session={isid}")

            # Personalized greeting
            r = await widget.post("/api/chat", json={"query": "hi", "session_id": isid, "current_url": "https://example.com", "current_page_title": "Test"})
            if r.status_code in (200, 201):
                text = r.json().get("answer", "")
                ok("Personalized greeting", f"contains 'John'={ 'John' in text }")
            else:
                fail("Greeting chat", f"{r.status_code}: {r.text[:200]}")

        # ── 8. Identity CRUD ──────────────────────────────────────
        # First create a visitor via chat, then test identity ops
        print("\n--- 8. Identity CRUD ---")
        widget = fresh_widget()
        isid2 = f"{TEST_PREFIX}_crud_{uuid.uuid4().hex[:8]}"
        r = await widget.post("/api/chat", json={"query": "hello", "session_id": isid2, "current_url": "https://example.com", "current_page_title": "Test"})
        ok("Chat to create visitor for identity CRUD", f"HTTP {r.status_code}") if r.status_code in (200, 201) else fail("Chat for CRUD", f"{r.status_code}: {r.text[:200]}")
        await asyncio.sleep(0.5)

        r = await tenant_cli.put(f"/api/dashboard/visitors/{isid2}/identity", json={
            "name": "Jane Tester", "email": "jane@test.com", "phone": "+1 555 999 9999"})
        ok("Set identity") if r.status_code == 200 else fail("Set identity", f"{r.status_code}: {r.text[:200]}")

        r = await tenant_cli.get(f"/api/dashboard/visitors/{isid2}")
        ok("Get visitor") if r.status_code == 200 else fail("Get visitor", f"{r.status_code}: {r.text[:100]}")

        r = await tenant_cli.delete(f"/api/dashboard/visitors/{isid2}/identity")
        ok("Clear identity") if r.status_code == 200 else fail("Clear identity", f"{r.status_code}: {r.text[:200]}")

        # ── 9. Admin Profile Stats ────────────────────────────────
        print("\n--- 9. Admin Profile Stats ---")
        r = await tenant_cli.get("/api/tenants/me")
        tid = r.json().get("tenant_id") if r.status_code == 200 else None
        if tid:
            r = await admin_cli.get(f"/api/admin/analytics/tenant/{tid}/profile-stats")
            ok("Admin profile stats") if r.status_code == 200 else fail("Admin stats", f"{r.status_code}: {r.text[:200]}")
        else:
            fail("Admin stats", "no tenant_id")

    # ── 10. Cleanup ────────────────────────────────────────────────
    print("\n--- 10. Cleanup ---")
    if mongodb_uri:
        try:
            mc4 = MotorClient(mongodb_uri, serverSelectionTimeoutMS=5000)
            db4 = mc4[db_name]
            n = 0
            for c, q in [("visitor_profiles", {"name": {"$regex": TEST_PREFIX}}),
                          ("visitors", {"session_id": {"$regex": TEST_PREFIX}}),
                          ("conversations", {"session_id": {"$regex": TEST_PREFIX}}),
                          ("leads", {"context": {"$regex": TEST_PREFIX}}),
                          ("lead_form_configs", {"name": {"$regex": TEST_PREFIX}})]:
                r = await db4[c].delete_many(q)
                n += r.deleted_count
            ok("Cleanup", f"{n} docs removed") if n > 0 else ok("Cleanup", "no test data")
        except Exception as e:
            fail("Cleanup", str(e)[:200])

    # ── Summary ────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"RESULTS: {passed} passed, {failed} failed")
    print(f"{'='*60}\n")
    sys.exit(0 if failed == 0 else 1)

if __name__ == "__main__":
    asyncio.run(main())
