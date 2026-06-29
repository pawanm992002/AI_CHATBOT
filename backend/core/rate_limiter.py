import time
import uuid
from fastapi import Request, HTTPException, status
from core.redis import redis_client, get_redis_key

def get_client_ip(request: Request) -> str:
    """Safely retrieve the client IP from the request headers or client connection info."""
    if request.client:
        return request.client.host
    return request.headers.get("x-forwarded-for", "0.0.0.0").split(",")[0].strip()

async def check_rate_limit(key: str, limit: int, window: int) -> bool:
    """
    Returns True if the rate limit is exceeded, False otherwise.
    Uses Redis sorted set (ZSET) for a sliding window rate limiter.
    """
    key = get_redis_key(key)
    now = time.time()
    cutoff = now - window
    # We append a unique identifier (UUID) to handle multiple requests at the exact same millisecond/microsecond
    member = f"{now}:{uuid.uuid4().hex}"
    
    try:
        async with redis_client.pipeline(transaction=True) as pipe:
            pipe.zremrangebyscore(key, 0, cutoff)
            pipe.zadd(key, {member: now})
            pipe.zcard(key)
            pipe.expire(key, window)
            results = await pipe.execute()
            count = results[2]
            return count > limit
    except Exception as e:
        # Fallback in case Redis is temporarily down/unreachable
        print(f"Redis rate limiter exception for key {key}: {e}")
        return False

class RateLimiter:
    """
    A FastAPI dependency to enforce rate limiting by IP.
    """
    def __init__(self, limit: int, window: int, key_prefix: str):
        self.limit = limit
        self.window = window
        self.key_prefix = key_prefix

    async def __call__(self, request: Request):
        ip = get_client_ip(request)
        key = f"rate_limit:{self.key_prefix}:{ip}"
        if await check_rate_limit(key, self.limit, self.window):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Please slow down."
            )
