from typing import Optional
import redis.asyncio as aioredis
from redis.asyncio import Redis
from app.core.config import settings

redis_client: Optional[Redis] = None


async def init_redis_pool() -> Redis:
    """
    Redis 비동기 커넥션 풀을 초기화하고 클라이언트를 반환합니다.
    """
    global redis_client
    if redis_client is None:
        redis_client = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
    return redis_client


async def close_redis_pool() -> None:
    """
    애플리케이션 종료 시 Redis 커넥션 풀을 닫습니다.
    """
    global redis_client
    if redis_client is not None:
        await redis_client.close()
        redis_client = None


async def get_redis() -> Redis:
    """
    FastAPI 의존성 주입 또는 비동기 함수에서 Redis 클라이언트를 가져옵니다.
    """
    if redis_client is None:
        return await init_redis_pool()
    return redis_client
