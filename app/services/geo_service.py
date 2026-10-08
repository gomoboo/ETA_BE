import json
import math
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from redis.asyncio import Redis
from app.core.redis import get_redis

# 지구 평균 반경 (미터 단위)
EARTH_RADIUS_METERS = 6371000.0

# 미출발 의심 기준 시간 (초 단위: 5분 = 300초)
SUSPECTED_NOT_DEPARTED_SECONDS = 300

# 정지 판정 기준 속도 (km/h)
STOP_SPEED_THRESHOLD_KMH = 2.0

# 정지 판정 기준 최소 이동 거리 (미터)
MIN_MOVEMENT_METERS = 15.0

# 캐시 유지 시간 (24시간 = 86400초)
CACHE_EXPIRE_SECONDS = 86400


def calculate_haversine_distance(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float
) -> float:
    """
    두 위경도 좌표 간의 대원거리(Haversine 공식)를 계산하여 미터(m) 단위로 반환합니다.
    """
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * (math.sin(delta_lambda / 2.0) ** 2)
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return EARTH_RADIUS_METERS * c


def is_within_geofence(
    current_lat: float,
    current_lng: float,
    target_lat: float,
    target_lng: float,
    radius_meters: float = 50.0
) -> bool:
    """
    목적지 반경(기본 50m) 내에 도달했는지 여부를 판별합니다.
    """
    distance = calculate_haversine_distance(current_lat, current_lng, target_lat, target_lng)
    return distance <= radius_meters


def calculate_estimated_arrival_minutes(
    distance_meters: float,
    speed_kmh: float
) -> Optional[int]:
    """
    남은 거리와 현재 이동 속도를 바탕으로 예상 도착 시간(분)을 계산합니다.
    - 속도가 너무 낮거나 정지 상태인 경우 None을 반환합니다.
    """
    if speed_kmh <= STOP_SPEED_THRESHOLD_KMH or distance_meters <= 0:
        return None

    # speed_kmh를 m/min으로 변환: (km/h * 1000) / 60
    speed_meters_per_minute = (speed_kmh * 1000.0) / 60.0
    minutes = math.ceil(distance_meters / speed_meters_per_minute)
    return max(1, minutes)


class GeoService:
    """
    Redis를 이용한 약속 참가자 실시간 위치 캐싱, 거리 계산, 미출발 의심 감지 서비스
    """

    @staticmethod
    def _get_appointment_locations_key(appointment_id: int) -> str:
        return f"eta:appointment:{appointment_id}:locations"

    @classmethod
    async def update_participant_location(
        cls,
        appointment_id: int,
        participant_id: int,
        latitude: float,
        longitude: float,
        speed_kmh: float,
        target_lat: float,
        target_lng: float,
        redis: Optional[Redis] = None
    ) -> Dict[str, Any]:
        """
        참가자의 최신 위치를 수신하여 정지 시간 및 미출발 여부를 판별한 후 Redis에 캐싱합니다.
        """
        if redis is None:
            redis = await get_redis()

        cache_key = cls._get_appointment_locations_key(appointment_id)
        now_ts = datetime.now(timezone.utc).timestamp()
        now_iso = datetime.now(timezone.utc).isoformat()

        # 1. 목적지까지의 직선 거리 계산
        distance_meter = round(calculate_haversine_distance(
            latitude, longitude, target_lat, target_lng
        ))

        # 2. 이전 캐시 데이터 조회
        prev_raw = await redis.hget(cache_key, str(participant_id))
        prev_data: Optional[Dict[str, Any]] = json.loads(prev_raw) if prev_raw else None

        is_arrived = bool(prev_data and prev_data.get("isArrived", False))

        # 정지 기준점(anchor): 머무르기 시작한 위치와 시각.
        # 직전 위치가 아니라 기준점과의 거리로 판단해야, 위치를 자주 보내는 도보 이동자
        # (예: 5km/h, 3초 간격 → 1회 약 4m 이동)가 정지로 오판되지 않음
        prev_anchor = prev_data.get("stopAnchor") if prev_data else None
        if prev_anchor and calculate_haversine_distance(
            prev_anchor["latitude"], prev_anchor["longitude"], latitude, longitude
        ) < MIN_MOVEMENT_METERS:
            anchor = prev_anchor
        else:
            # 첫 수신이거나 기준점에서 MIN_MOVEMENT_METERS 이상 벗어나면 현재 위치로 기준점 재설정
            anchor = {"latitude": latitude, "longitude": longitude, "since": now_ts}

        # 3. 멈춤 시간(초 및 분) 계산 및 movementState 결정
        no_movement_seconds = int(now_ts - anchor["since"])
        no_movement_minutes = 0
        stopped_since: Optional[float] = None

        if is_arrived:
            movement_state = "ARRIVED"
        elif no_movement_seconds >= SUSPECTED_NOT_DEPARTED_SECONDS:
            # 기준점 반경 안에 5분 이상 머묾 (GPS 속도 값이 튀어도 위치 기준으로 판정)
            movement_state = "SUSPECTED_NOT_DEPARTED"
        elif speed_kmh <= STOP_SPEED_THRESHOLD_KMH:
            movement_state = "STOPPED"
        else:
            movement_state = "MOVING"

        if movement_state in ("STOPPED", "SUSPECTED_NOT_DEPARTED"):
            stopped_since = anchor["since"]
            no_movement_minutes = no_movement_seconds // 60

        # 4. 예상 도착 시간(분)
        estimated_arrival_minutes = calculate_estimated_arrival_minutes(distance_meter, speed_kmh)

        # 5. 캐시 데이터 구성
        location_data: Dict[str, Any] = {
            "participantId": participant_id,
            "latitude": latitude,
            "longitude": longitude,
            "speedKmh": round(speed_kmh, 1),
            "distanceMeter": distance_meter,
            "estimatedArrivalMinutes": estimated_arrival_minutes,
            "movementState": movement_state,
            "noMovementMinutes": no_movement_minutes,
            "stoppedSince": stopped_since,
            "stopAnchor": anchor,
            "updatedAt": now_iso,
            "isArrived": is_arrived,
        }

        # 6. Redis Hash에 저장 및 만료 시간 갱신
        await redis.hset(cache_key, str(participant_id), json.dumps(location_data))
        await redis.expire(cache_key, CACHE_EXPIRE_SECONDS)

        return location_data

    @classmethod
    async def get_participant_location(
        cls,
        appointment_id: int,
        participant_id: int,
        redis: Optional[Redis] = None
    ) -> Optional[Dict[str, Any]]:
        """
        특정 참가자의 캐싱된 위치 정보를 반환합니다.
        """
        if redis is None:
            redis = await get_redis()

        cache_key = cls._get_appointment_locations_key(appointment_id)
        raw = await redis.hget(cache_key, str(participant_id))
        return json.loads(raw) if raw else None

    @classmethod
    async def get_all_participants_locations(
        cls,
        appointment_id: int,
        redis: Optional[Redis] = None
    ) -> Dict[int, Dict[str, Any]]:
        """
        해당 약속에 캐시된 모든 참가자의 최신 위치 정보를 {participant_id: location_dict} 형태로 반환합니다.
        """
        if redis is None:
            redis = await get_redis()

        cache_key = cls._get_appointment_locations_key(appointment_id)
        all_raw = await redis.hgetall(cache_key)

        result: Dict[int, Dict[str, Any]] = {}
        for p_id_str, raw in all_raw.items():
            try:
                result[int(p_id_str)] = json.loads(raw)
            except (ValueError, json.JSONDecodeError):
                continue
        return result

    @classmethod
    async def mark_participant_arrived(
        cls,
        appointment_id: int,
        participant_id: int,
        redis: Optional[Redis] = None
    ) -> Optional[Dict[str, Any]]:
        """
        참가자가 도착(체크인) 완료되었음을 Redis 캐시에 반영합니다.
        """
        if redis is None:
            redis = await get_redis()

        loc = await cls.get_participant_location(appointment_id, participant_id, redis)
        if loc:
            loc["isArrived"] = True
            loc["movementState"] = "ARRIVED"
            loc["speedKmh"] = 0.0
            loc["distanceMeter"] = 0
            loc["estimatedArrivalMinutes"] = 0
            cache_key = cls._get_appointment_locations_key(appointment_id)
            await redis.hset(cache_key, str(participant_id), json.dumps(loc))
            return loc
        return None

    @classmethod
    async def remove_participant_location(
        cls, appointment_id: int, participant_id: int, redis: Optional[Redis] = None
    ) -> None:
        """나가거나 위치 동의를 철회한 참가자의 위치만 삭제합니다."""
        if redis is None:
            redis = await get_redis()
        await redis.hdel(cls._get_appointment_locations_key(appointment_id), str(participant_id))

    @classmethod
    async def clear_appointment_cache(
        cls,
        appointment_id: int,
        redis: Optional[Redis] = None
    ) -> None:
        """
        약속 종료 또는 취소 시 캐시된 위치 데이터를 삭제합니다.
        """
        if redis is None:
            redis = await get_redis()

        cache_key = cls._get_appointment_locations_key(appointment_id)
        await redis.delete(cache_key)
