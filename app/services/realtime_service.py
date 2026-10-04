"""[WS-01 ~ WS-06] 실시간 레이더 이벤트 처리 (위치 동기화, 찌르기, 자동 체크인)"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppException, ErrorCode
from app.core.websocket_manager import manager
from app.models import (
    Appointment,
    AppointmentStatus,
    ArrivalStatus,
    JoinStatus,
    Participant,
    PokeLog,
    User,
)
from app.schemas.websocket import LocationUpdatePayload, PokeRespondPayload, PokeSendPayload
from app.services.geo_service import GeoService, is_within_geofence
from app.services.settlement_service import calculate_fine_amount, calculate_late_minutes

logger = logging.getLogger(__name__)

ENDED_STATUSES = {AppointmentStatus.COMPLETED.value, AppointmentStatus.CANCELLED.value}
# 약속 시각 기준 이 시간(초) 이전에 도착하면 EARLY, 그 이후 ~ 1분 미만 지각이면 ON_TIME
ON_TIME_WINDOW_SECONDS = 60


def _utcnow() -> datetime:
    # DB에는 UTC naive datetime으로 저장되어 있음
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _iso_utc(value: datetime) -> str:
    return value.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def _parse(model: type[BaseModel], message: dict) -> Any:
    try:
        return model.model_validate(message)
    except ValidationError as exc:
        error = exc.errors()[0]
        field = ".".join(str(loc) for loc in error["loc"])
        raise AppException(ErrorCode.INVALID_INPUT, f"{field}: {error['msg']}")


def error_event(exc: AppException) -> dict:
    return {"type": "error", "code": exc.code, "message": exc.message}


# ---------- 연결 / 컨텍스트 ----------

async def authorize_connection(
    db: AsyncSession, appointment_id: int, participant_id: int, guest_uuid: str | None
) -> Participant:
    """소켓 연결 시 요청자가 해당 약속에 참여 중(JOINED)인 본인 참가자인지 확인"""
    if not guest_uuid:
        raise AppException(ErrorCode.UNAUTHORIZED, "guestUuid가 필요합니다.")
    appointment, participant = await _load_context(db, appointment_id, participant_id)
    user = await db.get(User, participant.user_id)
    if user is None or user.guest_uuid != guest_uuid:
        raise AppException(ErrorCode.NOT_PARTICIPANT)
    return participant


async def _load_context(db: AsyncSession, appointment_id: int, participant_id: int) -> tuple[Appointment, Participant]:
    appointment = await db.get(Appointment, appointment_id)
    if appointment is None:
        raise AppException(ErrorCode.APPOINTMENT_NOT_FOUND)
    if appointment.status in ENDED_STATUSES:
        raise AppException(ErrorCode.APPOINTMENT_ALREADY_ENDED)
    participant = await db.get(Participant, participant_id)
    if (
        participant is None
        or participant.appointment_id != appointment_id
        or participant.join_status != JoinStatus.JOINED.value
    ):
        raise AppException(ErrorCode.NOT_PARTICIPANT)
    return appointment, participant


async def _joined_participants(db: AsyncSession, appointment_id: int) -> list[Participant]:
    result = await db.execute(
        select(Participant)
        .where(Participant.appointment_id == appointment_id, Participant.join_status == JoinStatus.JOINED.value)
        .order_by(Participant.id)
    )
    return list(result.scalars().all())


# ---------- [WS-01, WS-02] 위치 수신 및 지도 동기화 ----------

def _late_elapsed_seconds(appointment: Appointment, participant: Participant, now: datetime) -> int:
    """약속 시각 이후 경과 초. 도착한 사람은 도착 시각 기준으로 고정"""
    until = participant.arrived_at if participant.is_arrived and participant.arrived_at else now
    return max(0, int((until - appointment.meet_at).total_seconds()))


def _display_movement_state(location: dict, participant: Participant, late_seconds: int) -> str:
    if participant.is_arrived:
        return "ARRIVED"
    state = location.get("movementState", "MOVING")
    # 미출발 의심이 더 중요한 정보라 유지하고, 그 외에는 약속 시간이 지났으면 LATE
    if state != "SUSPECTED_NOT_DEPARTED" and late_seconds > 0:
        return "LATE"
    return state


async def build_map_sync(db: AsyncSession, appointment: Appointment) -> dict:
    """[WS-02] map:sync 메시지 구성 (위치를 한 번 이상 보낸 참여 중 참가자만 포함)"""
    now = _utcnow()
    locations = await GeoService.get_all_participants_locations(appointment.id)
    participants = []
    for participant in await _joined_participants(db, appointment.id):
        location = locations.get(participant.id)
        if location is None:
            continue
        late_seconds = _late_elapsed_seconds(appointment, participant, now)
        participants.append({
            "participantId": participant.id,
            "nickname": participant.nickname,
            "latitude": location["latitude"],
            "longitude": location["longitude"],
            "distanceMeter": location["distanceMeter"],
            "speedKmh": location["speedKmh"],
            "estimatedArrivalMinutes": location["estimatedArrivalMinutes"],
            "movementState": _display_movement_state(location, participant, late_seconds),
            "noMovementMinutes": location["noMovementMinutes"],
            "lateElapsedSeconds": late_seconds,
            "currentAccruedFine": calculate_fine_amount(appointment, late_seconds // 60),
        })
    return {
        "type": "map:sync",
        "appointmentId": appointment.id,
        "destination": {"latitude": appointment.target_latitude, "longitude": appointment.target_longitude},
        "participants": participants,
    }


async def handle_location_update(
    db: AsyncSession, appointment: Appointment, participant: Participant, message: dict
) -> None:
    payload: LocationUpdatePayload = _parse(LocationUpdatePayload, message)
    if payload.appointment_id not in (None, appointment.id) or payload.participant_id not in (None, participant.id):
        raise AppException(ErrorCode.INVALID_INPUT, "연결 정보와 appointmentId/participantId가 일치하지 않습니다.")

    now = _utcnow()
    if appointment.status != AppointmentStatus.RADAR_ACTIVE.value:
        if now < appointment.radar_start_at:
            raise AppException(ErrorCode.RADAR_NOT_STARTED)
        # 레이더 시작 시각 이후 첫 위치 수신 시 상태 전환
        appointment.status = AppointmentStatus.RADAR_ACTIVE.value
        await db.commit()

    await GeoService.update_participant_location(
        appointment_id=appointment.id,
        participant_id=participant.id,
        latitude=payload.latitude,
        longitude=payload.longitude,
        speed_kmh=payload.speed_kmh,
        target_lat=appointment.target_latitude,
        target_lng=appointment.target_longitude,
    )

    if not participant.is_arrived and is_within_geofence(
        payload.latitude, payload.longitude,
        appointment.target_latitude, appointment.target_longitude,
        radius_meters=settings.GEOFENCE_RADIUS_METERS,
    ):
        await checkin_participant(db, appointment, participant, now)

    await manager.broadcast_to_appointment(appointment.id, await build_map_sync(db, appointment))


# ---------- [WS-06] 자동 체크인 ----------

def determine_arrival_status(appointment: Appointment, arrived_at: datetime, late_minutes: int) -> str:
    if late_minutes > 0:
        return ArrivalStatus.LATE.value
    if arrived_at < appointment.meet_at - timedelta(seconds=ON_TIME_WINDOW_SECONDS):
        return ArrivalStatus.EARLY.value
    return ArrivalStatus.ON_TIME.value


async def checkin_participant(
    db: AsyncSession, appointment: Appointment, participant: Participant, arrived_at: datetime
) -> None:
    """도착 확정: 도착 정보 저장, 전원 도착 시 약속 COMPLETED, checkin:completed 브로드캐스트"""
    participant.is_arrived = True
    participant.arrived_at = arrived_at
    participant.final_late_minutes = calculate_late_minutes(appointment, participant)
    participant.final_fine_amount = calculate_fine_amount(appointment, participant.final_late_minutes)
    participant.arrival_status = determine_arrival_status(appointment, arrived_at, participant.final_late_minutes)

    if all(p.is_arrived for p in await _joined_participants(db, appointment.id)):
        appointment.status = AppointmentStatus.COMPLETED.value
    await db.commit()

    await GeoService.mark_participant_arrived(appointment.id, participant.id)
    await manager.broadcast_to_appointment(appointment.id, {
        "type": "checkin:completed",
        "participantId": participant.id,
        "nickname": participant.nickname,
        "arrivedAt": _iso_utc(arrived_at),
        "arrivalStatus": participant.arrival_status,
        "finalLateMinutes": participant.final_late_minutes,
    })


# ---------- [WS-03, WS-04, WS-05] 찌르기 ----------

async def handle_poke_send(
    db: AsyncSession, appointment: Appointment, participant: Participant, message: dict
) -> None:
    payload: PokeSendPayload = _parse(PokeSendPayload, message)
    if payload.appointment_id not in (None, appointment.id):
        raise AppException(ErrorCode.INVALID_INPUT, "연결 정보와 appointmentId가 일치하지 않습니다.")

    target = await db.get(Participant, payload.target_participant_id)
    if target is None or target.appointment_id != appointment.id or target.join_status != JoinStatus.JOINED.value:
        raise AppException(ErrorCode.NOT_PARTICIPANT, "찌를 대상이 이 약속의 참가자가 아닙니다.")
    if target.id == participant.id:
        raise AppException(ErrorCode.INVALID_INPUT, "자기 자신은 찌를 수 없습니다.")
    if target.is_arrived:
        raise AppException(ErrorCode.CONFLICT, "이미 도착한 참가자는 찌를 수 없습니다.")

    poke = PokeLog(
        appointment_id=appointment.id,
        sender_participant_id=participant.id,
        target_participant_id=target.id,
    )
    db.add(poke)
    await db.commit()
    await db.refresh(poke)

    location = await GeoService.get_participant_location(appointment.id, target.id)
    remaining_seconds = (appointment.meet_at - _utcnow()).total_seconds()
    message_to_target = {
        "type": "poke:received",
        "pokeId": poke.id,
        "senderNickname": participant.nickname,
        "appointmentTitle": appointment.title,
        "targetPlaceName": appointment.target_place_name,
        "remainingMinutesToMeet": max(0, int(remaining_seconds // 60)),
        "remainingDistanceMeter": location["distanceMeter"] if location else None,
    }
    if target.id in manager.active_connections.get(appointment.id, {}):
        try:
            await manager.send_to_participant(appointment.id, target.id, message_to_target)
        except Exception:
            logger.warning("Failed to deliver poke %s to participant %s", poke.id, target.id)
    else:
        # TODO: 앱이 꺼져 있으면 FCM 푸시로 대체 발송 (FCM 미구현)
        logger.info("Poke %s target %s is offline; FCM fallback not implemented", poke.id, target.id)


async def handle_poke_respond(
    db: AsyncSession, appointment: Appointment, participant: Participant, message: dict
) -> None:
    payload: PokeRespondPayload = _parse(PokeRespondPayload, message)
    poke = await db.get(PokeLog, payload.poke_id)
    if poke is None or poke.appointment_id != appointment.id or poke.target_participant_id != participant.id:
        raise AppException(ErrorCode.POKE_NOT_FOUND)
    if poke.responded_at is not None:
        raise AppException(ErrorCode.CONFLICT, "이미 응답한 찌르기입니다.")

    poke.response_action = payload.action
    poke.responded_at = _utcnow()
    await db.commit()


# ---------- 디스패처 ----------

Handler = Callable[[AsyncSession, Appointment, Participant, dict], Awaitable[None]]

EVENT_HANDLERS: dict[str, Handler] = {
    "location:update": handle_location_update,
    "poke:send": handle_poke_send,
    "poke:respond": handle_poke_respond,
}


async def dispatch(db: AsyncSession, appointment_id: int, participant_id: int, message: Any) -> None:
    """수신 메시지를 type별 핸들러로 전달. 처리 중 상태가 바뀌었을 수 있어 매번 컨텍스트를 다시 조회"""
    if not isinstance(message, dict):
        raise AppException(ErrorCode.INVALID_INPUT, "메시지는 JSON 객체여야 합니다.")
    handler = EVENT_HANDLERS.get(message.get("type"))
    if handler is None:
        raise AppException(ErrorCode.INVALID_INPUT, f"지원하지 않는 이벤트입니다: {message.get('type')}")
    appointment, participant = await _load_context(db, appointment_id, participant_id)
    await handler(db, appointment, participant, message)
