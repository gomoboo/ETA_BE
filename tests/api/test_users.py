import pytest

from tests.helpers import auth


def test_onboarding_creates_user(client, db):
    response = client.post(
        "/api/v1/users/onboarding",
        json={"guestUuid": "dev-1", "nickname": "지민", "profileCharacter": "char_cat", "fcmToken": "tok"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data == {"userId": data["userId"], "nickname": "지민", "locationTermsAgreed": False}
    assert db.fetchone("select profile_character, fcm_token from users where guest_uuid='dev-1'") == ("char_cat", "tok")


def test_onboarding_again_updates_and_keeps_omitted_optional_fields(client, onboard, db):
    first = onboard("dev-1", "지민", profileCharacter="char_cat", fcmToken="tok")
    second = onboard("dev-1", "  지민이  ", locationTermsAgreed=False)

    assert second["userId"] == first["userId"]
    assert second["nickname"] == "지민이"
    assert second["locationTermsAgreed"] is False
    assert db.fetchone("select profile_character, fcm_token from users where guest_uuid='dev-1'") == ("char_cat", "tok")
    assert db.scalar("select count(*) from users") == 1


@pytest.mark.parametrize("nickname", ["a", "열한글자닉네임입니다요", "   "])
def test_onboarding_rejects_invalid_nickname_length(client, nickname):
    response = client.post("/api/v1/users/onboarding", json={"guestUuid": "dev-1", "nickname": nickname})
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_NICKNAME_LENGTH"


def test_onboarding_requires_guest_uuid(client):
    response = client.post("/api/v1/users/onboarding", json={"nickname": "지민"})
    assert response.status_code == 400
    assert response.json()["data"] == [{"field": "guestUuid", "reason": "Field required"}]


def test_authenticated_api_requires_header_and_registered_user(client):
    missing = client.get("/api/v1/appointments/home")
    assert (missing.status_code, missing.json()["code"]) == (401, "UNAUTHORIZED")

    unknown = client.get("/api/v1/appointments/home", headers=auth("nobody"))
    assert (unknown.status_code, unknown.json()["code"]) == (404, "USER_NOT_FOUND")


def test_guest_uuid_header_is_case_insensitive(client, onboard):
    onboard("dev-1")
    response = client.get("/api/v1/appointments/home", headers={"x-guest-uuid": "dev-1"})
    assert response.status_code == 200


def test_omitted_consent_does_not_restore_withdrawn_consent(client, onboard):
    onboard("dev-1", locationTermsAgreed=False)
    response = client.post("/api/v1/users/onboarding", json={"guestUuid": "dev-1", "nickname": "지민이"})
    assert response.json()["data"]["locationTermsAgreed"] is False


def test_omitted_consent_preserves_existing_agreement(client, onboard):
    onboard("dev-1", locationTermsAgreed=True)
    response = client.post("/api/v1/users/onboarding", json={"guestUuid": "dev-1", "nickname": "지민이"})
    assert response.json()["data"]["locationTermsAgreed"] is True
