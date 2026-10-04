import pytest

from tests.helpers import auth, future_iso


@pytest.fixture
def users(onboard):
    for guest_uuid, nickname in [("host", "지민"), ("u2", "민수"), ("u3", "지원"), ("out", "외부인")]:
        onboard(guest_uuid, nickname)


def home(client, guest_uuid):
    return client.get("/api/v1/appointments/home", headers=auth(guest_uuid)).json()["data"]


def summary(items):
    return [(i["title"], i["isLocationSharingActive"], i["participantCount"]) for i in items]


def test_home_splits_active_and_upcoming(client, db, users, create_appointment, join):
    radar = create_appointment("host", title="A 레이더중", meetAt=future_iso(minutes=10))  # 30분 전 레이더 → 시작됨
    tomorrow = create_appointment("host", title="B 내일", meetAt=future_iso(days=1))
    create_appointment("host", title="C 모레", meetAt=future_iso(days=2))
    cancelled = create_appointment("host", title="D 취소", meetAt=future_iso(days=3))
    left = create_appointment("host", title="E 나감", meetAt=future_iso(days=4))

    for code in (radar["inviteCode"], tomorrow["inviteCode"], left["inviteCode"]):
        join("u2", code)
    join("u3", radar["inviteCode"])
    client.post(f"/api/v1/appointments/{radar['appointmentId']}/leave", headers=auth("u3"))  # 카운트 제외
    client.post(f"/api/v1/appointments/{left['appointmentId']}/leave", headers=auth("host"))
    db.execute("update appointments set status='CANCELLED' where id=?", cancelled["appointmentId"])

    data = home(client, "host")
    assert summary(data["activeAppointments"]) == [("A 레이더중", True, 2)]
    assert summary(data["upcomingAppointments"]) == [("B 내일", False, 2), ("C 모레", False, 1)]

    u2 = home(client, "u2")
    assert [i["title"] for i in u2["upcomingAppointments"]] == ["B 내일", "E 나감"]
    assert home(client, "out") == {"activeAppointments": [], "upcomingAppointments": []}


def test_detail_matches_spec(client, users, create_appointment, join):
    appointment = create_appointment("host", penaltyType="FEE", finePerMinute=1000, meetAt=future_iso(days=2))
    join("u2", appointment["inviteCode"])

    data = client.get(f"/api/v1/appointments/{appointment['appointmentId']}", headers=auth("u2")).json()["data"]

    assert data["targetPlace"] == {
        "name": "스타벅스 강남역점", "address": "서울 강남구 강남대로 396", "latitude": 37.497952, "longitude": 127.027619,
    }
    assert data["penalty"] == {"type": "FEE", "content": None, "finePerMinute": 1000}
    assert data["inviteUrl"] == appointment["inviteUrl"]
    assert data["myParticipantId"] == data["participants"][1]["participantId"]  # 요청자(민수) 본인
    assert data["radarStartAt"] == appointment["radarStartAt"]
    assert abs(data["remainingSecondsToRadar"] - (2 * 86400 - 1800)) <= 5
    assert [(p["nickname"], p["isHost"], p["joinStatus"]) for p in data["participants"]] == [
        ("지민", True, "JOINED"), ("민수", False, "JOINED"),
    ]


def test_detail_remaining_seconds_is_zero_after_radar_start(client, users, create_appointment):
    appointment = create_appointment("host", meetAt=future_iso(minutes=10))
    data = client.get(f"/api/v1/appointments/{appointment['appointmentId']}", headers=auth("host")).json()["data"]
    assert data["remainingSecondsToRadar"] == 0


@pytest.mark.parametrize("guest_uuid, path_id, expected", [
    ("out", None, (403, "NOT_PARTICIPANT")),
    ("host", 9999, (404, "APPOINTMENT_NOT_FOUND")),
    ("host", "abc", (400, "INVALID_INPUT")),
])
def test_detail_errors(client, users, create_appointment, guest_uuid, path_id, expected):
    appointment = create_appointment("host")
    response = client.get(f"/api/v1/appointments/{path_id or appointment['appointmentId']}", headers=auth(guest_uuid))
    assert (response.status_code, response.json()["code"]) == expected


def test_detail_forbidden_after_leaving(client, users, create_appointment, join):
    appointment = create_appointment("host")
    join("u2", appointment["inviteCode"])
    client.post(f"/api/v1/appointments/{appointment['appointmentId']}/leave", headers=auth("u2"))
    response = client.get(f"/api/v1/appointments/{appointment['appointmentId']}", headers=auth("u2"))
    assert response.json()["code"] == "NOT_PARTICIPANT"
