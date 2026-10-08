from datetime import timedelta

import pytest
from starlette.websockets import WebSocketDisconnect

from tests.helpers import auth, future_iso, utc_naive

DEST_LAT, DEST_LNG = 37.497952, 127.027619
# 위도 0.00001도 ≈ 1.11m
NEAR_10M = (DEST_LAT + 0.00009, DEST_LNG)
NEAR_40M = (DEST_LAT + 0.00036, DEST_LNG)
FAR_2KM = (37.48, 127.01)


@pytest.fixture
def room(client, db, onboard, create_appointment, join):
    """방장(지민), 민수, 지원이 참여한 약속. 기본은 약속 10분 전(레이더 시작됨)"""
    for guest_uuid, nickname in [("host", "지민"), ("u2", "민수"), ("u3", "지원"), ("out", "외부인")]:
        onboard(guest_uuid, nickname)

    def _room(meet_in_minutes: float = 10, **fields):
        appointment = create_appointment(
            "host", meetAt=future_iso(days=1), targetLatitude=DEST_LAT, targetLongitude=DEST_LNG, **fields
        )
        appointment_id = appointment["appointmentId"]
        join("u2", appointment["inviteCode"])
        join("u3", appointment["inviteCode"])
        meet_at = utc_naive(minutes=meet_in_minutes).replace(microsecond=0)
        db.execute(
            "update appointments set meet_at=?, radar_start_at=? where id=?",
            str(meet_at), str(meet_at - timedelta(minutes=30)), appointment_id,
        )
        pids = {
            guest_uuid: db.scalar(
                "select p.id from participants p join users u on u.id=p.user_id "
                "where p.appointment_id=? and u.guest_uuid=?", appointment_id, guest_uuid,
            )
            for guest_uuid in ("host", "u2", "u3")
        }
        return appointment_id, pids

    return _room


def connect(client, appointment_id, participant_id, guest_uuid):
    return client.websocket_connect(
        f"/api/v1/ws/appointments/{appointment_id}?participant_id={participant_id}&guestUuid={guest_uuid}"
    )


def location(lat_lng, speed=4.0, **extra):
    return {"type": "location:update", "latitude": lat_lng[0], "longitude": lat_lng[1], "speedKmh": speed, **extra}


# ---------- 연결 검증 ----------

def test_rejects_invalid_connections(client, db, room):
    appointment_id, pids = room()
    cases = [
        (appointment_id, pids["host"], ""),            # guestUuid 없음
        (appointment_id, pids["host"], "u2"),          # 다른 사람의 participant_id
        (appointment_id, 9999, "host"),                # 없는 참가자
        (9999, pids["host"], "host"),                  # 없는 약속
    ]
    for args in cases:
        with pytest.raises(WebSocketDisconnect) as exc:
            with connect(client, *args):
                pass
        assert exc.value.code == 1008

    client.post(f"/api/v1/appointments/{appointment_id}/leave", headers=auth("u2"))
    with pytest.raises(WebSocketDisconnect):
        with connect(client, appointment_id, pids["u2"], "u2"):
            pass


def test_guest_uuid_header_is_accepted(client, room):
    appointment_id, pids = room()
    with client.websocket_connect(
        f"/api/v1/ws/appointments/{appointment_id}?participant_id={pids['host']}", headers=auth("host")
    ) as ws:
        ws.send_json(location(FAR_2KM))
        assert ws.receive_json()["type"] == "map:sync"


# ---------- WS-01, WS-02 ----------

def test_location_update_broadcasts_map_sync_and_activates_radar(client, db, room):
    appointment_id, pids = room()
    with connect(client, appointment_id, pids["host"], "host") as host_ws, \
            connect(client, appointment_id, pids["u2"], "u2") as u2_ws:
        host_ws.send_json(location(FAR_2KM, speed=14.5, appointmentId=appointment_id, participantId=pids["host"]))

        for ws in (host_ws, u2_ws):
            message = ws.receive_json()
            assert message["type"] == "map:sync"
            assert message["appointmentId"] == appointment_id
            assert message["destination"] == {"latitude": DEST_LAT, "longitude": DEST_LNG}
            assert len(message["participants"]) == 1  # 위치를 보낸 사람만 포함
            me = message["participants"][0]
            assert (me["participantId"], me["nickname"], me["movementState"]) == (pids["host"], "지민", "MOVING")
            assert 2000 < me["distanceMeter"] < 3000
            assert me["speedKmh"] == 14.5
            assert me["estimatedArrivalMinutes"] >= 1
            assert (me["lateElapsedSeconds"], me["currentAccruedFine"]) == (0, 0)

        u2_ws.send_json(location(FAR_2KM, speed=0))
        assert len(host_ws.receive_json()["participants"]) == 2

    assert db.scalar("select status from appointments where id=?", appointment_id) == "RADAR_ACTIVE"


def test_location_rejected_before_radar_start(client, room):
    appointment_id, pids = room(meet_in_minutes=60)  # 레이더는 30분 전부터
    with connect(client, appointment_id, pids["host"], "host") as ws:
        ws.send_json(location(FAR_2KM))
        assert ws.receive_json() == {
            "type": "error", "code": "RADAR_NOT_STARTED", "message": "아직 위치 공유(레이더)가 시작되지 않았습니다.",
        }


def test_late_participant_shows_elapsed_time_and_accrued_fine(client, room):
    appointment_id, pids = room(meet_in_minutes=-5, penaltyType="FEE", finePerMinute=1000, penaltyContent=None)
    with connect(client, appointment_id, pids["u2"], "u2") as ws:
        ws.send_json(location(FAR_2KM, speed=10))
        me = ws.receive_json()["participants"][0]
        assert me["movementState"] == "LATE"
        assert 300 <= me["lateElapsedSeconds"] < 310
        assert me["currentAccruedFine"] == 5000


@pytest.mark.parametrize("message, expected_code", [
    ("not json", "INVALID_INPUT"),
    ({"type": "unknown:event"}, "INVALID_INPUT"),
    ({"type": "location:update", "latitude": 100, "longitude": 127}, "INVALID_INPUT"),
    ({"type": "location:update", "latitude": 37.4, "longitude": 127, "participantId": 9999}, "INVALID_INPUT"),
])
def test_invalid_messages_return_error_and_keep_connection(client, room, message, expected_code):
    appointment_id, pids = room()
    with connect(client, appointment_id, pids["host"], "host") as ws:
        ws.send_text(message) if isinstance(message, str) else ws.send_json(message)
        error = ws.receive_json()
        assert (error["type"], error["code"]) == ("error", expected_code)

        ws.send_json(location(FAR_2KM))  # 연결은 유지됨
        assert ws.receive_json()["type"] == "map:sync"


def test_reconnect_replaces_previous_connection(client, room):
    appointment_id, pids = room()
    with connect(client, appointment_id, pids["host"], "host") as first:
        with connect(client, appointment_id, pids["host"], "host") as second:
            with pytest.raises(WebSocketDisconnect):
                first.receive_json()  # 이전 연결은 서버가 닫음
            second.send_json(location(FAR_2KM))
            assert second.receive_json()["type"] == "map:sync"


# ---------- WS-06 자동 체크인 ----------

def test_checkin_within_radius_broadcasts_and_saves(client, db, room):
    appointment_id, pids = room(meet_in_minutes=10)
    with connect(client, appointment_id, pids["host"], "host") as host_ws, \
            connect(client, appointment_id, pids["u2"], "u2") as u2_ws:
        u2_ws.send_json(location(NEAR_10M))

        for ws in (host_ws, u2_ws):
            checkin = ws.receive_json()
            assert checkin["type"] == "checkin:completed"
            assert (checkin["participantId"], checkin["nickname"]) == (pids["u2"], "민수")
            assert (checkin["arrivalStatus"], checkin["finalLateMinutes"]) == ("EARLY", 0)
            assert checkin["arrivedAt"].endswith("Z")
            synced = ws.receive_json()
            assert synced["type"] == "map:sync"
            assert synced["participants"][0]["movementState"] == "ARRIVED"
            assert synced["participants"][0]["distanceMeter"] == 0

    assert db.fetchone(
        "select is_arrived, arrival_status, arrived_at is not null from participants where id=?", pids["u2"]
    ) == (1, "EARLY", 1)
    assert db.scalar("select status from appointments where id=?", appointment_id) == "RADAR_ACTIVE"


def test_no_checkin_outside_30m_radius(client, db, room):
    appointment_id, pids = room()
    with connect(client, appointment_id, pids["u2"], "u2") as ws:
        ws.send_json(location(NEAR_40M))  # 50m 안이지만 30m 밖
        assert ws.receive_json()["type"] == "map:sync"
    assert db.scalar("select is_arrived from participants where id=?", pids["u2"]) == 0


def test_late_checkin_records_late_minutes(client, db, room):
    appointment_id, pids = room(meet_in_minutes=-3, penaltyType="FEE", finePerMinute=1000, penaltyContent=None)
    with connect(client, appointment_id, pids["u2"], "u2") as ws:
        ws.send_json(location(NEAR_10M))
        checkin = ws.receive_json()
        assert (checkin["arrivalStatus"], checkin["finalLateMinutes"]) == ("LATE", 3)
    assert db.fetchone("select final_late_minutes, final_fine_amount from participants where id=?", pids["u2"]) == (3, 3000)


def test_all_arrived_completes_appointment_and_settlement_is_ready(client, db, room):
    appointment_id, pids = room(meet_in_minutes=10)
    for guest_uuid in ("host", "u2", "u3"):
        with connect(client, appointment_id, pids[guest_uuid], guest_uuid) as ws:
            ws.send_json(location(NEAR_10M))
            assert ws.receive_json()["type"] == "checkin:completed"
            ws.receive_json()  # map:sync

    assert db.scalar("select status from appointments where id=?", appointment_id) == "COMPLETED"
    response = client.get(f"/api/v1/appointments/{appointment_id}/settlement", headers=auth("host"))
    assert response.status_code == 200
    assert [p["arrivalStatus"] for p in response.json()["data"]["participants"]] == ["EARLY"] * 3

    with pytest.raises(WebSocketDisconnect):  # 종료된 약속에는 연결 불가
        with connect(client, appointment_id, pids["host"], "host"):
            pass


# ---------- WS-03, WS-04, WS-05 찌르기 ----------

def test_poke_send_delivers_to_target_and_respond_updates_log(client, db, room):
    appointment_id, pids = room(meet_in_minutes=18)
    with connect(client, appointment_id, pids["host"], "host") as host_ws, \
            connect(client, appointment_id, pids["u2"], "u2") as u2_ws:
        u2_ws.send_json(location(FAR_2KM, speed=0))
        host_ws.receive_json()
        u2_ws.receive_json()

        host_ws.send_json({"type": "poke:send", "appointmentId": appointment_id, "targetParticipantId": pids["u2"]})
        received = u2_ws.receive_json()
        assert received["type"] == "poke:received"
        assert (received["senderNickname"], received["appointmentTitle"]) == ("지민", "강남역 맛집 탐방")
        assert received["targetPlaceName"] == "스타벅스 강남역점"
        assert received["remainingMinutesToMeet"] in (17, 18)
        assert 2000 < received["remainingDistanceMeter"] < 3000
        poke_id = received["pokeId"]

        u2_ws.send_json({"type": "poke:respond", "pokeId": poke_id, "action": "NOW_DEPARTING"})
        u2_ws.send_json({"type": "poke:respond", "pokeId": poke_id, "action": "DISMISSED"})
        assert u2_ws.receive_json()["code"] == "CONFLICT"  # 이미 응답함

        host_ws.send_json({"type": "poke:respond", "pokeId": poke_id, "action": "DISMISSED"})
        assert host_ws.receive_json()["code"] == "POKE_NOT_FOUND"  # 본인이 받은 찌르기가 아님

    assert db.fetchone(
        "select sender_participant_id, target_participant_id, response_action, responded_at is not null "
        "from poke_logs where id=?", poke_id,
    ) == (pids["host"], pids["u2"], "NOW_DEPARTING", 1)


def test_poke_to_offline_target_is_logged(client, db, room):
    appointment_id, pids = room()
    with connect(client, appointment_id, pids["host"], "host") as ws:
        ws.send_json({"type": "poke:send", "targetParticipantId": pids["u3"]})
        ws.send_json(location(FAR_2KM))
        assert ws.receive_json()["type"] == "map:sync"  # 에러 없이 처리됨
    assert db.scalar("select count(*) from poke_logs where target_participant_id=?", pids["u3"]) == 1


def test_poke_cooldown_per_target(client, db, room):
    appointment_id, pids = room()
    with connect(client, appointment_id, pids["host"], "host") as ws:
        ws.send_json({"type": "poke:send", "targetParticipantId": pids["u2"]})
        ws.send_json({"type": "poke:send", "targetParticipantId": pids["u2"]})  # 바로 다시 찌르기
        error = ws.receive_json()
        assert error["code"] == "POKE_COOLDOWN"
        assert "초 뒤에 다시" in error["message"]

        ws.send_json({"type": "poke:send", "targetParticipantId": pids["u3"]})  # 다른 대상은 가능
        db.execute("update poke_logs set created_at=datetime('now', '-61 seconds')")  # 쿨다운 경과
        ws.send_json({"type": "poke:send", "targetParticipantId": pids["u2"]})
        ws.send_json(location(FAR_2KM))
        assert ws.receive_json()["type"] == "map:sync"  # 에러 없이 처리됨

    assert db.scalar("select count(*) from poke_logs") == 3


def test_poke_validation(client, db, room):
    appointment_id, pids = room()
    db.execute("update participants set is_arrived=1 where id=?", pids["u3"])
    with connect(client, appointment_id, pids["host"], "host") as ws:
        for target, code in [(pids["host"], "INVALID_INPUT"), (pids["u3"], "CONFLICT"), (9999, "NOT_PARTICIPANT")]:
            ws.send_json({"type": "poke:send", "targetParticipantId": target})
            assert ws.receive_json()["code"] == code
        ws.send_json({"type": "poke:respond", "pokeId": 1, "action": "IGNORE"})
        assert ws.receive_json()["code"] == "INVALID_INPUT"


# ---------- 위치 공유 개인정보 보호 회귀 테스트 (#42, #43, #44) ----------

def cache_key(appointment_id):
    return f"eta:appointment:{appointment_id}:locations"


def test_location_requires_consent(client, db, room, onboard, fake_redis):
    aid, pids = room()
    onboard("host", locationTermsAgreed=False)
    assert client.get(f"/api/v1/appointments/{aid}", headers=auth("host")).status_code == 200
    with connect(client, aid, pids["host"], "host") as ws:
        ws.send_json(location(FAR_2KM))
        assert ws.receive_json().get("code") == "LOCATION_CONSENT_REQUIRED"
        assert client.portal.call(fake_redis.exists, cache_key(aid)) == 0
        assert db.scalar("select status from appointments where id=?", aid) == "SCHEDULED"
        onboard("host", locationTermsAgreed=True)
        ws.send_json(location(FAR_2KM))
        assert ws.receive_json()["type"] == "map:sync"


def test_withdrawal_removes_cache_and_blocks_existing_socket(client, room, onboard, fake_redis):
    aid, pids = room()
    with connect(client, aid, pids["host"], "host") as ws:
        ws.send_json(location(FAR_2KM))
        ws.receive_json()
        onboard("host", locationTermsAgreed=False)
        assert client.portal.call(fake_redis.hget, cache_key(aid), str(pids["host"])) is None
        ws.send_json(location(FAR_2KM))
        assert ws.receive_json().get("code") == "LOCATION_CONSENT_REQUIRED"
        assert client.portal.call(fake_redis.exists, cache_key(aid)) == 0


def test_arrived_location_is_frozen_but_socket_receives_other_locations(client, db, room, fake_redis):
    aid, pids = room(meet_in_minutes=-3, penaltyType="FEE", finePerMinute=1000, penaltyContent=None)
    with connect(client, aid, pids["host"], "host") as host, connect(client, aid, pids["u2"], "u2") as other:
        host.send_json(location(NEAR_10M))
        for ws in (host, other):
            assert ws.receive_json()["type"] == "checkin:completed"
            assert ws.receive_json()["type"] == "map:sync"
        cached = client.portal.call(fake_redis.hget, cache_key(aid), str(pids["host"]))
        saved = db.fetchone("select arrived_at, final_late_minutes, final_fine_amount from participants where id=?", pids["host"])
        host.send_json(location(FAR_2KM, speed=50))
        assert host.receive_json().get("code") == "LOCATION_SHARING_ENDED"
        assert client.portal.call(fake_redis.hget, cache_key(aid), str(pids["host"])) == cached
        assert db.fetchone("select arrived_at, final_late_minutes, final_fine_amount from participants where id=?", pids["host"]) == saved
        other.send_json(location(FAR_2KM))
        synced = host.receive_json()
        me = next(p for p in synced["participants"] if p["participantId"] == pids["host"])
        assert (me["latitude"], me["longitude"], me["distanceMeter"], me["speedKmh"]) == (*NEAR_10M, 0, 0)
        assert other.receive_json()["type"] == "map:sync"


def test_leave_removes_only_leaver_cache_and_rejoin_does_not_restore_it(client, db, room, fake_redis, join):
    aid, pids = room()
    for guest in ("host", "u2"):
        with connect(client, aid, pids[guest], guest) as ws:
            ws.send_json(location(FAR_2KM))
            ws.receive_json()
    key = cache_key(aid)
    other = client.portal.call(fake_redis.hget, key, str(pids["u2"]))
    assert client.post(f"/api/v1/appointments/{aid}/leave", headers=auth("host")).status_code == 200
    assert client.portal.call(fake_redis.hget, key, str(pids["host"])) is None
    assert client.portal.call(fake_redis.hget, key, str(pids["u2"])) == other
    assert join("host", db.scalar("select invite_code from appointments where id=?", aid)).status_code == 200
    assert client.portal.call(fake_redis.hget, key, str(pids["host"])) is None


def test_cancel_clears_entire_cache_including_stale_participants(client, db, room, fake_redis):
    aid, pids = room()
    client.portal.call(fake_redis.hset, cache_key(aid), "999", "stale")
    for guest in ("host", "u2", "u3"):
        assert client.post(f"/api/v1/appointments/{aid}/leave", headers=auth(guest)).status_code == 200
    assert db.scalar("select status from appointments where id=?", aid) == "CANCELLED"
    assert client.portal.call(fake_redis.exists, cache_key(aid)) == 0


def test_completion_sends_final_map_then_clears_cache(client, room, fake_redis):
    aid, pids = room()
    for guest in ("host", "u2", "u3"):
        with connect(client, aid, pids[guest], guest) as ws:
            ws.send_json(location(NEAR_10M))
            assert ws.receive_json()["type"] == "checkin:completed"
            synced = ws.receive_json()
            assert len(synced["participants"]) == ("host", "u2", "u3").index(guest) + 1
            assert all(p["movementState"] == "ARRIVED" for p in synced["participants"])
    assert client.portal.call(fake_redis.exists, cache_key(aid)) == 0


def test_leave_succeeds_when_redis_cleanup_fails(client, db, room, monkeypatch, caplog):
    from redis.exceptions import ConnectionError
    from app.services.geo_service import GeoService
    aid, _ = room()
    async def fail(*args, **kwargs):
        raise ConnectionError("test outage")
    monkeypatch.setattr(GeoService, "remove_participant_location", fail, raising=False)
    assert client.post(f"/api/v1/appointments/{aid}/leave", headers=auth("host")).status_code == 200
    assert db.scalar("select join_status from participants where appointment_id=? and user_id=(select id from users where guest_uuid='host')", aid) == "LEFT"
    assert "location cache" in caplog.text


def test_withdrawal_clears_all_joined_rooms(client, room, onboard, fake_redis):
    rooms = [room(), room()]
    for aid, pids in rooms:
        client.portal.call(fake_redis.hset, cache_key(aid), str(pids["host"]), "stale")
    onboard("host", locationTermsAgreed=False)
    for aid, pids in rooms:
        assert client.portal.call(fake_redis.hget, cache_key(aid), str(pids["host"])) is None


def test_withdrawn_location_not_broadcast_when_cleanup_fails(client, room, onboard, fake_redis, monkeypatch):
    from redis.exceptions import ConnectionError
    from app.services.geo_service import GeoService
    aid, pids = room()
    with connect(client, aid, pids["host"], "host") as ws:
        ws.send_json(location(FAR_2KM))
        ws.receive_json()
    async def fail(*args, **kwargs):
        raise ConnectionError("test outage")
    monkeypatch.setattr(GeoService, "remove_participant_location", fail)
    onboard("host", locationTermsAgreed=False)
    assert client.portal.call(fake_redis.hget, cache_key(aid), str(pids["host"])) is not None
    with connect(client, aid, pids["u2"], "u2") as ws:
        ws.send_json(location(FAR_2KM))
        assert [p["participantId"] for p in ws.receive_json()["participants"]] == [pids["u2"]]
