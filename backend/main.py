from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse, RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware
from controllers import tenants, crawl, chat, sources, faqs, text_docs, leads, admin, knowledge_improvement
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from core.auth import db, limiter
from core.config import settings
from fastapi.staticfiles import StaticFiles
import os

app = FastAPI(title="Chatbot Widget SaaS")

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

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

app.include_router(tenants.router)
app.include_router(crawl.router)
app.include_router(chat.router)
app.include_router(sources.router)
app.include_router(faqs.router)
app.include_router(text_docs.router)
app.include_router(leads.router)
app.include_router(admin.router)
app.include_router(knowledge_improvement.router)

backend_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.abspath(os.path.join(backend_dir, ".."))

widget_dist = os.path.join(root_dir, "apps/widget/dist")
dashboard_dist = os.path.join(root_dir, "apps/dashboard/dist")
uploads_dir = os.path.join(backend_dir, "uploads")

os.makedirs(widget_dist, exist_ok=True)
os.makedirs(uploads_dir, exist_ok=True)

# In production, static files are served by Nginx instead of Python
if settings.APP_ENV != "production":
    app.mount("/static", StaticFiles(directory=widget_dist), name="static")

    os.makedirs(dashboard_dist, exist_ok=True)
    dashboard_assets = os.path.join(dashboard_dist, "assets")
    if os.path.isdir(dashboard_assets):
        app.mount("/dashboard/assets", StaticFiles(directory=dashboard_assets), name="dashboard_assets")


    @app.get("/dashboard/{full_path:path}")
    async def dashboard_spa(full_path: str):
        return FileResponse(os.path.join(dashboard_dist, "index.html"))


    @app.get("/")
    async def root():
        return RedirectResponse(url="/dashboard/")


@app.on_event("startup")
async def apply_db_schemas():
    from core.schema_validator import ensure_schemas
    await ensure_schemas()


@app.on_event("startup")
async def cleanup_stale_jobs():
    from datetime import datetime, timezone
    from repositories.crawl_job_repository import CrawlJobRepository
    repo = CrawlJobRepository()
    modified = await repo.mark_stale_running_as_failed()
    if modified:
        print(f"Cleaned up {modified} stale crawl job(s)")


@app.on_event("startup")
async def backfill_api_key_hashes():
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


@app.on_event("startup")
async def ensure_lookup_indexes():
    await db.parents.create_index([("tenant_id", 1), ("parent_id", 1)])
    await db.parents.create_index([("tenant_id", 1), ("source_id", 1)])
    await db.chunks.create_index([("tenant_id", 1), ("parent_id", 1), ("child_index", 1)])
    await db.chunks.create_index([("tenant_id", 1), ("source_id", 1)])
    await db.pages.create_index([("tenant_id", 1), ("url", 1)])
    await db.pages.create_index([("tenant_id", 1), ("source_id", 1)])
    await db.visitors.create_index("session_id")
    await db.tenants.create_index("tenant_id", unique=True)
    await db.tenants.create_index("api_key", unique=True)
    await db.tenants.create_index("domain")
    await db.conversations.create_index("session_id")
    await db.crawl_jobs.create_index([("job_id", 1), ("tenant_id", 1)])
    await db.sources.create_index([("tenant_id", 1), ("source_id", 1)])
    await db.faqs.create_index([("tenant_id", 1), ("source_id", 1), ("faq_id", 1)])
    await db.documents.create_index([("tenant_id", 1), ("source_id", 1), ("doc_id", 1)])
    await db.leads.create_index([("tenant_id", 1), ("created_at", -1)])
    await db.knowledge_gaps.create_index([("tenant_id", 1), ("status", 1)])
    await db.knowledge_gaps.create_index([("tenant_id", 1), ("cluster_id", 1)])
    await db.source_jobs.create_index([("tenant_id", 1), ("source_id", 1), ("started_at", -1)])
    await db.source_jobs.create_index([("tenant_id", 1), ("job_type", 1)])