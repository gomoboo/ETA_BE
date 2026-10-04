from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.time import utcnow
from app.models import User
from app.schemas.appointment import (
    AppointmentCreateRequest,
    AppointmentCreateResponse,
    AppointmentDetailResponse,
    HomeAppointmentItem,
    HomeAppointmentsResponse,
    InvitePreviewResponse,
    JoinRequest,
    JoinResponse,
    LeaveResponse,
    ParticipantItem,
    PenaltyInfo,
    TargetPlace,
)
from app.schemas.common import BaseResponse
from app.services import appointment_query_service, appointment_service, invite_service

router = APIRouter()


def _as_utc(value: datetime) -> datetime:
    # DB의 UTC naive datetime을 응답용 UTC aware datetime으로 변환
    return value.replace(tzinfo=timezone.utc)


@router.get("/home", response_model=BaseResponse[HomeAppointmentsResponse])
async def get_home_appointments(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """[API-02] 홈 화면 약속 목록 조회"""
    active, upcoming = await appointment_query_service.get_home_appointments(db, current_user)

    def to_item(home: appointment_query_service.HomeAppointment) -> HomeAppointmentItem:
        appointment = home.appointment
        return HomeAppointmentItem(
            appointment_id=appointment.id,
            title=appointment.title,
            meet_at=_as_utc(appointment.meet_at),
            target_place_name=appointment.target_place_name,
            is_location_sharing_active=home.is_location_sharing_active,
            participant_count=home.participant_count,
        )

    return BaseResponse(
        data=HomeAppointmentsResponse(
            active_appointments=[to_item(h) for h in active],
            upcoming_appointments=[to_item(h) for h in upcoming],
        )
    )

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
            radar_start_at=_as_utc(appointment.radar_start_at),
        )
    )

@router.get("/invite/{invite_code}", response_model=BaseResponse[InvitePreviewResponse])
async def preview_invite(invite_code: str, db: AsyncSession = Depends(get_db)):
    """[API-05] 초대 링크 정보 미리보기 (온보딩 전에도 조회 가능)"""
    appointment = await invite_service.get_appointment_by_invite_code(db, invite_code)
    return BaseResponse(
        data=InvitePreviewResponse(
            appointment_id=appointment.id,
            title=appointment.title,
            meet_at=_as_utc(appointment.meet_at),
            target_place_name=appointment.target_place_name,
            penalty_type=appointment.penalty_type,
            penalty_summary=invite_service.build_penalty_summary(appointment),
            radar_start_summary=invite_service.build_radar_start_summary(appointment),
            status=appointment.status,
        )
    )

@router.post("/invite/{invite_code}/join", response_model=BaseResponse[JoinResponse])
async def join_appointment(
    invite_code: str,
    request: JoinRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """[API-06] 초대받은 약속 참여하기"""
    participant = await invite_service.join_appointment(db, current_user, invite_code, request.nickname)
    return BaseResponse(
        data=JoinResponse(
            appointment_id=participant.appointment_id,
            participant_id=participant.id,
            join_status=participant.join_status,
        )
    )

@router.get("/{appointment_id}", response_model=BaseResponse[AppointmentDetailResponse])
async def get_appointment_detail(
    appointment_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """[API-07] 약속 대기 및 상세 화면 조회"""
    appointment, participants = await appointment_query_service.get_appointment_detail(
        db, current_user, appointment_id
    )
    now = utcnow()
    return BaseResponse(
        data=AppointmentDetailResponse(
            appointment_id=appointment.id,
            title=appointment.title,
            meet_at=_as_utc(appointment.meet_at),
            radar_start_at=_as_utc(appointment.radar_start_at),
            remaining_seconds_to_radar=appointment_query_service.remaining_seconds_to_radar(appointment, now),
            target_place=TargetPlace(
                name=appointment.target_place_name,
                address=appointment.target_address,
                latitude=appointment.target_latitude,
                longitude=appointment.target_longitude,
            ),
            penalty=PenaltyInfo(
                type=appointment.penalty_type,
                content=appointment.penalty_content,
                fine_per_minute=appointment.fine_per_minute,
            ),
            invite_url=appointment_service.build_invite_url(appointment.invite_code),
            my_participant_id=next(p.id for p in participants if p.user_id == current_user.id),
            participants=[
                ParticipantItem(
                    participant_id=p.id,
                    nickname=p.nickname,
                    is_host=p.is_host,
                    is_ready=p.is_ready,
                    join_status=p.join_status,
                )
                for p in participants
            ],
        )
    )

@router.post("/{appointment_id}/leave", response_model=BaseResponse[LeaveResponse])
async def leave_appointment(
    appointment_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """[API-08] 약속 나가기"""
    participant = await invite_service.leave_appointment(db, current_user, appointment_id)
    return BaseResponse(
        data=LeaveResponse(join_status=participant.join_status, message=invite_service.LEAVE_MESSAGE)
    )
