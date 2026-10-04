import pytest
import json
from datetime import datetime
from unittest.mock import AsyncMock, patch
import app.services.geo_service as geo_service_module
from app.services.geo_service import (
    calculate_haversine_distance,
    is_within_geofence,
    calculate_estimated_arrival_minutes,
    GeoService,
)

def test_haversine_distance_same_location():
    lat, lng = 37.497952, 127.027619
    dist = calculate_haversine_distance(lat, lng, lat, lng)
    assert dist == 0.0

def test_haversine_distance_known_points():
    # 강남역 2번 출구 (37.497952, 127.027619) ~ 역삼역 3번 출구 (37.500628, 127.036447)
    # 직선거리 약 820m
    dist = calculate_haversine_distance(37.497952, 127.027619, 37.500628, 127.036447)
    assert 750 <= dist <= 900

def test_is_within_geofence():
    target_lat, target_lng = 37.497952, 127.027619
    # 아주 가까운 위치 (약 10m 이내)
    near_lat, near_lng = 37.498000, 127.027650
    # 먼 위치 (약 800m)
    far_lat, far_lng = 37.500628, 127.036447

    assert is_within_geofence(near_lat, near_lng, target_lat, target_lng, radius_meters=50.0) is True
    assert is_within_geofence(far_lat, far_lng, target_lat, target_lng, radius_meters=50.0) is False

def test_calculate_estimated_arrival_minutes():
    # 1000m를 20km/h로 이동 -> 1000 / (20000/60) = 3분
    assert calculate_estimated_arrival_minutes(1000, 20.0) == 3
    # 0km/h (정지) -> None
    assert calculate_estimated_arrival_minutes(1000, 0.0) is None
    # 1.5km/h (임계값 이하 정지) -> None
    assert calculate_estimated_arrival_minutes(1000, 1.5) is None

@pytest.mark.asyncio
async def test_geo_service_update_and_suspected_not_departed():
    mock_redis = AsyncMock()
    cache_store = {}

    async def mock_hget(key, field):
        return cache_store.get(f"{key}:{field}")

    async def mock_hset(key, field, value):
        cache_store[f"{key}:{field}"] = value

    async def mock_expire(key, seconds):
        return True

    mock_redis.hget.side_effect = mock_hget
    mock_redis.hset.side_effect = mock_hset
    mock_redis.expire.side_effect = mock_expire

    appointment_id = 12
    participant_id = 45
    target_lat, target_lng = 37.497952, 127.027619

    # 1. 첫 위치 수신: 정지 상태 (속도 0km/h)
    loc1 = await GeoService.update_participant_location(
        appointment_id=appointment_id,
        participant_id=participant_id,
        latitude=37.480000,
        longitude=127.010000,
        speed_kmh=0.0,
        target_lat=target_lat,
        target_lng=target_lng,
        redis=mock_redis
    )
    assert loc1["movementState"] == "STOPPED"
    assert loc1["noMovementMinutes"] == 0

    # 2. 5분(301초) 전 시각으로 정지 기준점 시각을 인위적 조정하여 재수신 시뮬레이션
    stored_data = json.loads(cache_store[f"eta:appointment:{appointment_id}:locations:{participant_id}"])
    stored_data["stopAnchor"]["since"] -= 301
    cache_store[f"eta:appointment:{appointment_id}:locations:{participant_id}"] = json.dumps(stored_data)

    loc2 = await GeoService.update_participant_location(
        appointment_id=appointment_id,
        participant_id=participant_id,
        latitude=37.480000,
        longitude=127.010000,
        speed_kmh=0.0,
        target_lat=target_lat,
        target_lng=target_lng,
        redis=mock_redis
    )
    assert loc2["movementState"] == "SUSPECTED_NOT_DEPARTED"
    assert loc2["noMovementMinutes"] >= 5

    # 3. 이동 시작 (속도 15km/h, 위치 변경) -> "MOVING" 상태 복귀
    loc3 = await GeoService.update_participant_location(
        appointment_id=appointment_id,
        participant_id=participant_id,
        latitude=37.485000,
        longitude=127.015000,
        speed_kmh=15.0,
        target_lat=target_lat,
        target_lng=target_lng,
        redis=mock_redis
    )
    assert loc3["movementState"] == "MOVING"
    assert loc3["noMovementMinutes"] == 0
    assert loc3["stoppedSince"] is None

    # 4. 도착 체크인 시뮬레이션
    loc_arrived = await GeoService.mark_participant_arrived(
        appointment_id=appointment_id,
        participant_id=participant_id,
        redis=mock_redis
    )
    assert loc_arrived["isArrived"] is True
    assert loc_arrived["movementState"] == "ARRIVED"
    assert loc_arrived["distanceMeter"] == 0

@pytest.mark.asyncio
async def test_geo_service_get_all_and_clear():
    mock_redis = AsyncMock()
    cache_store = {
        "10": json.dumps({"participantId": 10, "latitude": 37.5, "longitude": 127.0}),
        "20": json.dumps({"participantId": 20, "latitude": 37.6, "longitude": 127.1}),
    }
    mock_redis.hgetall.return_value = cache_store
    mock_redis.delete = AsyncMock()

    # 전체 참가자 위치 조회
    all_locs = await GeoService.get_all_participants_locations(appointment_id=99, redis=mock_redis)
    assert len(all_locs) == 2
    assert 10 in all_locs
    assert 20 in all_locs
    assert all_locs[10]["latitude"] == 37.5

    # 캐시 초기화
    await GeoService.clear_appointment_cache(appointment_id=99, redis=mock_redis)
    mock_redis.delete.assert_called_once_with("eta:appointment:99:locations")



def _make_fake_redis():
    mock_redis = AsyncMock()
    cache_store = {}

    async def mock_hget(key, field):
        return cache_store.get(f"{key}:{field}")

    async def mock_hset(key, field, value):
        cache_store[f"{key}:{field}"] = value

    mock_redis.hget.side_effect = mock_hget
    mock_redis.hset.side_effect = mock_hset
    mock_redis.expire.return_value = True
    return mock_redis


async def _simulate_updates(positions, speed_kmh, interval_seconds):
    """positions 순서대로 interval_seconds 간격으로 위치를 전송하고 movementState 목록을 반환"""
    mock_redis = _make_fake_redis()
    clock = [1_000_000.0]

    class FakeDateTime:
        @staticmethod
        def now(tz=None):
            return datetime.fromtimestamp(clock[0], tz)

    states = []
    with patch.object(geo_service_module, "datetime", FakeDateTime):
        for lat, lng in positions:
            loc = await GeoService.update_participant_location(
                appointment_id=1,
                participant_id=1,
                latitude=lat,
                longitude=lng,
                speed_kmh=speed_kmh,
                target_lat=37.5,
                target_lng=127.03,
                redis=mock_redis,
            )
            states.append(loc["movementState"])
            clock[0] += interval_seconds
    return states


@pytest.mark.asyncio
@pytest.mark.parametrize("speed_kmh, interval_seconds", [(5.0, 3), (5.0, 10), (4.0, 5)])
async def test_walking_with_frequent_updates_is_not_suspected(speed_kmh, interval_seconds):
    # 걸어서 이동 중인 참가자가 위치를 자주 보내 1회 이동 거리가 15m 미만이어도 미출발 의심이 아니어야 함
    step_degrees = (speed_kmh * 1000 / 3600 * interval_seconds) / 111_000
    count = int(7 * 60 / interval_seconds)
    positions = [(37.48 + step_degrees * i, 127.01) for i in range(count)]

    states = await _simulate_updates(positions, speed_kmh, interval_seconds)

    assert "SUSPECTED_NOT_DEPARTED" not in states
    assert states[-1] == "MOVING"


@pytest.mark.asyncio
async def test_staying_within_gps_jitter_is_suspected():
    # 제자리에서 GPS 오차(±약 5m)로 위치와 속도 값이 흔들려도 5분 이상 머물면 미출발 의심
    jitter = [(0, 0), (0.00004, 0), (0, 0.00005), (-0.00004, 0), (0, -0.00005)]
    positions = [(37.48 + dlat, 127.01 + dlng) for dlat, dlng in jitter * 30]  # 10초 간격, 25분

    states = await _simulate_updates(positions, speed_kmh=3.0, interval_seconds=10)

    assert states[0] == "MOVING"
    assert states[int(300 / 10)] == "SUSPECTED_NOT_DEPARTED"
    assert states[-1] == "SUSPECTED_NOT_DEPARTED"
