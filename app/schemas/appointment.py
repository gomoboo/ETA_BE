from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel

from app.models.appointment import PenaltyType, RadarStartType

CUSTOM_RADAR_MAX_MINUTES = 24 * 60


def to_utc(value: datetime) -> datetime:
    """timezone 정보가 없으면 UTC로 간주하고, 있으면 UTC로 변환"""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class AppointmentCreateRequest(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    title: str = Field(..., min_length=1, max_length=100)
    target_place_name: str = Field(..., min_length=1, max_length=150)
    target_address: Optional[str] = Field(None, max_length=255)
    target_latitude: float = Field(..., ge=-90, le=90)
    target_longitude: float = Field(..., ge=-180, le=180)
    meet_at: datetime
    radar_start_type: RadarStartType = RadarStartType.M30_BEFORE
    custom_radar_minutes_before: Optional[int] = Field(None, ge=1, le=CUSTOM_RADAR_MAX_MINUTES)
    penalty_type: PenaltyType = PenaltyType.PENALTY
    penalty_content: Optional[str] = Field(None, max_length=150)
    fine_per_minute: int = Field(0, ge=0)

    @field_validator("title", "target_place_name")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("공백만 입력할 수 없습니다.")
        return value

    @field_validator("penalty_type", mode="before")
    @classmethod
    def normalize_penalty_type(cls, value):
        # API 명세는 지각비 모드를 "FEE"로, 모델은 "FINE"으로 정의하고 있어 둘 다 허용
        if value == "FEE":
            return PenaltyType.FINE
        return value

    @field_validator("meet_at")
    @classmethod
    def meet_at_in_future(cls, value: datetime) -> datetime:
        value = to_utc(value)
        if value <= datetime.now(timezone.utc):
            raise ValueError("약속 시간은 현재 이후여야 합니다.")
        return value

    @model_validator(mode="after")
    def check_mode_fields(self):
        if self.radar_start_type == RadarStartType.CUSTOM:
            if self.custom_radar_minutes_before is None:
                raise ValueError("CUSTOM 레이더는 customRadarMinutesBefore가 필요합니다.")
        else:
            self.custom_radar_minutes_before = None

        if self.penalty_type == PenaltyType.PENALTY:
            self.penalty_content = (self.penalty_content or "").strip() or None
            if self.penalty_content is None:
                raise ValueError("벌칙 모드는 penaltyContent가 필요합니다.")
            self.fine_per_minute = 0
        else:
            if self.fine_per_minute <= 0:
                raise ValueError("지각비 모드는 finePerMinute가 0보다 커야 합니다.")
            self.penalty_content = None
        return self


class AppointmentCreateResponse(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    appointment_id: int
    invite_code: str
    invite_url: str
    radar_start_at: datetime


class InvitePreviewResponse(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    appointment_id: int
    title: str
    meet_at: datetime
    target_place_name: str
    penalty_type: str
    penalty_summary: str
    radar_start_summary: str
    status: str


class JoinRequest(BaseModel):
    # 생략하면 온보딩 닉네임 사용
    nickname: Optional[str] = Field(None, description="약속 내 표시 닉네임 (2~10자)")


class JoinResponse(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    appointment_id: int
    participant_id: int
    join_status: str


class LeaveResponse(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    join_status: str
    message: str
