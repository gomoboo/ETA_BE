"""약속 시간 60분 경과 시 조회·소켓·백그라운드에서 공통으로 종료 처리."""
import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.core.time import utcnow
from app.models import Appointment, AppointmentStatus, Participant
from app.services.location_cleanup_service import clear_location_cache

logger = logging.getLogger(__name__)
ENDED_STATUSES = {AppointmentStatus.COMPLETED.value, AppointmentStatus.CANCELLED.value}
EXPIRY_SWEEP_SECONDS = 5


def has_reached_deadline(appointment: Appointment, now: datetime) -> bool:
    return now >= appointment.meet_at + timedelta(minutes=settings.SETTLEMENT_TIMEOUT_MINUTES)


async def complete_expired_appointments(
    db: AsyncSession, *, appointment_id: int | None = None,
    user_id: int | None = None, now: datetime | None = None,
) -> list[int]:
    cutoff = (now or utcnow()) - timedelta(minutes=settings.SETTLEMENT_TIMEOUT_MINUTES)
    statement = update(Appointment).where(
        Appointment.status.not_in(ENDED_STATUSES), Appointment.meet_at <= cutoff,
    )
    if appointment_id is not None:
        statement = statement.where(Appointment.id == appointment_id)
    if user_id is not None:
        statement = statement.where(Appointment.id.in_(
            select(Participant.appointment_id).where(Participant.user_id == user_id)
        ))
    result = await db.execute(statement.values(status=AppointmentStatus.COMPLETED.value).returning(Appointment.id))
    completed_ids = list(result.scalars())
    await db.commit()
    for completed_id in completed_ids:
        await clear_location_cache(completed_id)
    return completed_ids


async def run_expiry_worker(session_factory: async_sessionmaker) -> None:
    """부팅 즉시 및 5초마다 만료 약속을 종료. 요청이 없어도 동작하며 재부팅 후 밀린 건도 처리."""
    while True:
        try:
            async with session_factory() as db:
                await complete_expired_appointments(db)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception('Failed to complete expired appointments; retrying next sweep')
        await asyncio.sleep(EXPIRY_SWEEP_SECONDS)
