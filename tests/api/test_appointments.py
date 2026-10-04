import re

import pytest

from tests.helpers import auth, future_iso

MEET_AT = "2099-09-27T19:00:00Z"


@pytest.fixture
def host(onboard):
    onboard("host", "지민")
    return "host"


def test_create_appointment_matches_spec(client, host, create_appointment, db):
    data = create_appointment(host, meetAt=MEET_AT)

    assert re.fullmatch(r"[A-Z0-9]{6}", data["inviteCode"])
    assert data["inviteUrl"] == f"https://eta.app/invite/{data['inviteCode']}"
    assert data["radarStartAt"] == "2099-09-27T18:30:00Z"

    host_user_id = db.scalar("select id from users where guest_uuid='host'")
    assert db.scalar("select host_id from appointments where id=?", data["appointmentId"]) == host_user_id
    assert db.fetchone(
        "select user_id, is_host, join_status from participants where appointment_id=?", data["appointmentId"]
    ) == (host_user_id, 1, "JOINED")


@pytest.mark.parametrize("fields, expected_radar_start", [
    ({"radarStartType": "10M_BEFORE"}, "2099-09-27T18:50:00Z"),
    ({"radarStartType": "1H_BEFORE"}, "2099-09-27T18:00:00Z"),
    ({"radarStartType": "CUSTOM", "customRadarMinutesBefore": 45}, "2099-09-27T18:15:00Z"),
    ({"meetAt": "2099-09-28T04:00:00+09:00"}, "2099-09-27T18:30:00Z"),  # KST 입력은 UTC로 변환
])
def test_radar_start_at_is_calculated(host, create_appointment, fields, expected_radar_start):
    data = create_appointment(host, **{"meetAt": MEET_AT, **fields})
    assert data["radarStartAt"] == expected_radar_start


def test_fee_mode_stores_fine_and_clears_content(host, create_appointment, db):
    data = create_appointment(host, penaltyType="FEE", finePerMinute=1000, penaltyContent="무시될 값")
    assert db.fetchone(
        "select penalty_type, penalty_content, fine_per_minute from appointments where id=?", data["appointmentId"]
    ) == ("FEE", None, 1000)


def test_penalty_mode_forces_zero_fine(host, create_appointment, db):
    data = create_appointment(host, penaltyType="PENALTY", penaltyContent="커피 쏘기", finePerMinute=5000)
    assert db.scalar("select fine_per_minute from appointments where id=?", data["appointmentId"]) == 0


def test_invite_codes_are_unique(host, create_appointment):
    codes = {create_appointment(host)["inviteCode"] for _ in range(20)}
    assert len(codes) == 20


@pytest.mark.parametrize("fields, field_name", [
    ({"penaltyType": "FINE", "finePerMinute": 1000}, "penaltyType"),  # FINE은 FEE로 통일됨
    ({"radarStartType": "CUSTOM", "customRadarMinutesBefore": None}, ""),
    ({"penaltyType": "PENALTY", "penaltyContent": "  "}, ""),
    ({"penaltyType": "FEE", "finePerMinute": 0}, ""),
    ({"meetAt": "2020-01-01T00:00:00Z"}, "meetAt"),
    ({"radarStartType": "5M_BEFORE"}, "radarStartType"),
    ({"targetLatitude": 91}, "targetLatitude"),
    ({"title": "   "}, "title"),
])
def test_create_appointment_validation(client, host, fields, field_name):
    body = {
        "title": "t", "targetPlaceName": "p", "targetLatitude": 37.0, "targetLongitude": 127.0,
        "meetAt": future_iso(), "penaltyType": "PENALTY", "penaltyContent": "커피", **fields,
    }
    response = client.post("/api/v1/appointments", json=body, headers=auth(host))
    assert (response.status_code, response.json()["code"]) == (400, "INVALID_INPUT")
    assert field_name in {e["field"] for e in response.json()["data"]}
