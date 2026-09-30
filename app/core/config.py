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

    # 초대 링크 (inviteUrl = INVITE_BASE_URL/{inviteCode})
    INVITE_BASE_URL: str = "https://eta.app/invite"

    # 결과 공유 링크 (정산/영장 공유 URL, 카드 이미지 URL의 기본 주소)
    SHARE_BASE_URL: str = "https://eta.app"

    # 정산: 약속 시간 이후 이 시간(분)이 지나면 미도착자가 있어도 정산 확정 (미도착자 지각 시간 = 이 값)
    SETTLEMENT_TIMEOUT_MINUTES: int = 60

    # External APIs
    KAKAO_REST_API_KEY: Optional[str] = None
    FCM_SERVER_KEY: Optional[str] = None

    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()
