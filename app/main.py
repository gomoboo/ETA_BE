import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.exception_handlers import register_exception_handlers
from app.core.redis import init_redis_pool, close_redis_pool
from app.api.v1.router import api_router

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    # from_url()은 실제로 연결하지 않으므로 ping으로 연결 가능 여부를 확인 (실패해도 서버는 기동, 이후 요청 시 재연결)
    try:
        redis = await init_redis_pool()
        await redis.ping()
    except Exception as e:
        logger.warning("Redis connection failed on startup: %s", e)
    yield
    # Shutdown
    await close_redis_pool()

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    debug=settings.DEBUG,
    lifespan=lifespan,
)

# CORS 설정 (프론트엔드 연동)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 글로벌 예외 핸들러 등록
register_exception_handlers(app)

# v1 라우터 등록
app.include_router(api_router, prefix=settings.API_V1_STR)

@app.get("/health")
async def health_check():
    return {"status": "ok", "app": settings.PROJECT_NAME}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
