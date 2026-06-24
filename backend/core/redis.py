import redis.asyncio as redis
from core.config import settings

# Initialize async Redis connection pool
redis_client = redis.from_url(settings.REDIS_URI, decode_responses=True)
