from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppException, ErrorCode
from app.core.time import utcnow
from app.models import (
    Appointment,
    AppointmentStatus,
    JoinStatus,
    Participant,
    PenaltyType,
    PokeLog,
    User,
    Warrant,
)

from app.services.location_cleanup_service import clear_location_cache

DEFAULT_CHARGE_TITLE = "침대 미출발 및 상습 지각죄"
NO_SHOW_CHARGE_TITLE = "약속 장소 무단 미도착죄"



@dataclass
class SettlementResult:
    appointment: Appointment
    participants: list[Participant]
    warrant: Warrant | None

    @property
    def total_fine_amount(self) -> int:
        return sum(p.final_fine_amount for p in self.participants)


def build_settlement_share_url(appointment_id: int) -> str:
    return f"{settings.SHARE_BASE_URL.rstrip('/')}/result/settlement/{appointment_id}"


def _build_warrant_urls(warrant_id: int) -> tuple[str, str]:
    base = settings.SHARE_BASE_URL.rstrip("/")
    return f"{base}/cards/warrant_{warrant_id}.png", f"{base}/result/warrant/{warrant_id}"


def calculate_late_minutes(appointment: Appointment, participant: Participant) -> int:
    """도착 시각 - 약속 시각 (분 단위 버림). 미도착자는 정산 타임아웃 시간으로 처리"""
    if participant.arrived_at is None:
        return settings.SETTLEMENT_TIMEOUT_MINUTES
    late_seconds = (participant.arrived_at - appointment.meet_at).total_seconds()
    return max(0, int(late_seconds // 60))


def calculate_fine_amount(appointment: Appointment, late_minutes: int) -> int:
    if appointment.penalty_type == PenaltyType.FEE.value:
        return late_minutes * appointment.fine_per_minute
    return 0


def _is_settlement_ready(appointment: Appointment, participants: list[Participant]) -> bool:
    if appointment.status == AppointmentStatus.COMPLETED.value:
        return True
    if participants and all(p.is_arrived for p in participants):
        return True
    return utcnow() >= appointment.meet_at + timedelta(minutes=settings.SETTLEMENT_TIMEOUT_MINUTES)


async def _get_joined_participants(db: AsyncSession, appointment_id: int) -> list[Participant]:
    result = await db.execute(
        select(Participant)
        .where(Participant.appointment_id == appointment_id, Participant.join_status == JoinStatus.JOINED.value)
        .order_by(Participant.id)
    )
    return list(result.scalars().all())


async def _get_warrant(db: AsyncSession, appointment_id: int) -> Warrant | None:
    return await db.scalar(select(Warrant).where(Warrant.appointment_id == appointment_id))


async def _count_ignored_pokes(db: AsyncSession, participant_id: int) -> int:
    """응답하지 않은 찌르기 횟수"""
    return await db.scalar(
        select(func.count(PokeLog.id)).where(
            PokeLog.target_participant_id == participant_id,
            PokeLog.responded_at.is_(None),
        )
    )


def _build_judgment_text(defendant: Participant, late_minutes: int, ignored_pokes: int) -> str:
    if defendant.arrived_at is None:
        text = f"약속 시간 {late_minutes}분이 지나도록 미도착"
    else:
        text = f"약속 시간 {late_minutes}분 초과"
    if ignored_pokes:
        text += f" 및 찌르기 {ignored_pokes}회 무시"
    return text + " 검거"


def _build_final_penalty(appointment: Appointment, fine_amount: int) -> str:
    if appointment.penalty_type == PenaltyType.FEE.value:
        return f"지각비 {fine_amount:,}원 납부"
    return appointment.penalty_content or ""


async def _issue_warrant(
    db: AsyncSession, appointment: Appointment, participants: list[Participant]
) -> Warrant | None:
    """최다 지각자에게 영장 발부. 지각자가 없으면 발부하지 않음"""
    late_participants = [p for p in participants if p.final_late_minutes > 0]
    if not late_participants:
        return None
    # 지각 시간이 가장 긴 사람, 같으면 먼저 참여한 사람
    defendant = max(late_participants, key=lambda p: (p.final_late_minutes, -p.id))
    ignored_pokes = await _count_ignored_pokes(db, defendant.id)

    warrant = Warrant(
        appointment_id=appointment.id,
        defendant_participant_id=defendant.id,
        charge_title=NO_SHOW_CHARGE_TITLE if defendant.arrived_at is None else DEFAULT_CHARGE_TITLE,
        late_minutes=defendant.final_late_minutes,
        judgment_text=_build_judgment_text(defendant, defendant.final_late_minutes, ignored_pokes),
        final_penalty=_build_final_penalty(appointment, defendant.final_fine_amount),
        total_fine_amount=sum(p.final_fine_amount for p in participants),
    )
    db.add(warrant)
    await db.flush()  # id 발급 후 공유 URL 생성
    warrant.share_card_image_url, warrant.share_link_url = _build_warrant_urls(warrant.id)
    return warrant


async def settle_appointment(db: AsyncSession, user: User, appointment_id: int) -> SettlementResult:
    """[API-09, 10] 정산 결과 조회. 처음 조회 시 지각 시간/지각비 확정, 영장 발부, 약속 COMPLETED 처리"""
    appointment = await db.get(Appointment, appointment_id)
    if appointment is None:
        raise AppException(ErrorCode.APPOINTMENT_NOT_FOUND)

    participants = await _get_joined_participants(db, appointment_id)
    if not any(p.user_id == user.id for p in participants):
        raise AppException(ErrorCode.NOT_PARTICIPANT)
    if appointment.status == AppointmentStatus.CANCELLED.value:
        raise AppException(ErrorCode.SETTLEMENT_NOT_READY, "취소된 약속은 정산할 수 없습니다.")

    # 영장이 발부됐으면 정산 확정 상태 → 저장된 결과 반환
    warrant = await _get_warrant(db, appointment_id)
    if warrant is not None:
        await clear_location_cache(appointment_id)
        return SettlementResult(appointment, participants, warrant)

    if not _is_settlement_ready(appointment, participants):
        raise AppException(ErrorCode.SETTLEMENT_NOT_READY)

    # 도착 시각 기준의 결정적 계산이라 지각자가 없어 영장이 없는 경우 다시 계산해도 결과 동일
    for participant in participants:
        participant.final_late_minutes = calculate_late_minutes(appointment, participant)
        participant.final_fine_amount = calculate_fine_amount(appointment, participant.final_late_minutes)
    warrant = await _issue_warrant(db, appointment, participants)
    appointment.status = AppointmentStatus.COMPLETED.value

    try:
        await db.commit()
    except IntegrityError:
        # 동시에 정산 요청이 들어와 영장이 먼저 발부된 경우 저장된 결과를 사용
        await db.rollback()
        await db.refresh(appointment)
        participants = await _get_joined_participants(db, appointment_id)
        warrant = await _get_warrant(db, appointment_id)
    await clear_location_cache(appointment_id)
    return SettlementResult(appointment, participants, warrant)
