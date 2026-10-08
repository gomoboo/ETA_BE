"""위치 캐시 정리 실패가 이미 확정된 DB 상태를 되돌리지 않도록 처리."""
import logging

from redis.exceptions import RedisError

from app.services.geo_service import GeoService

logger = logging.getLogger(__name__)


async def clear_location_cache(appointment_id: int, participant_id: int | None = None) -> None:
    try:
        if participant_id is None:
            await GeoService.clear_appointment_cache(appointment_id)
        else:
            await GeoService.remove_participant_location(appointment_id, participant_id)
    except RedisError:
        # 캐시는 TTL로도 만료된다. 실패를 기록하고 이후 정산 조회에서 방 전체 삭제를 재시도한다.
        logger.exception("Failed to clear location cache: appointment=%s participant=%s", appointment_id, participant_id)
