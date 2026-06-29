import redis.asyncio as redis
from core.config import settings

# Initialize async Redis connection pool
redis_client = redis.from_url(settings.REDIS_URI, decode_responses=True)

def get_redis_key(key: str) -> str:
    """Prepend the system-configured Redis namespace to the key if defined."""
    if settings.REDIS_NAMESPACE:
        return f"{settings.REDIS_NAMESPACE}:{key}"
    return key
