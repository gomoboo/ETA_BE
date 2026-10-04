from datetime import timedelta

import pytest

from tests.helpers import auth, utc_naive


@pytest.fixture
def setup(client, db, onboard, create_appointment, join):
    """방장(지민), 지원, 민수가 참여한 약속을 만들고 약속 시각을 조정하는 헬퍼 반환"""
    for guest_uuid, nickname in [("host", "지민"), ("u2", "지원"), ("u3", "민수"), ("out", "외부인")]:
        onboard(guest_uuid, nickname)

    def _setup(minutes_since_meet: int, **fields):
        appointment_id = create_appointment("host", **fields)["appointmentId"]
        code = db.scalar("select invite_code from appointments where id=?", appointment_id)
        join("u2", code)
        join("u3", code)
        meet_at = utc_naive(minutes=-minutes_since_meet).replace(microsecond=0)
        db.execute(
            "update appointments set meet_at=?, radar_start_at=? where id=?",
            str(meet_at), str(meet_at - timedelta(minutes=30)), appointment_id,
        )
        return appointment_id, meet_at

    return _setup


def arrive(db, appointment_id, guest_uuid, arrived_at, status):
    db.execute(
        "update participants set is_arrived=1, arrived_at=?, arrival_status=? "
        "where appointment_id=? and user_id=(select id from users where guest_uuid=?)",
        str(arrived_at), status, appointment_id, guest_uuid,
    )


def settlement(client, appointment_id, guest_uuid="host"):
    return client.get(f"/api/v1/appointments/{appointment_id}/settlement", headers=auth(guest_uuid))


def warrant(client, appointment_id, guest_uuid="host"):
    return client.get(f"/api/v1/appointments/{appointment_id}/warrant", headers=auth(guest_uuid))


def rows(data):
    return [(p["nickname"], p["arrivalStatus"], p["lateMinutes"], p["fineAmount"]) for p in data["participants"]]


def test_fee_settlement_after_timeout_with_no_show(client, db, setup):
    appointment_id, meet_at = setup(61, penaltyType="FEE", finePerMinute=1000)
    arrive(db, appointment_id, "host", meet_at - timedelta(minutes=5), "EARLY")
    arrive(db, appointment_id, "u2", meet_at + timedelta(minutes=18, seconds=30), "LATE")  # 초는 버림

    data = settlement(client, appointment_id).json()["data"]

    assert data["totalFineAmount"] == 78000
    assert data["shareUrl"] == f"https://eta.app/result/settlement/{appointment_id}"
    assert rows(data) == [
        ("지민", "EARLY", 0, 0), ("지원", "LATE", 18, 18000), ("민수", "NOT_ARRIVED", 60, 60000),
    ]
    assert db.scalar("select status from appointments where id=?", appointment_id) == "COMPLETED"

    w = warrant(client, appointment_id).json()["data"]
    assert (w["defendantNickname"], w["chargeTitle"], w["lateMinutes"]) == ("민수", "약속 장소 무단 미도착죄", 60)
    assert w["judgmentText"] == "약속 시간 60분이 지나도록 미도착 검거"
    assert w["finalPenalty"] == "지각비 60,000원 납부"
    assert w["shareLinkUrl"] == f"https://eta.app/result/warrant/{w['warrantId']}"


def test_settlement_is_fixed_once_warrant_issued(client, db, setup):
    appointment_id, meet_at = setup(61, penaltyType="FEE", finePerMinute=1000)
    first = settlement(client, appointment_id).json()["data"]
    warrant_id = warrant(client, appointment_id).json()["data"]["warrantId"]

    arrive(db, appointment_id, "u3", meet_at + timedelta(minutes=5), "LATE")  # 확정 후 데이터 변경

    assert settlement(client, appointment_id).json()["data"]["totalFineAmount"] == first["totalFineAmount"]
    assert warrant(client, appointment_id).json()["data"]["warrantId"] == warrant_id
    assert db.scalar("select count(*) from warrants") == 1


def test_penalty_settlement_when_all_arrived_counts_ignored_pokes(client, db, setup):
    appointment_id, meet_at = setup(10)
    arrive(db, appointment_id, "host", meet_at, "ON_TIME")
    arrive(db, appointment_id, "u3", meet_at - timedelta(minutes=1), "EARLY")
    arrive(db, appointment_id, "u2", meet_at + timedelta(minutes=5, seconds=59), "LATE")
    def pid(guest_uuid):
        return db.scalar(
            "select id from participants where appointment_id=? and user_id=(select id from users where guest_uuid=?)",
            appointment_id, guest_uuid,
        )

    for responded in (None, None, "2026-01-01 00:00:00"):  # 무시 2회 + 응답 1회
        db.execute(
            "insert into poke_logs(appointment_id, sender_participant_id, target_participant_id, created_at, responded_at) "
            "values (?, ?, ?, datetime('now'), ?)",
            appointment_id, pid("host"), pid("u2"), responded,
        )

    data = settlement(client, appointment_id).json()["data"]
    assert data["totalFineAmount"] == 0
    assert rows(data)[1] == ("지원", "LATE", 5, 0)

    w = warrant(client, appointment_id, "u3").json()["data"]
    assert (w["defendantNickname"], w["chargeTitle"]) == ("지원", "침대 미출발 및 상습 지각죄")
    assert w["judgmentText"] == "약속 시간 5분 초과 및 찌르기 2회 무시 검거"
    assert w["finalPenalty"] == "커피 쏘기"


def test_no_warrant_when_everyone_on_time(client, db, setup):
    appointment_id, meet_at = setup(5)
    for guest_uuid in ("host", "u2", "u3"):
        arrive(db, appointment_id, guest_uuid, meet_at - timedelta(seconds=10), "EARLY")

    assert settlement(client, appointment_id).status_code == 200
    response = warrant(client, appointment_id)
    assert (response.status_code, response.json()["code"]) == (404, "WARRANT_NOT_FOUND")


def test_completed_status_set_elsewhere_is_still_calculated(client, db, setup):
    # 체크인(#11)에서 COMPLETED만 먼저 바꾼 경우에도 정산이 계산되어야 함
    appointment_id, meet_at = setup(20, penaltyType="FEE", finePerMinute=500)
    arrive(db, appointment_id, "host", meet_at, "ON_TIME")
    arrive(db, appointment_id, "u2", meet_at + timedelta(minutes=10), "LATE")
    arrive(db, appointment_id, "u3", meet_at + timedelta(minutes=3), "LATE")
    db.execute("update appointments set status='COMPLETED' where id=?", appointment_id)

    data = settlement(client, appointment_id).json()["data"]
    assert data["totalFineAmount"] == 6500
    assert warrant(client, appointment_id).json()["data"]["defendantNickname"] == "지원"


def test_arrival_status_without_is_arrived_is_not_arrived(client, db, setup):
    appointment_id, meet_at = setup(5)
    db.execute(
        "update participants set arrival_status='EARLY', arrived_at=? where appointment_id=?",
        str(meet_at), appointment_id,
    )
    assert settlement(client, appointment_id).json()["code"] == "SETTLEMENT_NOT_READY"


@pytest.mark.parametrize("minutes_since_meet", [-60, 30])  # 약속 전 / 약속 후 타임아웃 전
def test_not_ready_before_all_arrived_or_timeout(client, setup, minutes_since_meet):
    appointment_id, _ = setup(minutes_since_meet)
    response = settlement(client, appointment_id)
    assert (response.status_code, response.json()["code"]) == (409, "SETTLEMENT_NOT_READY")


def test_settlement_errors(client, db, setup):
    appointment_id, _ = setup(61)
    assert settlement(client, appointment_id, "out").json()["code"] == "NOT_PARTICIPANT"
    assert settlement(client, 9999).json()["code"] == "APPOINTMENT_NOT_FOUND"

    db.execute("update appointments set status='CANCELLED' where id=?", appointment_id)
    response = settlement(client, appointment_id)
    assert (response.status_code, response.json()["message"]) == (409, "취소된 약속은 정산할 수 없습니다.")


def test_completed_appointment_disappears_from_home(client, setup):
    appointment_id, _ = setup(61)
    settlement(client, appointment_id)
    data = client.get("/api/v1/appointments/home", headers=auth("host")).json()["data"]
    assert data == {"activeAppointments": [], "upcomingAppointments": []}
