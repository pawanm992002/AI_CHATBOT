from core.auth import db
from services.llm.factory import get_llm


async def generate_suggested_questions(tenant_id: str):
    """Generate auto-suggested questions based on tenant's indexed content."""
    try:
        # Fetch top 10 chunks
        chunks = await db.chunks.find(
            {"tenant_id": tenant_id},
            {"text": 1, "title": 1, "section_title": 1, "_id": 0}
        ).sort("indexed_at", -1).limit(10).to_list(length=10)

        # Fetch all FAQs
        faqs = await db.faqs.find(
            {"tenant_id": tenant_id},
            {"question": 1, "answer": 1, "_id": 0}
        ).to_list(length=50)

        if not chunks and not faqs:
            return

        # Build context for LLM
        context_parts = []
        for c in chunks:
            label = c.get("section_title") or c.get("title") or "Content"
            context_parts.append(f"[{label}]: {c['text'][:500]}")
        for f in faqs:
            context_parts.append(f"[FAQ] Q: {f['question']}\nA: {f['answer'][:300]}")

        context = "\n".join(context_parts[:15])

        tenant = await db.tenants.find_one(
            {"tenant_id": tenant_id},
            {"domain": 1, "ai": 1, "_id": 0},
        )
        domain = tenant.get("domain", "the website") if tenant else "the website"
        ai_cfg = (tenant or {}).get("ai") or {}
        provider = (ai_cfg.get("provider") or "openai").strip()
        model = (ai_cfg.get("model") or "gpt-4o-mini").strip()

        llm = get_llm(provider, model)
        resp = await llm.ainvoke(
            [
                {
                    "role": "system",
                    "content": (
                        f"You generate suggested questions for a website chatbot on {domain}. "
                        "Based on the website content below, generate exactly 6 short questions "
                        "that a visitor might ask. Mix different topics. "
                        "Reply ONLY with a JSON array of strings, no explanation. "
                        "Example: [\"What services do you offer?\", \"How much does it cost?\"]"
                    ),
                },
                {"role": "user", "content": context},
            ]
        )

        import json
        raw = (resp.content or "").strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        questions = json.loads(raw)
        if isinstance(questions, list) and all(isinstance(q, str) for q in questions):
            await db.tenants.update_one(
                {"tenant_id": tenant_id},
                {"$set": {"suggested_questions_auto": questions[:6]}}
            )
    except Exception:
        pass  # Must never break the main flow
