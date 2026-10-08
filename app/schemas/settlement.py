from typing import Optional

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class SettlementParticipantItem(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    participant_id: int
    nickname: str
    arrival_status: str
    late_minutes: int
    fine_amount: int


class SettlementResponse(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    appointment_id: int
    title: str
    total_fine_amount: int
    share_url: str
    participants: list[SettlementParticipantItem]


class WarrantResponse(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    warrant_id: int
    defendant_participant_id: int
    defendant_nickname: str
    charge_title: str
    late_minutes: int
    judgment_text: str
    final_penalty: str
    share_card_image_url: Optional[str]
    share_link_url: Optional[str]


class WarrantListResponse(BaseModel):
    """[API-10] 지각자 전원의 영장 (지각 시간이 긴 순서)"""
    warrants: list[WarrantResponse]
