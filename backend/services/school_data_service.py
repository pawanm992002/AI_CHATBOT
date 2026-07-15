"""School ERP service entry point and School Mode session management."""

from core.redis import redis_client, get_redis_key

SCHOOL_MODE_TTL = 1800


class SchoolDataService:
    """Invoke the registry-backed School Agent for a tenant-scoped question."""

    async def query(
        self,
        tenant_id: str,
        session_id: str,
        question: str,
        llm_provider: str = "openai",
        llm_model: str = "gpt-4o-mini",
    ) -> str:
        from langchain_core.messages import HumanMessage
        from services.school_agent.graph import graph

        initial_state = {
            "messages": [HumanMessage(content=question)],
            "tenant_id": tenant_id,
            "school_session_id": session_id,
            "original_question": question,
        }
        config = {
            "configurable": {
                "thread_id": session_id,
                "tenant_id": tenant_id,
                "session_id": session_id,
                "question": question,
                "llm_provider": llm_provider,
                "llm_model": llm_model,
            }
        }
        result = await graph.ainvoke(initial_state, config=config)

        if result.get("__interrupt__"):
            interrupt_value = result["__interrupt__"][0].value
            return f"[APPROVAL_REQUIRED]: {interrupt_value.get('message', 'Write action approval requested.')}"

        messages = result.get("messages", [])
        return messages[-1].content if messages else "I couldn't find any information for that question."

    @staticmethod
    async def set_school_mode(session_id: str, tenant_id: str) -> None:
        await redis_client.setex(get_redis_key(f"school_mode:{session_id}"), SCHOOL_MODE_TTL, tenant_id)

    @staticmethod
    async def get_school_mode(session_id: str) -> str | None:
        value = await redis_client.get(get_redis_key(f"school_mode:{session_id}"))
        return value.decode() if isinstance(value, bytes) else value

    @staticmethod
    async def clear_school_mode(session_id: str) -> None:
        await redis_client.delete(get_redis_key(f"school_mode:{session_id}"))
