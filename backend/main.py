from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse, RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware
from controllers import tenants, crawl, chat, sources, faqs, text_docs, leads, admin, knowledge_improvement, providers, admin_analytics, visitor_profiles, conversations
from core.auth import db
from fastapi.staticfiles import StaticFiles
import os

app = FastAPI(title="Chatbot Widget SaaS")

class CORSRreflectMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        origin = request.headers.get("origin")

        if request.method == "OPTIONS":
            response = Response(status_code=200)
            requested_headers = request.headers.get("access-control-request-headers", "")
            if requested_headers:
                response.headers["Access-Control-Allow-Headers"] = requested_headers
            response.headers["Access-Control-Allow-Methods"] = request.headers.get("access-control-request-method", "POST")
        else:
            try:
                response = await call_next(request)
            except Exception as exc:
                import traceback
                traceback.print_exc()
                response = Response(status_code=500, content="Internal Server Error")

        if origin:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Vary"] = "Origin"

        return response

app.add_middleware(CORSRreflectMiddleware)

app.include_router(tenants.router, prefix="/api")
app.include_router(tenants.test_router)
app.include_router(crawl.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(sources.router, prefix="/api")
app.include_router(faqs.router, prefix="/api")
app.include_router(text_docs.router, prefix="/api")
app.include_router(leads.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(admin_analytics.router, prefix="/api")
app.include_router(knowledge_improvement.router, prefix="/api")
app.include_router(providers.router, prefix="/api")
app.include_router(visitor_profiles.router, prefix="/api")
app.include_router(conversations.router, prefix="/api")

backend_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.abspath(os.path.join(backend_dir, ".."))

widget_dist = os.path.join(root_dir, "apps/widget/dist")
dashboard_dist = os.path.join(root_dir, "apps/dashboard/dist")
uploads_dir = os.path.join(backend_dir, "uploads")

os.makedirs(widget_dist, exist_ok=True)
os.makedirs(uploads_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=widget_dist), name="static")

os.makedirs(dashboard_dist, exist_ok=True)
dashboard_assets = os.path.join(dashboard_dist, "assets")
if os.path.isdir(dashboard_assets):
    app.mount("/dashboard/assets", StaticFiles(directory=dashboard_assets), name="dashboard_assets")


@app.get("/dashboard/{full_path:path}")
async def dashboard_spa(full_path: str):
    return FileResponse(os.path.join(dashboard_dist, "index.html"))


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.get("/")
async def root():
    return RedirectResponse(url="/dashboard/")

@app.on_event("startup")
async def backfill_tenant_statuses():
    try:
        result = await db.tenants.update_many(
            {"status": {"$exists": False}},
            {"$set": {"status": "approved"}}
        )
        if result.modified_count:
            print(f"Backfilled status for {result.modified_count} existing tenant(s)")
    except Exception as e:
        print(f"Startup: backfill_tenant_statuses failed: {e}")


@app.on_event("startup")
async def apply_db_schemas():
    try:
        from core.schema_validator import ensure_schemas
        await ensure_schemas()
    except Exception as e:
        print(f"Startup: apply_db_schemas failed: {e}")

@app.on_event("startup")
async def cleanup_stale_jobs():
    try:
        from datetime import datetime, timezone
        from repositories.crawl_job_repository import CrawlJobRepository
        repo = CrawlJobRepository()
        modified = await repo.mark_stale_running_as_failed()
        if modified:
            print(f"Cleaned up {modified} stale crawl job(s)")
    except Exception as e:
        print(f"Startup: cleanup_stale_jobs failed: {e}")

@app.on_event("startup")
async def backfill_api_key_hashes():
    try:
        from core.auth import hash_api_key
        cursor = db.tenants.find({"api_key_hash": {"$exists": False}}, {"tenant_id": 1, "api_key": 1})
        count = 0
        async for tenant in cursor:
            await db.tenants.update_one(
                {"_id": tenant["_id"]},
                {"$set": {"api_key_hash": hash_api_key(tenant["api_key"])}}
            )
            count += 1
        if count:
            print(f"Backfilled api_key_hash for {count} existing tenant(s)")
    except Exception as e:
        print(f"Startup: backfill_api_key_hashes failed: {e}")


@app.on_event("startup")
async def ensure_lookup_indexes():
    try:
        await db.parents.create_index([("tenant_id", 1), ("parent_id", 1)])
        await db.parents.create_index([("tenant_id", 1), ("source_id", 1)])
        await db.chunks.create_index([("tenant_id", 1), ("parent_id", 1), ("child_index", 1)])
        await db.chunks.create_index([("tenant_id", 1), ("source_id", 1)])
        await db.pages.create_index([("tenant_id", 1), ("url", 1)])
        await db.pages.create_index([("tenant_id", 1), ("source_id", 1)])
        await db.visitors.create_index("last_seen_at")
        await db.visitors.create_index([("tenant_id", 1), ("visitor_id", 1)])
        await db.tenants.create_index("tenant_id", unique=True)
        await db.tenants.create_index("api_key", unique=True)
        await db.tenants.create_index("domain")
        await db.conversations.create_index([("session_id", 1), ("tenant_id", 1)])
        await db.conversations.create_index([("tenant_id", 1), ("created_at", -1)])
        await db.conversations.create_index([("tenant_id", 1), ("updated_at", -1)])
        await db.crawl_jobs.create_index([("job_id", 1), ("tenant_id", 1)])
        await db.sources.create_index([("tenant_id", 1), ("source_id", 1)])
        await db.faqs.create_index([("tenant_id", 1), ("source_id", 1), ("faq_id", 1)])
        await db.documents.create_index([("tenant_id", 1), ("source_id", 1), ("doc_id", 1)])
        await db.leads.create_index([("tenant_id", 1), ("created_at", -1)])
        await db.knowledge_gaps.create_index([("tenant_id", 1), ("status", 1)])
        await db.knowledge_gaps.create_index([("tenant_id", 1), ("cluster_id", 1)])
        await db.source_jobs.create_index([("tenant_id", 1), ("source_id", 1), ("started_at", -1)])
        await db.source_jobs.create_index([("tenant_id", 1), ("job_type", 1)])
        await db.lead_form_configs.create_index([("tenant_id", 1), ("form_id", 1)])
        await db.lead_form_configs.create_index([("tenant_id", 1), ("enabled", 1)])
    except Exception as e:
        print(f"Startup: ensure_lookup_indexes failed: {e}")


@app.on_event("startup")
async def start_visitor_classification_sweep():
    """
    Periodic background sweep that auto-classifies visitors after session inactivity.
    
    Every 5 minutes, finds visitors whose last_seen_at is older than the inactivity
    threshold (5 min) and who haven't been classified since their last activity.
    Runs classify_visitor as fire-and-forget to avoid blocking.
    
    Tradeoff: periodic sweep adds up to INACTIVITY_TIMEOUT + SWEEP_INTERVAL delay
    before classification fires. This is simpler than hooking WebSocket disconnect
    and works for HTTP-only sessions too.
    """
    import asyncio
    from datetime import datetime, timezone, timedelta
    from core.auth import db
    from services.visitor_profile_service import VisitorProfileService

    INACTIVITY_TIMEOUT_MINUTES = 5
    SWEEP_INTERVAL_SECONDS = 300  # 5 minutes

    svc = VisitorProfileService()

    async def _sweep():
        while True:
            try:
                await asyncio.sleep(SWEEP_INTERVAL_SECONDS)
                threshold = datetime.now(timezone.utc) - timedelta(minutes=INACTIVITY_TIMEOUT_MINUTES)
                cursor = db.visitors.find({
                    "last_seen_at": {"$lt": threshold},
                    "$or": [
                        {"last_classified_at": None},
                        {"$expr": {"$lt": ["$last_classified_at", "$last_seen_at"]}},
                    ],
                }, {"visitor_id": 1, "tenant_id": 1})
                count = 0
                async for v in cursor:
                    asyncio.ensure_future(
                        svc.classify_visitor(v["visitor_id"], v["tenant_id"], trigger="auto")
                    )
                    count += 1
                if count:
                    print(f"[CLASSIFICATION_SWEEP] Triggered auto-classification for {count} visitor(s)")
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[CLASSIFICATION_SWEEP] Error: {e}")

    asyncio.ensure_future(_sweep())


@app.on_event("shutdown")
def shutdown_db_client():
    from core.auth import client
    client.close()