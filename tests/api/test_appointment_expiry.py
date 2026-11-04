import time
from datetime import timedelta

import pytest
from redis.exceptions import RedisError
from starlette.websockets import WebSocketDisconnect

from app.core.time import utcnow
from app.services import appointment_lifecycle_service as lifecycle
from app.services import appointment_query_service, realtime_service
from app.services.geo_service import GeoService
from tests.helpers import auth


def past_meet(db, aid, seconds, now):
    meet = now - timedelta(seconds=seconds)
    db.execute('update appointments set meet_at=?, radar_start_at=? where id=?',
               str(meet), str(meet - timedelta(minutes=30)), aid)


def clock(monkeypatch):
    now = utcnow()
    for module in (lifecycle, appointment_query_service, realtime_service):
        monkeypatch.setattr(module, 'utcnow', lambda: now)
    return now


def cache(aid):
    return f'eta:appointment:{aid}:locations'


@pytest.mark.parametrize('seconds, expired', [(3599, False), (3600, True), (3601, True)])
@pytest.mark.parametrize('initial_status', ['SCHEDULED', 'RADAR_ACTIVE'])
def test_exact_deadline_home_and_cache(client, db, onboard, create_appointment, fake_redis, monkeypatch, seconds, expired, initial_status):
    now = clock(monkeypatch)
    onboard('expiry-host')
    aid = create_appointment('expiry-host')['appointmentId']
    past_meet(db, aid, seconds, now)
    db.execute('update appointments set status=? where id=?', initial_status, aid)
    client.portal.call(fake_redis.hset, cache(aid), '999', 'stale')
    data = client.get('/api/v1/appointments/home', headers=auth('expiry-host')).json()['data']
    assert len(data['activeAppointments']) == (0 if expired else 1)
    assert data['upcomingAppointments'] == []
    assert db.scalar('select status from appointments where id=?', aid) == ('COMPLETED' if expired else initial_status)
    assert bool(client.portal.call(fake_redis.exists, cache(aid))) is (not expired)


def test_four_old_appointments_finish_without_settlement(client, db, onboard, create_appointment, monkeypatch):
    now = clock(monkeypatch)
    onboard('expiry-host')
    ids = []
    for seconds in (3601, 7200, 86400, 172800):
        aid = create_appointment('expiry-host')['appointmentId']
        past_meet(db, aid, seconds, now)
        ids.append(aid)
    response = client.get('/api/v1/appointments/home', headers=auth('expiry-host'))
    assert response.json()['data'] == {'activeAppointments': [], 'upcomingAppointments': []}
    assert all(db.scalar('select status from appointments where id=?', aid) == 'COMPLETED' for aid in ids)
    # 기존 정산 결과 계산은 종료 상태에서도 가능해야 한다.
    assert client.get(f'/api/v1/appointments/{ids[0]}/settlement', headers=auth('expiry-host')).status_code == 200


def test_detail_alone_completes_expired_appointment(client, db, onboard, create_appointment, monkeypatch):
    now = clock(monkeypatch)
    onboard('expiry-host')
    aid = create_appointment('expiry-host')['appointmentId']
    past_meet(db, aid, 3600, now)
    data = client.get(f'/api/v1/appointments/{aid}', headers=auth('expiry-host')).json()['data']
    assert data['appointmentId'] == aid
    assert db.scalar('select status from appointments where id=?', aid) == 'COMPLETED'


@pytest.mark.parametrize('event', ['location:update', 'poke:send'])
def test_existing_socket_rejects_events_at_deadline(client, db, onboard, create_appointment, fake_redis, monkeypatch, event):
    now = clock(monkeypatch)
    onboard('expiry-host')
    aid = create_appointment('expiry-host')['appointmentId']
    past_meet(db, aid, 3599, now)
    pid = db.scalar('select id from participants where appointment_id=?', aid)
    with client.websocket_connect(f'/api/v1/ws/appointments/{aid}?participant_id={pid}&guestUuid=expiry-host') as ws:
        ws.send_json({'type': 'location:update', 'latitude': 37.52, 'longitude': 127.04, 'speedKmh': 4})
        assert ws.receive_json()['type'] == 'map:sync'
        past_meet(db, aid, 3600, now)
        ws.send_json({'type': event, 'latitude': 37.52, 'longitude': 127.04, 'targetParticipantId': pid})
        assert ws.receive_json()['code'] == 'APPOINTMENT_ALREADY_ENDED'
        assert client.portal.call(fake_redis.exists, cache(aid)) == 0
    assert db.scalar('select status from appointments where id=?', aid) == 'COMPLETED'


def test_expired_socket_cannot_connect(client, db, onboard, create_appointment, monkeypatch):
    now = clock(monkeypatch)
    onboard('expiry-host')
    aid = create_appointment('expiry-host')['appointmentId']
    past_meet(db, aid, 3600, now)
    pid = db.scalar('select id from participants where appointment_id=?', aid)
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f'/api/v1/ws/appointments/{aid}?participant_id={pid}&guestUuid=expiry-host'):
            pass
    assert db.scalar('select status from appointments where id=?', aid) == 'COMPLETED'


def test_worker_finishes_and_clears_cache_without_any_api_request(client, db, onboard, create_appointment, fake_redis):
    onboard('expiry-host')
    aid = create_appointment('expiry-host')['appointmentId']
    past_meet(db, aid, 3601, utcnow())
    client.portal.call(fake_redis.hset, cache(aid), '999', 'stale')
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        if (db.scalar('select status from appointments where id=?', aid) == 'COMPLETED'
                and client.portal.call(fake_redis.exists, cache(aid)) == 0):
            break
        time.sleep(0.05)
    else:
        pytest.fail('Lifespan worker did not complete and clean up the appointment without a request')


def test_all_arrived_finishes_before_timeout_and_allows_settlement(client, db, onboard, create_appointment, join, fake_redis):
    onboard('expiry-host')
    onboard('expiry-guest')
    from tests.helpers import future_iso
    created = create_appointment('expiry-host', meetAt=future_iso(minutes=10))
    aid = created['appointmentId']
    join('expiry-guest', created['inviteCode'])
    for user in ('expiry-host', 'expiry-guest'):
        detail = client.get(f'/api/v1/appointments/{aid}', headers=auth(user)).json()['data']
        pid = detail['myParticipantId']
        with client.websocket_connect(f'/api/v1/ws/appointments/{aid}?participant_id={pid}&guestUuid={user}') as ws:
            ws.send_json({'type': 'location:update', 'latitude': 37.497952, 'longitude': 127.027619})
            assert ws.receive_json()['type'] == 'checkin:completed'
            assert ws.receive_json()['type'] == 'map:sync'
    assert db.scalar('select status from appointments where id=?', aid) == 'COMPLETED'
    assert client.portal.call(fake_redis.exists, cache(aid)) == 0
    assert client.get('/api/v1/appointments/home', headers=auth('expiry-host')).json()['data'] == {'activeAppointments': [], 'upcomingAppointments': []}
    assert client.get(f'/api/v1/appointments/{aid}/settlement', headers=auth('expiry-host')).status_code == 200


def test_cache_failure_does_not_undo_completion(client, db, onboard, create_appointment, monkeypatch):
    now = clock(monkeypatch)
    onboard('expiry-host')
    aid = create_appointment('expiry-host')['appointmentId']
    past_meet(db, aid, 3600, now)
    async def unavailable(*args, **kwargs):
        raise RedisError('test cache unavailable')
    monkeypatch.setattr(GeoService, 'clear_appointment_cache', unavailable)
    response = client.get('/api/v1/appointments/home', headers=auth('expiry-host'))
    assert response.status_code == 200
    assert response.json()['data']['activeAppointments'] == []
    assert db.scalar('select status from appointments where id=?', aid) == 'COMPLETED'


def test_last_unarrived_participant_leaves_completes_remaining_arrived_group(client, db, onboard, create_appointment, join, fake_redis):
    from tests.helpers import future_iso
    onboard('expiry-host')
    onboard('expiry-guest')
    created = create_appointment('expiry-host', meetAt=future_iso(minutes=10))
    aid = created['appointmentId']
    join('expiry-guest', created['inviteCode'])
    detail = client.get(f'/api/v1/appointments/{aid}', headers=auth('expiry-host')).json()['data']
    pid = detail['myParticipantId']
    with client.websocket_connect(f'/api/v1/ws/appointments/{aid}?participant_id={pid}&guestUuid=expiry-host') as ws:
        ws.send_json({'type': 'location:update', 'latitude': 37.497952, 'longitude': 127.027619})
        assert ws.receive_json()['type'] == 'checkin:completed'
        assert ws.receive_json()['type'] == 'map:sync'
    assert db.scalar('select status from appointments where id=?', aid) == 'RADAR_ACTIVE'
    assert client.post(f'/api/v1/appointments/{aid}/leave', headers=auth('expiry-guest')).status_code == 200
    assert db.scalar('select status from appointments where id=?', aid) == 'COMPLETED'
    assert client.portal.call(fake_redis.exists, cache(aid)) == 0
