import secrets
import string
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import Appointment, Participant, RadarStartType, User
from app.schemas.appointment import AppointmentCreateRequest

INVITE_CODE_LENGTH = 6
INVITE_CODE_ALPHABET = string.ascii_uppercase + string.digits
MAX_INVITE_CODE_ATTEMPTS = 5

RADAR_MINUTES_BEFORE = {
    RadarStartType.M10_BEFORE: 10,
    RadarStartType.M20_BEFORE: 20,
    RadarStartType.M30_BEFORE: 30,
    RadarStartType.H1_BEFORE: 60,
}


def calculate_radar_minutes(radar_start_type: str, custom_minutes_before: int | None) -> int:
    radar_start_type = RadarStartType(radar_start_type)
    if radar_start_type == RadarStartType.CUSTOM:
        return custom_minutes_before
    return RADAR_MINUTES_BEFORE[radar_start_type]


def generate_invite_code() -> str:
    return "".join(secrets.choice(INVITE_CODE_ALPHABET) for _ in range(INVITE_CODE_LENGTH))


def build_invite_url(invite_code: str) -> str:
    return f"{settings.INVITE_BASE_URL.rstrip('/')}/{invite_code}"


async def _generate_unused_invite_code(db: AsyncSession) -> str:
    while True:
        code = generate_invite_code()
        exists = await db.scalar(select(Appointment.id).where(Appointment.invite_code == code))
        if exists is None:
            return code


async def create_appointment(db: AsyncSession, host: User, request: AppointmentCreateRequest) -> Appointment:
    """[API-04] 약속 생성, 초대 코드 발급, 방장 참가자 등록"""
    # DB에는 UTC naive datetime으로 저장 (기존 created_at 등과 동일)
    meet_at = request.meet_at.replace(tzinfo=None)
    radar_minutes = calculate_radar_minutes(request.radar_start_type, request.custom_radar_minutes_before)
    radar_start_at = meet_at - timedelta(minutes=radar_minutes)
    host_id, host_nickname = host.id, host.nickname

    for attempt in range(MAX_INVITE_CODE_ATTEMPTS):
        appointment = Appointment(
            host_id=host_id,
            title=request.title,
            target_place_name=request.target_place_name,
            target_address=request.target_address,
            target_latitude=request.target_latitude,
            target_longitude=request.target_longitude,
            meet_at=meet_at,
            radar_start_type=request.radar_start_type.value,
            custom_radar_minutes_before=request.custom_radar_minutes_before,
            radar_start_at=radar_start_at,
            penalty_type=request.penalty_type.value,
            penalty_content=request.penalty_content,
            fine_per_minute=request.fine_per_minute,
            invite_code=await _generate_unused_invite_code(db),
        )
        appointment.participants.append(
            Participant(user_id=host_id, nickname=host_nickname, is_host=True)
        )
        db.add(appointment)
        try:
            await db.commit()
            break
        except IntegrityError:
            # 조회와 저장 사이에 같은 초대 코드가 먼저 저장된 경우 재시도
            await db.rollback()
            if attempt == MAX_INVITE_CODE_ATTEMPTS - 1:
                raise

    await db.refresh(appointment)
    return appointment
