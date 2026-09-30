from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException, ErrorCode
from app.models import Appointment, AppointmentStatus, JoinStatus, Participant, User

ENDED_STATUSES = {AppointmentStatus.COMPLETED.value, AppointmentStatus.CANCELLED.value}


def _utcnow() -> datetime:
    # DB에는 UTC naive datetime으로 저장되어 있음
    return datetime.now(timezone.utc).replace(tzinfo=None)


def is_location_sharing_active(appointment: Appointment, now: datetime) -> bool:
    """레이더 시작 시각이 지났거나 RADAR_ACTIVE 상태면 위치 공유 중"""
    if appointment.status in ENDED_STATUSES:
        return False
    return appointment.status == AppointmentStatus.RADAR_ACTIVE.value or now >= appointment.radar_start_at


def remaining_seconds_to_radar(appointment: Appointment, now: datetime) -> int:
    return max(0, int((appointment.radar_start_at - now).total_seconds()))


@dataclass
class HomeAppointment:
    appointment: Appointment
    participant_count: int
    is_location_sharing_active: bool


async def get_home_appointments(db: AsyncSession, user: User) -> tuple[list[HomeAppointment], list[HomeAppointment]]:
    """[API-02] 내가 참여 중인(JOINED) 종료되지 않은 약속을 진행 중/예정으로 나눠 조회"""
    my_appointment_ids = select(Participant.appointment_id).where(
        Participant.user_id == user.id,
        Participant.join_status == JoinStatus.JOINED.value,
    )
    participant_counts = (
        select(Participant.appointment_id, func.count(Participant.id).label("cnt"))
        .where(Participant.join_status == JoinStatus.JOINED.value)
        .group_by(Participant.appointment_id)
        .subquery()
    )
    result = await db.execute(
        select(Appointment, func.coalesce(participant_counts.c.cnt, 0))
        .outerjoin(participant_counts, participant_counts.c.appointment_id == Appointment.id)
        .where(Appointment.id.in_(my_appointment_ids), Appointment.status.not_in(ENDED_STATUSES))
        .order_by(Appointment.meet_at, Appointment.id)
    )

    now = _utcnow()
    active, upcoming = [], []
    for appointment, count in result.all():
        sharing = is_location_sharing_active(appointment, now)
        item = HomeAppointment(appointment=appointment, participant_count=count, is_location_sharing_active=sharing)
        (active if sharing else upcoming).append(item)
    return active, upcoming


async def get_appointment_detail(
    db: AsyncSession, user: User, appointment_id: int
) -> tuple[Appointment, list[Participant]]:
    """[API-07] 약속 상세와 참여 중인 참가자 목록 (참여 중인 참가자만 조회 가능)"""
    appointment = await db.get(Appointment, appointment_id)
    if appointment is None:
        raise AppException(ErrorCode.APPOINTMENT_NOT_FOUND)

    result = await db.execute(
        select(Participant)
        .where(
            Participant.appointment_id == appointment_id,
            Participant.join_status == JoinStatus.JOINED.value,
        )
        # 방장 먼저, 이후 참여 순
        .order_by(Participant.is_host.desc(), Participant.created_at, Participant.id)
    )
    participants = list(result.scalars().all())
    if not any(p.user_id == user.id for p in participants):
        raise AppException(ErrorCode.NOT_PARTICIPANT)
    return appointment, participants
