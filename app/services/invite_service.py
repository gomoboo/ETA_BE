import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException, ErrorCode
from app.core.websocket_manager import manager
from app.models import Appointment, AppointmentStatus, JoinStatus, Participant, PenaltyType, User
from app.services.appointment_service import calculate_radar_minutes
from app.services.user_service import validate_nickname

logger = logging.getLogger(__name__)

ENDED_STATUSES = {AppointmentStatus.COMPLETED.value, AppointmentStatus.CANCELLED.value}
LEAVE_MESSAGE = "약속에서 나갔습니다. 위치 공유가 중단되며 정산에서 제외됩니다."


def _utcnow() -> datetime:
    # DB에는 UTC naive datetime으로 저장되어 있음
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _format_minutes(minutes: int) -> str:
    hours, mins = divmod(minutes, 60)
    if hours and mins:
        return f"{hours}시간 {mins}분"
    if hours:
        return f"{hours}시간"
    return f"{mins}분"


def build_penalty_summary(appointment: Appointment) -> str:
    if appointment.penalty_type == PenaltyType.FINE.value:
        return f"지각비: 분당 {appointment.fine_per_minute:,}원"
    return f"벌칙: {appointment.penalty_content}"


def build_radar_start_summary(appointment: Appointment) -> str:
    minutes = calculate_radar_minutes(appointment.radar_start_type, appointment.custom_radar_minutes_before)
    return f"약속 {_format_minutes(minutes)} 전부터 위치 공유 시작"


def _is_invite_expired(appointment: Appointment) -> bool:
    """종료/취소되었거나 약속 시간이 지난 약속은 초대 링크 만료 (FR-25)"""
    return appointment.status in ENDED_STATUSES or _utcnow() >= appointment.meet_at


async def get_appointment_by_invite_code(db: AsyncSession, invite_code: str) -> Appointment:
    result = await db.execute(select(Appointment).where(Appointment.invite_code == invite_code.upper()))
    appointment = result.scalar_one_or_none()
    if appointment is None:
        raise AppException(ErrorCode.INVITE_CODE_NOT_FOUND)
    if _is_invite_expired(appointment):
        raise AppException(ErrorCode.INVITE_LINK_EXPIRED)
    return appointment


async def _get_participant(db: AsyncSession, appointment_id: int, user_id: int) -> Participant | None:
    result = await db.execute(
        select(Participant)
        .where(Participant.appointment_id == appointment_id, Participant.user_id == user_id)
        .order_by(Participant.id)
    )
    return result.scalars().first()


async def join_appointment(db: AsyncSession, user: User, invite_code: str, nickname: str | None) -> Participant:
    """[API-06] 초대 코드로 약속 참여. 나갔던 약속이면 다시 참여 처리"""
    appointment = await get_appointment_by_invite_code(db, invite_code)
    nickname = validate_nickname(nickname) if nickname is not None else user.nickname

    participant = await _get_participant(db, appointment.id, user.id)
    if participant is None:
        participant = Participant(user_id=user.id, appointment_id=appointment.id, nickname=nickname)
        db.add(participant)
    elif participant.join_status == JoinStatus.JOINED.value:
        raise AppException(ErrorCode.ALREADY_JOINED)
    else:
        participant.join_status = JoinStatus.JOINED.value
        participant.nickname = nickname

    await db.commit()
    await db.refresh(participant)
    return participant


async def _close_location_socket(appointment_id: int, participant_id: int) -> None:
    """나간 참가자의 웹소켓 연결을 끊어 위치 공유 중단"""
    websocket = manager.active_connections.get(appointment_id, {}).get(participant_id)
    if websocket is None:
        return
    manager.disconnect(appointment_id, participant_id)
    try:
        await websocket.close()
    except Exception:
        logger.warning("Failed to close websocket: appointment=%s participant=%s", appointment_id, participant_id)


async def leave_appointment(db: AsyncSession, user: User, appointment_id: int) -> Participant:
    """[API-08] 약속 나가기. 방장이 나가면 가장 먼저 참여한 참가자에게 방장 위임"""
    appointment = await db.get(Appointment, appointment_id)
    if appointment is None:
        raise AppException(ErrorCode.APPOINTMENT_NOT_FOUND)
    if appointment.status in ENDED_STATUSES:
        raise AppException(ErrorCode.APPOINTMENT_ALREADY_ENDED)

    participant = await _get_participant(db, appointment_id, user.id)
    if participant is None or participant.join_status != JoinStatus.JOINED.value:
        raise AppException(ErrorCode.NOT_PARTICIPANT)

    participant.join_status = JoinStatus.LEFT.value
    if participant.is_host:
        participant.is_host = False
        result = await db.execute(
            select(Participant)
            .where(
                Participant.appointment_id == appointment_id,
                Participant.join_status == JoinStatus.JOINED.value,
                Participant.id != participant.id,
            )
            .order_by(Participant.created_at, Participant.id)
        )
        next_host = result.scalars().first()
        if next_host is not None:
            next_host.is_host = True
        else:
            # 남은 참가자가 없으면 약속 취소
            appointment.status = AppointmentStatus.CANCELLED.value

    await db.commit()
    await _close_location_socket(appointment_id, participant.id)
    return participant
