from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    PROJECT_NAME: str = "이따 (ETA) Backend"
    API_V1_STR: str = "/api/v1"
    DEBUG: bool = True

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./eta.db"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # External APIs
    KAKAO_REST_API_KEY: Optional[str] = None
    FCM_SERVER_KEY: Optional[str] = None

    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()
