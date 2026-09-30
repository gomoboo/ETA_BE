from datetime import timezone

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import User
from app.schemas.appointment import AppointmentCreateRequest, AppointmentCreateResponse
from app.schemas.common import BaseResponse
from app.services import appointment_service

router = APIRouter()

@router.get("/home")
async def get_home_appointments():
    """[API-02] 홈 화면 약속 목록 조회"""
    return {"success": True, "data": {"activeAppointments": [], "upcomingAppointments": []}}

@router.post("", response_model=BaseResponse[AppointmentCreateResponse])
async def create_appointment(
    request: AppointmentCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """[API-04] 새 약속 생성하기"""
    appointment = await appointment_service.create_appointment(db, current_user, request)
    return BaseResponse(
        data=AppointmentCreateResponse(
            appointment_id=appointment.id,
            invite_code=appointment.invite_code,
            invite_url=appointment_service.build_invite_url(appointment.invite_code),
            radar_start_at=appointment.radar_start_at.replace(tzinfo=timezone.utc),
        )
    )

@router.get("/invite/{invite_code}")
async def preview_invite(invite_code: str):
    """[API-05] 초대 링크 정보 미리보기"""
    return {"success": True, "data": {"appointmentId": 12, "title": "약속"}}

@router.post("/invite/{invite_code}/join")
async def join_appointment(invite_code: str):
    """[API-06] 초대받은 약속 참여하기"""
    return {"success": True, "data": {"appointmentId": 12, "participantId": 45}}

@router.get("/{appointment_id}")
async def get_appointment_detail(appointment_id: int):
    """[API-07] 약속 대기 및 상세 화면 조회"""
    return {"success": True, "data": {"appointmentId": appointment_id}}

@router.post("/{appointment_id}/leave")
async def leave_appointment(appointment_id: int):
    """[API-08] 약속 나가기"""
    return {"success": True, "data": {"joinStatus": "LEFT"}}
