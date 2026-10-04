from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class _Payload(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class LocationUpdatePayload(_Payload):
    """[WS-01] location:update"""
    # 연결 URL에 이미 있는 값이라 생략 가능, 보내면 연결 정보와 일치해야 함
    appointment_id: Optional[int] = None
    participant_id: Optional[int] = None
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    speed_kmh: float = Field(0.0, ge=0)


class PokeSendPayload(_Payload):
    """[WS-03] poke:send"""
    appointment_id: Optional[int] = None
    target_participant_id: int


class PokeRespondPayload(_Payload):
    """[WS-05] poke:respond"""
    poke_id: int
    action: Literal["NOW_DEPARTING", "DISMISSED"]
