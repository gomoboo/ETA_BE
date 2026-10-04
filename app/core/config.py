from pydantic_settings import BaseSettings, SettingsConfigDict
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

    # 실시간 레이더: 목적지 반경 이 거리(m) 안에 들어오면 자동 체크인 (WS-06 명세 30m)
    GEOFENCE_RADIUS_METERS: float = 30.0
    # 같은 대상에게 다시 찌르기까지 기다려야 하는 시간(초)
    POKE_COOLDOWN_SECONDS: int = 60

    # External APIs
    KAKAO_REST_API_KEY: Optional[str] = None
    FCM_SERVER_KEY: Optional[str] = None

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)

settings = Settings()
