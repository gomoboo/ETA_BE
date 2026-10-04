import pytest

from app.core.websocket_manager import manager
from app.services import invite_service
from tests.helpers import auth


@pytest.fixture
def appointment(onboard, create_appointment):
    onboard("host", "지민")
    onboard("u2", "민수")
    onboard("u3", "지원")
    return create_appointment("host")


def preview(client, invite_code):
    return client.get(f"/api/v1/appointments/invite/{invite_code}")


def leave(client, guest_uuid, appointment_id):
    return client.post(f"/api/v1/appointments/{appointment_id}/leave", headers=auth(guest_uuid))


def participant(db, appointment_id, guest_uuid):
    return db.fetchone(
        "select p.id, p.is_host, p.join_status, p.left_at, p.nickname from participants p "
        "join users u on u.id = p.user_id where p.appointment_id=? and u.guest_uuid=?",
        appointment_id, guest_uuid,
    )


# ---------- API-05 미리보기 ----------

def test_preview_without_auth(client, appointment):
    data = preview(client, appointment["inviteCode"]).json()["data"]
    assert data["appointmentId"] == appointment["appointmentId"]
    assert data["penaltyType"] == "PENALTY"
    assert data["penaltySummary"] == "벌칙: 커피 쏘기"
    assert data["radarStartSummary"] == "약속 30분 전부터 위치 공유 시작"
    assert data["status"] == "SCHEDULED"
    assert data["meetAt"].endswith("Z")


def test_preview_summaries_for_fee_and_custom_radar(client, onboard, create_appointment):
    onboard("host")
    code = create_appointment(
        "host", penaltyType="FEE", finePerMinute=1000, radarStartType="CUSTOM", customRadarMinutesBefore=90
    )["inviteCode"]
    data = preview(client, code).json()["data"]
    assert (data["penaltyType"], data["penaltySummary"]) == ("FEE", "지각비: 분당 1,000원")
    assert data["radarStartSummary"] == "약속 1시간 30분 전부터 위치 공유 시작"


def test_preview_code_is_case_insensitive(client, appointment):
    assert preview(client, appointment["inviteCode"].lower()).status_code == 200


def test_preview_unknown_code(client, appointment):
    response = preview(client, "ZZZZZZ")
    assert (response.status_code, response.json()["code"]) == (404, "INVITE_CODE_NOT_FOUND")


@pytest.mark.parametrize("update", [
    "status='CANCELLED'",
    "status='COMPLETED'",
    "meet_at='2020-01-01 00:00:00.000000'",
])
def test_expired_invite_returns_410(client, db, appointment, join, update):
    db.execute(f"update appointments set {update} where id=?", appointment["appointmentId"])
    for response in (preview(client, appointment["inviteCode"]), join("u2", appointment["inviteCode"])):
        assert (response.status_code, response.json()["code"]) == (410, "INVITE_LINK_EXPIRED")


# ---------- API-06 참여 ----------

def test_join_with_and_without_nickname(client, db, appointment, join):
    first = join("u2", appointment["inviteCode"], nickname="민수짱")
    second = join("u3", appointment["inviteCode"])

    assert first.status_code == second.status_code == 200
    assert first.json()["data"]["joinStatus"] == "JOINED"
    assert participant(db, appointment["appointmentId"], "u2")[4] == "민수짱"
    assert participant(db, appointment["appointmentId"], "u3")[4] == "지원"  # 온보딩 닉네임


def test_join_twice_returns_409(appointment, join):
    join("u2", appointment["inviteCode"])
    response = join("u2", appointment["inviteCode"])
    assert (response.status_code, response.json()["code"]) == (409, "ALREADY_JOINED")


def test_join_invalid_nickname(appointment, join):
    response = join("u2", appointment["inviteCode"], nickname="a")
    assert response.json()["code"] == "INVALID_NICKNAME_LENGTH"


def test_concurrent_join_unique_conflict_returns_409(appointment, join, monkeypatch, db):
    join("u2", appointment["inviteCode"])

    async def not_found_yet(db_session, appointment_id, user_id):
        return None  # 조회 시점에는 아직 없던 것처럼 → insert 시 unique 제약 충돌

    monkeypatch.setattr(invite_service, "_get_participant", not_found_yet)
    response = join("u2", appointment["inviteCode"])

    assert (response.status_code, response.json()["code"]) == (409, "ALREADY_JOINED")
    assert db.scalar("select count(*) from participants where appointment_id=?", appointment["appointmentId"]) == 2


# ---------- API-08 나가기 ----------

def test_host_leave_transfers_host_and_records_left_at(client, db, appointment, join):
    join("u2", appointment["inviteCode"])
    join("u3", appointment["inviteCode"])
    appointment_id = appointment["appointmentId"]

    response = leave(client, "host", appointment_id)

    assert response.json()["data"] == {
        "joinStatus": "LEFT", "message": "약속에서 나갔습니다. 위치 공유가 중단되며 정산에서 제외됩니다.",
    }
    _, is_host, join_status, left_at, _ = participant(db, appointment_id, "host")
    assert (is_host, join_status) == (0, "LEFT") and left_at is not None
    assert participant(db, appointment_id, "u2")[1] == 1  # 먼저 참여한 사람이 방장
    assert db.scalar("select host_id from appointments where id=?", appointment_id) == db.scalar(
        "select id from users where guest_uuid='u2'"
    )


def test_last_host_leaving_cancels_appointment(client, db, appointment):
    leave(client, "host", appointment["appointmentId"])
    assert db.scalar("select status from appointments where id=?", appointment["appointmentId"]) == "CANCELLED"

    response = leave(client, "host", appointment["appointmentId"])
    assert (response.status_code, response.json()["code"]) == (409, "APPOINTMENT_ALREADY_ENDED")


def test_rejoin_after_leave_reuses_participant(client, db, appointment, join):
    join("u2", appointment["inviteCode"])
    appointment_id = appointment["appointmentId"]
    leave(client, "u2", appointment_id)

    assert join("u2", appointment["inviteCode"]).status_code == 200
    _, _, join_status, left_at, _ = participant(db, appointment_id, "u2")
    assert (join_status, left_at) == ("JOINED", None)
    assert db.scalar("select count(*) from participants where appointment_id=?", appointment_id) == 2


def test_leave_closes_location_socket(client, appointment, join, monkeypatch):
    join("u2", appointment["inviteCode"])
    appointment_id = appointment["appointmentId"]
    participant_id = client.get(
        f"/api/v1/appointments/{appointment_id}", headers=auth("u2")
    ).json()["data"]["participants"][1]["participantId"]

    class FakeWebSocket:
        closed = False

        async def close(self, *args, **kwargs):
            FakeWebSocket.closed = True

    monkeypatch.setitem(manager.active_connections, appointment_id, {participant_id: FakeWebSocket()})
    leave(client, "u2", appointment_id)

    assert FakeWebSocket.closed is True
    assert appointment_id not in manager.active_connections


@pytest.mark.parametrize("guest_uuid, appointment_id, expected", [
    ("u2", None, (403, "NOT_PARTICIPANT")),       # 참여하지 않은 사람
    ("host", 9999, (404, "APPOINTMENT_NOT_FOUND")),
])
def test_leave_errors(client, appointment, guest_uuid, appointment_id, expected):
    response = leave(client, guest_uuid, appointment_id or appointment["appointmentId"])
    assert (response.status_code, response.json()["code"]) == expected
