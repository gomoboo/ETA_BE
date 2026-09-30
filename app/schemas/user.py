from typing import Optional

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class OnboardingRequest(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    guest_uuid: str = Field(..., min_length=1, max_length=64, description="클라이언트 기기 고유 UUID")
    # 닉네임 길이(2~10자)는 INVALID_NICKNAME_LENGTH로 응답하기 위해 서비스에서 검증
    nickname: str = Field(..., description="닉네임 (2~10자)")
    profile_character: Optional[str] = Field(None, max_length=50, description="프로필 캐릭터 ID")
    location_terms_agreed: bool = Field(True, description="위치 정보 수집/이용 약관 동의 여부")
    notification_allowed: bool = Field(True, description="푸시 알림 수신 동의 여부")
    fcm_token: Optional[str] = Field(None, max_length=255, description="FCM 디바이스 토큰")


class OnboardingResponse(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    user_id: int
    nickname: str
    location_terms_agreed: bool
