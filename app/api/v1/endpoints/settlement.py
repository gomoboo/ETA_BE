from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.exceptions import AppException, ErrorCode
from app.models import User
from app.schemas.common import BaseResponse
from app.schemas.settlement import (
    SettlementParticipantItem,
    SettlementResponse,
    WarrantListResponse,
    WarrantResponse,
)
from app.services import settlement_service

router = APIRouter()

@router.get("/{appointment_id}/settlement", response_model=BaseResponse[SettlementResponse])
async def get_settlement(
    appointment_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """[API-09] 지각비 정산 결과 조회"""
    result = await settlement_service.settle_appointment(db, current_user, appointment_id)
    return BaseResponse(
        data=SettlementResponse(
            appointment_id=result.appointment.id,
            title=result.appointment.title,
            total_fine_amount=result.total_fine_amount,
            share_url=settlement_service.build_settlement_share_url(result.appointment.id),
            participants=[
                SettlementParticipantItem(
                    participant_id=p.id,
                    nickname=p.nickname,
                    arrival_status=p.arrival_status,
                    late_minutes=p.final_late_minutes,
                    fine_amount=p.final_fine_amount,
                )
                for p in result.participants
            ],
        )
    )

@router.get("/{appointment_id}/warrant", response_model=BaseResponse[WarrantListResponse])
async def get_warrant(
    appointment_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """[API-10] 지각 체포 영장 및 결과 카드 조회 (지각자 전원, 지각 시간이 긴 순서)"""
    result = await settlement_service.settle_appointment(db, current_user, appointment_id)
    nicknames = {p.id: p.nickname for p in result.participants}
    warrants = [w for w in result.warrants if w.defendant_participant_id in nicknames]
    if not warrants:
        raise AppException(ErrorCode.WARRANT_NOT_FOUND, "지각자가 없어 발부된 체포 영장이 없습니다.")
    return BaseResponse(
        data=WarrantListResponse(
            warrants=[
                WarrantResponse(
                    warrant_id=w.id,
                    defendant_participant_id=w.defendant_participant_id,
                    defendant_nickname=nicknames[w.defendant_participant_id],
                    charge_title=w.charge_title,
                    late_minutes=w.late_minutes,
                    judgment_text=w.judgment_text,
                    final_penalty=w.final_penalty,
                    share_card_image_url=w.share_card_image_url,
                    share_link_url=w.share_link_url,
                )
                for w in warrants
            ]
        )
    )
