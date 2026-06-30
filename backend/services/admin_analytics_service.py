"""Admin analytics service — MongoDB aggregation pipelines for platform-wide usage analytics."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone, timedelta
from typing import Any

from core.auth import db
from core.redis import redis_client, get_redis_key
from services.llm.pricing import calculate_cost

CACHE_TTL = 30  # seconds


def _parse_period(period: str) -> datetime:
    """Parse a period string like '7d', '30d', '90d', '1y' and return the start datetime."""
    period = period.strip().lower()
    now = datetime.now(timezone.utc)

    if period.endswith("d"):
        days = int(period[:-1])
        return now - timedelta(days=days)
    if period.endswith("y"):
        years = int(period[:-1])
        return now - timedelta(days=years * 365)
    if period == "custom":
        return now - timedelta(days=30)

    return now - timedelta(days=30)


def _model_usage_pipeline(tenant_id: str | None = None) -> list[dict[str, Any]]:
    """Build a MongoDB aggregation pipeline for per-model token usage."""
    match_stage: dict[str, Any] = {"messages.role": "assistant", "messages.usage.model": {"$ne": None}}
    if tenant_id:
        match_stage["tenant_id"] = tenant_id

    return [
        {"$unwind": "$messages"},
        {"$match": match_stage},
        {
            "$group": {
                "_id": {
                    "provider": {"$ifNull": ["$messages.usage.provider", "unknown"]},
                    "model": {"$ifNull": ["$messages.usage.model", "unknown"]},
                },
                "prompt_tokens": {"$sum": {"$ifNull": ["$messages.usage.prompt_tokens", 0]}},
                "completion_tokens": {"$sum": {"$ifNull": ["$messages.usage.completion_tokens", 0]}},
                "total_tokens": {"$sum": {"$ifNull": ["$messages.usage.total_tokens", 0]}},
                "call_count": {"$sum": 1},
                "total_latency_ms": {"$sum": {"$ifNull": ["$messages.usage.latency_ms", 0]}},
                "success_count": {"$sum": {"$cond": [{"$eq": [{"$ifNull": ["$messages.usage.status", "success"]}, "success"]}, 1, 0]}},
                "error_count": {"$sum": {"$cond": [{"$eq": [{"$ifNull": ["$messages.usage.status", "success"]}, "error"]}, 1, 0]}},
            }
        },
        {"$sort": {"total_tokens": -1}},
    ]


def _build_model_usage(res: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Transform aggregation results into a clean model usage list with cost."""
    items = []
    for doc in res:
        provider = doc["_id"]["provider"]
        model = doc["_id"]["model"]
        prompt_t = doc.get("prompt_tokens", 0)
        comp_t = doc.get("completion_tokens", 0)
        call_count = doc.get("call_count", 0)
        total_latency = doc.get("total_latency_ms", 0)
        items.append({
            "provider": provider,
            "model": model,
            "prompt_tokens": prompt_t,
            "completion_tokens": comp_t,
            "total_tokens": doc.get("total_tokens", 0),
            "call_count": call_count,
            "avg_latency_ms": round(total_latency / call_count, 1) if call_count > 0 else 0.0,
            "success_count": doc.get("success_count", 0),
            "error_count": doc.get("error_count", 0),
            "cost": calculate_cost(provider, model, prompt_t, comp_t),
        })
    return items


async def get_platform_overview() -> dict[str, Any]:
    """Return platform-wide KPIs. Cached for 30s in Redis."""
    cache_key = get_redis_key("analytics:overview")
    try:
        cached = await redis_client.get(cache_key)
        if cached:
            return json.loads(cached)
    except Exception:
        pass

    total_tenants_pipeline = [
        {"$count": "count"},
    ]

    active_tenants_pipeline = [
        {"$match": {"updated_at": {"$gte": datetime.now(timezone.utc) - timedelta(days=30)}}},
        {"$group": {"_id": "$tenant_id"}},
        {"$count": "count"},
    ]

    conversations_pipeline = [
        {"$count": "count"},
    ]

    messages_pipeline = [
        {"$unwind": "$messages"},
        {"$match": {"messages.role": "assistant"}},
        {
            "$group": {
                "_id": None,
                "total_messages": {"$sum": 1},
                "total_prompt_tokens": {"$sum": {"$ifNull": ["$messages.usage.prompt_tokens", 0]}},
                "total_completion_tokens": {"$sum": {"$ifNull": ["$messages.usage.completion_tokens", 0]}},
                "total_tokens": {"$sum": {"$ifNull": ["$messages.usage.total_tokens", 0]}},
                "total_latency_ms": {"$sum": {"$ifNull": ["$messages.usage.latency_ms", 0]}},
                "success_count": {"$sum": {"$cond": [{"$eq": [{"$ifNull": ["$messages.usage.status", "success"]}, "success"]}, 1, 0]}},
                "error_count": {"$sum": {"$cond": [{"$eq": [{"$ifNull": ["$messages.usage.status", "success"]}, "error"]}, 1, 0]}},
            }
        },
    ]

    leads_pipeline = [
        {"$count": "count"},
    ]

    feedback_pipeline = [
        {
            "$group": {
                "_id": "$rating",
                "count": {"$sum": 1},
            }
        },
    ]

    model_usage_pipeline = _model_usage_pipeline()

    (
        total_tenants_res,
        active_tenants_res,
        conversations_res,
        messages_res,
        leads_res,
        feedback_res,
        model_usage_res,
    ) = await asyncio.gather(
        db.tenants.aggregate(total_tenants_pipeline).to_list(1),
        db.conversations.aggregate(active_tenants_pipeline).to_list(1),
        db.conversations.aggregate(conversations_pipeline).to_list(1),
        db.conversations.aggregate(messages_pipeline).to_list(1),
        db.leads.aggregate(leads_pipeline).to_list(1),
        db.message_feedback.aggregate(feedback_pipeline).to_list(1),
        db.conversations.aggregate(model_usage_pipeline).to_list(50),
    )

    total_tenants = total_tenants_res[0]["count"] if total_tenants_res else 0
    active_tenants = active_tenants_res[0]["count"] if active_tenants_res else 0
    total_conversations = conversations_res[0]["count"] if conversations_res else 0

    msg_data = messages_res[0] if messages_res else {}
    total_messages = msg_data.get("total_messages", 0)
    total_prompt_tokens = msg_data.get("total_prompt_tokens", 0)
    total_completion_tokens = msg_data.get("total_completion_tokens", 0)
    total_tokens = msg_data.get("total_tokens", 0)
    total_latency_ms = msg_data.get("total_latency_ms", 0)
    success_count = msg_data.get("success_count", 0)
    error_count = msg_data.get("error_count", 0)

    total_leads = leads_res[0]["count"] if leads_res else 0

    likes = 0
    dislikes = 0
    for fb in feedback_res:
        if fb["_id"] == "like":
            likes = fb["count"]
        elif fb["_id"] == "dislike":
            dislikes = fb["count"]
    total_feedback = likes + dislikes
    like_ratio = round((likes / total_feedback * 100), 1) if total_feedback > 0 else 0.0

    model_usage = _build_model_usage(model_usage_res)
    estimated_cost = sum(m["cost"] for m in model_usage)

    lead_conversion = round((total_leads / total_conversations * 100), 1) if total_conversations > 0 else 0.0

    result = {
        "total_tenants": total_tenants,
        "active_tenants": active_tenants,
        "total_conversations": total_conversations,
        "total_messages": total_messages,
        "total_tokens": total_tokens,
        "prompt_tokens": total_prompt_tokens,
        "completion_tokens": total_completion_tokens,
        "estimated_cost": estimated_cost,
        "model_usage": model_usage,
        "avg_latency_ms": round(total_latency_ms / total_messages, 1) if total_messages > 0 else 0.0,
        "success_count": success_count,
        "error_count": error_count,
        "error_rate": round((error_count / total_messages * 100), 2) if total_messages > 0 else 0.0,
        "total_leads": total_leads,
        "lead_conversion": lead_conversion,
        "like_count": likes,
        "dislike_count": dislikes,
        "like_ratio": like_ratio,
    }

    try:
        await redis_client.setex(cache_key, CACHE_TTL, json.dumps(result, default=str))
    except Exception:
        pass

    return result


async def get_timeseries(period: str = "30d") -> list[dict[str, Any]]:
    """Return daily time-series data for messages, conversations, tokens, cost, and leads. Cached for 30s."""
    cache_key = get_redis_key(f"analytics:timeseries:{period}")
    try:
        cached = await redis_client.get(cache_key)
        if cached:
            return json.loads(cached)
    except Exception:
        pass

    start_date = _parse_period(period)
    field_name = "created_at"
    field_ref = "$created_at"

    messages_pipeline = [
        {"$match": {field_name: {"$gte": start_date}}},
        {"$unwind": "$messages"},
        {"$match": {"messages.role": "assistant"}},
        {
            "$group": {
                "_id": {
                    "date": {"$dateToString": {"format": "%Y-%m-%d", "date": field_ref}},
                    "provider": {"$ifNull": ["$messages.usage.provider", "unknown"]},
                    "model": {"$ifNull": ["$messages.usage.model", "unknown"]},
                },
                "messages": {"$sum": 1},
                "tokens": {"$sum": {"$ifNull": ["$messages.usage.total_tokens", 0]}},
                "prompt_tokens": {"$sum": {"$ifNull": ["$messages.usage.prompt_tokens", 0]}},
                "completion_tokens": {"$sum": {"$ifNull": ["$messages.usage.completion_tokens", 0]}},
            }
        },
        {
            "$group": {
                "_id": "$_id.date",
                "messages": {"$sum": "$messages"},
                "tokens": {"$sum": "$tokens"},
                "prompt_tokens": {"$sum": "$prompt_tokens"},
                "completion_tokens": {"$sum": "$completion_tokens"},
                "model_details": {
                    "$push": {
                        "provider": "$_id.provider",
                        "model": "$_id.model",
                        "prompt_tokens": "$prompt_tokens",
                        "completion_tokens": "$completion_tokens",
                    }
                },
            }
        },
        {"$sort": {"_id": 1}},
    ]

    conversations_pipeline = [
        {"$match": {field_name: {"$gte": start_date}}},
        {
            "$group": {
                "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": field_ref}},
                "conversations": {"$sum": 1},
            }
        },
        {"$sort": {"_id": 1}},
    ]

    leads_pipeline = [
        {"$match": {"created_at": {"$gte": start_date}}},
        {
            "$group": {
                "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}},
                "leads": {"$sum": 1},
            }
        },
        {"$sort": {"_id": 1}},
    ]

    messages_res, conversations_res, leads_res = await asyncio.gather(
        db.conversations.aggregate(messages_pipeline).to_list(366),
        db.conversations.aggregate(conversations_pipeline).to_list(366),
        db.leads.aggregate(leads_pipeline).to_list(366),
    )

    # Merge into daily buckets
    days_map: dict[str, dict[str, Any]] = {}

    for doc in messages_res:
        day = doc["_id"]
        # Calculate actual cost from per-model breakdown
        day_cost = sum(
            calculate_cost(m["provider"], m["model"], m["prompt_tokens"], m["completion_tokens"])
            for m in doc.get("model_details", [])
        )
        days_map[day] = {
            "date": day,
            "messages": doc.get("messages", 0),
            "conversations": 0,
            "tokens": doc.get("tokens", 0),
            "prompt_tokens": doc.get("prompt_tokens", 0),
            "completion_tokens": doc.get("completion_tokens", 0),
            "cost": day_cost,
            "leads": 0,
        }

    for doc in conversations_res:
        day = doc["_id"]
        if day not in days_map:
            days_map[day] = {"date": day, "messages": 0, "conversations": 0, "tokens": 0, "prompt_tokens": 0, "completion_tokens": 0, "cost": 0.0, "leads": 0}
        days_map[day]["conversations"] = doc.get("conversations", 0)

    for doc in leads_res:
        day = doc["_id"]
        if day not in days_map:
            days_map[day] = {"date": day, "messages": 0, "conversations": 0, "tokens": 0, "prompt_tokens": 0, "completion_tokens": 0, "cost": 0.0, "leads": 0}
        days_map[day]["leads"] = doc.get("leads", 0)

    result = sorted(days_map.values(), key=lambda x: x["date"])

    try:
        await redis_client.setex(cache_key, CACHE_TTL, json.dumps(result, default=str))
    except Exception:
        pass

    return result


async def get_tenants_usage(
    page: int = 1,
    limit: int = 10,
    search: str | None = None,
    sort: str = "messages",
    order: str = "desc",
    period: str = "30d",
) -> dict[str, Any]:
    """Return per-tenant usage stats with pagination and sorting."""
    start_date = _parse_period(period)
    sort_field = sort if sort in ("messages", "tokens", "cost", "leads", "last_activity") else "messages"
    sort_order = -1 if order == "desc" else 1

    # Build tenant filter
    tenant_match: dict[str, Any] = {}
    if search:
        search_regex = {"$regex": search, "$options": "i"}
        tenant_match["$or"] = [
            {"domain": search_regex},
            {"business_name": search_regex},
            {"tenant_id": search_regex},
        ]

    pipeline = [
        {"$match": {"created_at": {"$gte": start_date}}},
        {
            "$group": {
                "_id": "$tenant_id",
                "conversations": {"$sum": 1},
                "messages": {"$sum": {"$size": "$messages"}},
                "prompt_tokens": {"$sum": {"$sum": {"$map": {"input": "$messages", "as": "m", "in": {"$ifNull": ["$$m.usage.prompt_tokens", 0]}}}}},
                "completion_tokens": {"$sum": {"$sum": {"$map": {"input": "$messages", "as": "m", "in": {"$ifNull": ["$$m.usage.completion_tokens", 0]}}}}},
                "total_tokens": {"$sum": {"$sum": {"$map": {"input": "$messages", "as": "m", "in": {"$ifNull": ["$$m.usage.total_tokens", 0]}}}}},
                "last_activity": {"$max": "$updated_at"},
            }
        },
    ]

    # Add lookup for tenant info
    pipeline.extend([
        {
            "$lookup": {
                "from": "tenants",
                "localField": "_id",
                "foreignField": "tenant_id",
                "as": "tenant_info",
            }
        },
        {"$unwind": {"path": "$tenant_info", "preserveNullAndEmptyArrays": True}},
        {
            "$project": {
                "tenant_id": "$_id",
                "domain": {"$ifNull": ["$tenant_info.domain", "unknown"]},
                "business_name": {"$ifNull": ["$tenant_info.business_name", ""]},
                "plan": {"$ifNull": ["$tenant_info.plan", "free"]},
                "created_at": {"$ifNull": ["$tenant_info.created_at", None]},
                "conversations": 1,
                "messages": 1,
                "prompt_tokens": 1,
                "completion_tokens": 1,
                "total_tokens": 1,
                "last_activity": 1,
            }
        },
    ])

    if tenant_match:
        pipeline.append({"$match": tenant_match})

    # Count total before pagination
    count_pipeline = pipeline + [{"$count": "total"}]

    # Add sort and pagination
    pipeline.extend([
        {"$sort": {sort_field: sort_order}},
        {"$skip": (page - 1) * limit},
        {"$limit": limit},
    ])

    # Get leads per tenant
    leads_pipeline = [
        {"$match": {"created_at": {"$gte": start_date}}},
        {"$group": {"_id": "$tenant_id", "leads": {"$sum": 1}}},
    ]

    # Get feedback per tenant
    feedback_pipeline = [
        {
            "$group": {
                "_id": {"tenant_id": "$tenant_id", "rating": "$rating"},
                "count": {"$sum": 1},
            }
        },
    ]

    # Get model usage per tenant
    model_pipeline = [
        {"$match": {"created_at": {"$gte": start_date}}},
        {"$unwind": "$messages"},
        {"$match": {"messages.role": "assistant", "messages.usage.model": {"$ne": None}}},
        {
            "$group": {
                "_id": {
                    "tenant_id": "$tenant_id",
                    "provider": {"$ifNull": ["$messages.usage.provider", "unknown"]},
                    "model": {"$ifNull": ["$messages.usage.model", "unknown"]},
                },
                "prompt_tokens": {"$sum": {"$ifNull": ["$messages.usage.prompt_tokens", 0]}},
                "completion_tokens": {"$sum": {"$ifNull": ["$messages.usage.completion_tokens", 0]}},
                "total_tokens": {"$sum": {"$ifNull": ["$messages.usage.total_tokens", 0]}},
                "call_count": {"$sum": 1},
                "total_latency_ms": {"$sum": {"$ifNull": ["$messages.usage.latency_ms", 0]}},
                "success_count": {"$sum": {"$cond": [{"$eq": [{"$ifNull": ["$messages.usage.status", "success"]}, "success"]}, 1, 0]}},
                "error_count": {"$sum": {"$cond": [{"$eq": [{"$ifNull": ["$messages.usage.status", "success"]}, "error"]}, 1, 0]}},
            }
        },
    ]

    (
        main_res,
        count_res,
        leads_res,
        feedback_res,
        model_res,
    ) = await asyncio.gather(
        db.conversations.aggregate(pipeline).to_list(limit),
        db.conversations.aggregate(count_pipeline).to_list(1),
        db.leads.aggregate(leads_pipeline).to_list(1000),
        db.message_feedback.aggregate(feedback_pipeline).to_list(2000),
        db.conversations.aggregate(model_pipeline).to_list(2000),
    )

    total = count_res[0]["total"] if count_res else 0

    # Build lookup maps
    leads_map: dict[str, int] = {doc["_id"]: doc["leads"] for doc in leads_res}
    feedback_map: dict[str, dict[str, int]] = {}
    for doc in feedback_res:
        tid = doc["_id"]["tenant_id"]
        rating = doc["_id"]["rating"]
        if tid not in feedback_map:
            feedback_map[tid] = {"likes": 0, "dislikes": 0}
        if rating == "like":
            feedback_map[tid]["likes"] = doc["count"]
        elif rating == "dislike":
            feedback_map[tid]["dislikes"] = doc["count"]

    # Build per-tenant model usage map
    tenant_model_map: dict[str, list[dict[str, Any]]] = {}
    for doc in model_res:
        tid = doc["_id"]["tenant_id"]
        if tid not in tenant_model_map:
            tenant_model_map[tid] = []
        provider = doc["_id"]["provider"]
        model = doc["_id"]["model"]
        prompt_t = doc.get("prompt_tokens", 0)
        comp_t = doc.get("completion_tokens", 0)
        call_count = doc.get("call_count", 0)
        total_latency = doc.get("total_latency_ms", 0)
        tenant_model_map[tid].append({
            "provider": provider,
            "model": model,
            "prompt_tokens": prompt_t,
            "completion_tokens": comp_t,
            "total_tokens": doc.get("total_tokens", 0),
            "call_count": call_count,
            "avg_latency_ms": round(total_latency / call_count, 1) if call_count > 0 else 0.0,
            "success_count": doc.get("success_count", 0),
            "error_count": doc.get("error_count", 0),
            "cost": calculate_cost(provider, model, prompt_t, comp_t),
        })

    items = []
    for doc in main_res:
        tid = doc["tenant_id"]
        fb = feedback_map.get(tid, {"likes": 0, "dislikes": 0})
        total_fb = fb["likes"] + fb["dislikes"]
        leads_count = leads_map.get(tid, 0)
        models = tenant_model_map.get(tid, [])

        items.append({
            "tenant_id": tid,
            "domain": doc.get("domain", ""),
            "business_name": doc.get("business_name", ""),
            "plan": doc.get("plan", "free"),
            "created_at": doc.get("created_at"),
            "conversations": doc.get("conversations", 0),
            "visitors": 0,
            "messages": doc.get("messages", 0),
            "prompt_tokens": doc.get("prompt_tokens", 0),
            "completion_tokens": doc.get("completion_tokens", 0),
            "total_tokens": doc.get("total_tokens", 0),
            "estimated_cost": sum(m["cost"] for m in models),
            "model_usage": models,
            "leads": leads_count,
            "likes": fb["likes"],
            "dislikes": fb["dislikes"],
            "like_ratio": round((fb["likes"] / total_fb * 100), 1) if total_fb > 0 else 0.0,
            "last_activity": doc.get("last_activity"),
        })

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": limit,
        "total_pages": (total + limit - 1) // limit if limit > 0 else 0,
    }


async def get_tenant_analytics(tenant_id: str, period: str = "30d") -> dict[str, Any] | None:
    """Return detailed analytics for a single tenant."""
    start_date = _parse_period(period)

    # Check tenant exists
    tenant = await db.tenants.find_one(
        {"tenant_id": tenant_id},
        {"password_hash": 0, "api_key": 0, "api_key_hash": 0},
    )
    if not tenant:
        return None

    # Aggregate conversation stats for this tenant
    conv_pipeline = [
        {"$match": {"tenant_id": tenant_id, "created_at": {"$gte": start_date}}},
        {
            "$group": {
                "_id": None,
                "conversations": {"$sum": 1},
                "messages": {"$sum": {"$size": "$messages"}},
                "prompt_tokens": {"$sum": {"$sum": {"$map": {"input": "$messages", "as": "m", "in": {"$ifNull": ["$$m.usage.prompt_tokens", 0]}}}}},
                "completion_tokens": {"$sum": {"$sum": {"$map": {"input": "$messages", "as": "m", "in": {"$ifNull": ["$$m.usage.completion_tokens", 0]}}}}},
                "total_tokens": {"$sum": {"$sum": {"$map": {"input": "$messages", "as": "m", "in": {"$ifNull": ["$$m.usage.total_tokens", 0]}}}}},
                "total_latency_ms": {"$sum": {"$sum": {"$map": {"input": "$messages", "as": "m", "in": {"$ifNull": ["$$m.usage.latency_ms", 0]}}}}},
                "assistant_count": {"$sum": {"$size": {"$filter": {"input": "$messages", "as": "m", "cond": {"$eq": ["$$m.role", "assistant"]}}}}},
                "last_activity": {"$max": "$updated_at"},
            }
        },
    ]

    leads_pipeline = [
        {"$match": {"tenant_id": tenant_id, "created_at": {"$gte": start_date}}},
        {"$count": "count"},
    ]

    feedback_pipeline = [
        {"$match": {"tenant_id": tenant_id}},
        {"$group": {"_id": "$rating", "count": {"$sum": 1}}},
    ]

    visitors_pipeline = [
        {"$match": {"tenant_id": tenant_id, "first_seen_at": {"$gte": start_date}}},
        {"$count": "count"},
    ]

    model_usage_pipeline = _model_usage_pipeline(tenant_id)

    (
        conv_res,
        leads_res,
        feedback_res,
        visitors_res,
        model_usage_res,
    ) = await asyncio.gather(
        db.conversations.aggregate(conv_pipeline).to_list(1),
        db.leads.aggregate(leads_pipeline).to_list(1),
        db.message_feedback.aggregate(feedback_pipeline).to_list(10),
        db.visitors.aggregate(visitors_pipeline).to_list(1),
        db.conversations.aggregate(model_usage_pipeline).to_list(50),
    )

    conv_data = conv_res[0] if conv_res else {}
    total_conversations = conv_data.get("conversations", 0)
    total_messages = conv_data.get("messages", 0)
    prompt_tokens = conv_data.get("prompt_tokens", 0)
    completion_tokens = conv_data.get("completion_tokens", 0)
    total_tokens = conv_data.get("total_tokens", 0)
    total_latency_ms = conv_data.get("total_latency_ms", 0)
    assistant_count = conv_data.get("assistant_count", 0)
    last_activity = conv_data.get("last_activity")

    total_leads = leads_res[0]["count"] if leads_res else 0
    total_visitors = visitors_res[0]["count"] if visitors_res else 0

    likes = 0
    dislikes = 0
    for fb in feedback_res:
        if fb["_id"] == "like":
            likes = fb["count"]
        elif fb["_id"] == "dislike":
            dislikes = fb["count"]
    total_feedback = likes + dislikes
    like_ratio = round((likes / total_feedback * 100), 1) if total_feedback > 0 else 0.0

    model_usage = _build_model_usage(model_usage_res)
    estimated_cost = sum(m["cost"] for m in model_usage)
    lead_conversion = round((total_leads / total_conversations * 100), 1) if total_conversations > 0 else 0.0

    # Time-series for this tenant
    ts_messages_pipeline = [
        {"$match": {"tenant_id": tenant_id, "created_at": {"$gte": start_date}}},
        {"$unwind": "$messages"},
        {"$match": {"messages.role": "assistant"}},
        {
            "$group": {
                "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}},
                "messages": {"$sum": 1},
                "tokens": {"$sum": {"$ifNull": ["$messages.usage.total_tokens", 0]}},
            }
        },
        {"$sort": {"_id": 1}},
    ]

    ts_leads_pipeline = [
        {"$match": {"tenant_id": tenant_id, "created_at": {"$gte": start_date}}},
        {
            "$group": {
                "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}},
                "leads": {"$sum": 1},
            }
        },
        {"$sort": {"_id": 1}},
    ]

    ts_msg_res, ts_leads_res = await asyncio.gather(
        db.conversations.aggregate(ts_messages_pipeline).to_list(366),
        db.leads.aggregate(ts_leads_pipeline).to_list(366),
    )

    # Merge time-series
    ts_map: dict[str, dict[str, Any]] = {}
    for doc in ts_msg_res:
        day = doc["_id"]
        ts_map[day] = {"date": day, "messages": doc.get("messages", 0), "tokens": doc.get("tokens", 0), "leads": 0}
    for doc in ts_leads_res:
        day = doc["_id"]
        if day not in ts_map:
            ts_map[day] = {"date": day, "messages": 0, "tokens": 0, "leads": 0}
        ts_map[day]["leads"] = doc.get("leads", 0)

    timeseries = sorted(ts_map.values(), key=lambda x: x["date"])

    return {
        "tenant": {
            "tenant_id": tenant_id,
            "domain": tenant.get("domain", ""),
            "plan": tenant.get("plan", "free"),
            "business_name": tenant.get("business_name", ""),
            "created_at": tenant.get("created_at"),
        },
        "kpi": {
            "conversations": total_conversations,
            "visitors": total_visitors,
            "messages": total_messages,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "estimated_cost": estimated_cost,
            "model_usage": model_usage,
            "avg_latency_ms": round(total_latency_ms / assistant_count, 1) if assistant_count > 0 else 0.0,
            "leads": total_leads,
            "lead_conversion": lead_conversion,
            "likes": likes,
            "dislikes": dislikes,
            "like_ratio": like_ratio,
            "last_activity": last_activity,
        },
        "timeseries": timeseries,
    }


async def get_top_tenants(sort_by: str = "messages", limit: int = 10) -> list[dict[str, Any]]:
    """Return top tenants sorted by the given metric."""
    sort_field = sort_by if sort_by in ("messages", "tokens", "cost") else "messages"

    pipeline = [
        {
            "$group": {
                "_id": "$tenant_id",
                "messages": {"$sum": {"$size": "$messages"}},
                "prompt_tokens": {"$sum": {"$sum": {"$map": {"input": "$messages", "as": "m", "in": {"$ifNull": ["$$m.usage.prompt_tokens", 0]}}}}},
                "completion_tokens": {"$sum": {"$sum": {"$map": {"input": "$messages", "as": "m", "in": {"$ifNull": ["$$m.usage.completion_tokens", 0]}}}}},
                "total_tokens": {"$sum": {"$sum": {"$map": {"input": "$messages", "as": "m", "in": {"$ifNull": ["$$m.usage.total_tokens", 0]}}}}},
                "llm_calls": {"$sum": {"$sum": {"$map": {"input": "$messages", "as": "m", "in": {"$cond": [{"$and": [{"$eq": ["$$m.role", "assistant"]}, {"$ne": ["$$m.usage", None]}]}, 1, 0]}}}}},
                "conversations": {"$sum": 1},
                "last_activity": {"$max": "$updated_at"},
            }
        },
        {
            "$lookup": {
                "from": "tenants",
                "localField": "_id",
                "foreignField": "tenant_id",
                "as": "tenant_info",
            }
        },
        {"$unwind": {"path": "$tenant_info", "preserveNullAndEmptyArrays": True}},
    ]

    # Leads per tenant
    leads_pipeline = [
        {"$group": {"_id": "$tenant_id", "leads": {"$sum": 1}}},
    ]

    # Model usage per tenant (for accurate cost calculation)
    model_pipeline = [
        {"$unwind": "$messages"},
        {"$match": {"messages.role": "assistant", "messages.usage.model": {"$ne": None}}},
        {
            "$group": {
                "_id": {
                    "tenant_id": "$tenant_id",
                    "provider": {"$ifNull": ["$messages.usage.provider", "unknown"]},
                    "model": {"$ifNull": ["$messages.usage.model", "unknown"]},
                },
                "prompt_tokens": {"$sum": {"$ifNull": ["$messages.usage.prompt_tokens", 0]}},
                "completion_tokens": {"$sum": {"$ifNull": ["$messages.usage.completion_tokens", 0]}},
            }
        },
    ]

    main_res, leads_res, model_res = await asyncio.gather(
        db.conversations.aggregate(pipeline).to_list(1000),
        db.leads.aggregate(leads_pipeline).to_list(1000),
        db.conversations.aggregate(model_pipeline).to_list(2000),
    )

    leads_map = {doc["_id"]: doc["leads"] for doc in leads_res}

    # Build per-tenant cost map from actual model breakdown
    tenant_cost_map: dict[str, float] = {}
    for doc in model_res:
        tid = doc["_id"]["tenant_id"]
        provider = doc["_id"]["provider"]
        model = doc["_id"]["model"]
        prompt_t = doc.get("prompt_tokens", 0)
        comp_t = doc.get("completion_tokens", 0)
        tenant_cost_map[tid] = tenant_cost_map.get(tid, 0.0) + calculate_cost(provider, model, prompt_t, comp_t)

    items = []
    for doc in main_res:
        tid = doc["_id"]
        items.append({
            "tenant_id": tid,
            "domain": doc.get("tenant_info", {}).get("domain", "unknown"),
            "plan": doc.get("tenant_info", {}).get("plan", "free"),
            "conversations": doc.get("conversations", 0),
            "messages": doc.get("messages", 0),
            "prompt_tokens": doc.get("prompt_tokens", 0),
            "completion_tokens": doc.get("completion_tokens", 0),
            "total_tokens": doc.get("total_tokens", 0),
            "estimated_cost": tenant_cost_map.get(tid, 0.0),
            "llm_calls": doc.get("llm_calls", 0),
            "leads": leads_map.get(tid, 0),
            "last_activity": doc.get("last_activity"),
        })

    # Sort by the requested field
    sort_key = "estimated_cost" if sort_field == "cost" else sort_field
    items.sort(key=lambda x: x.get(sort_key, 0), reverse=True)

    return items[:limit]


async def get_model_leaderboard(period: str = "30d") -> list[dict[str, Any]]:
    """Return per-model usage stats ranked by total tokens."""
    start_date = _parse_period(period)

    pipeline = [
        {"$match": {"created_at": {"$gte": start_date}}},
        {"$unwind": "$messages"},
        {"$match": {"messages.role": "assistant", "messages.usage.model": {"$ne": None}}},
        {
            "$group": {
                "_id": {
                    "provider": {"$ifNull": ["$messages.usage.provider", "unknown"]},
                    "model": {"$ifNull": ["$messages.usage.model", "unknown"]},
                },
                "prompt_tokens": {"$sum": {"$ifNull": ["$messages.usage.prompt_tokens", 0]}},
                "completion_tokens": {"$sum": {"$ifNull": ["$messages.usage.completion_tokens", 0]}},
                "total_tokens": {"$sum": {"$ifNull": ["$messages.usage.total_tokens", 0]}},
                "call_count": {"$sum": 1},
                "total_latency_ms": {"$sum": {"$ifNull": ["$messages.usage.latency_ms", 0]}},
                "success_count": {"$sum": {"$cond": [{"$eq": [{"$ifNull": ["$messages.usage.status", "success"]}, "success"]}, 1, 0]}},
                "error_count": {"$sum": {"$cond": [{"$eq": [{"$ifNull": ["$messages.usage.status", "success"]}, "error"]}, 1, 0]}},
            }
        },
        {"$sort": {"total_tokens": -1}},
    ]

    res = await db.conversations.aggregate(pipeline).to_list(100)

    items = []
    for doc in res:
        provider = doc["_id"]["provider"]
        model = doc["_id"]["model"]
        prompt_t = doc.get("prompt_tokens", 0)
        comp_t = doc.get("completion_tokens", 0)
        call_count = doc.get("call_count", 0)
        total_latency = doc.get("total_latency_ms", 0)
        items.append({
            "provider": provider,
            "model": model,
            "prompt_tokens": prompt_t,
            "completion_tokens": comp_t,
            "total_tokens": doc.get("total_tokens", 0),
            "call_count": call_count,
            "avg_latency_ms": round(total_latency / call_count, 1) if call_count > 0 else 0.0,
            "success_count": doc.get("success_count", 0),
            "error_count": doc.get("error_count", 0),
            "cost": calculate_cost(provider, model, prompt_t, comp_t),
        })

    return items
