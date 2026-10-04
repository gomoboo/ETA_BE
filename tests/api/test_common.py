import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

from app.core.exception_handlers import register_exception_handlers
from app.core.exceptions import AppException, ErrorCode


class _Body(BaseModel):
    nickname: str = Field(min_length=2)


@pytest.fixture
def handler_client():
    """글로벌 예외 핸들러만 등록한 테스트 전용 앱 (실제 앱 라우트를 오염시키지 않음)"""
    test_app = FastAPI()
    register_exception_handlers(test_app)

    @test_app.get("/app-exception")
    async def raise_app_exception():
        raise AppException(ErrorCode.INVITE_LINK_EXPIRED, "커스텀 메시지")

    @test_app.get("/http-exception")
    async def raise_http_exception():
        raise HTTPException(403, "금지")

    @test_app.post("/validation/{item_id}")
    async def validate(item_id: int, body: _Body):
        return body

    @test_app.get("/boom")
    async def boom():
        raise RuntimeError("unexpected")

    return TestClient(test_app, raise_server_exceptions=False)


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


def test_app_exception_uses_error_code_and_custom_message(handler_client):
    response = handler_client.get("/app-exception")
    assert response.status_code == 410
    assert response.json() == {
        "success": False, "code": "INVITE_LINK_EXPIRED", "message": "커스텀 메시지", "data": None,
    }


def test_http_exception_maps_to_standard_code(handler_client):
    response = handler_client.get("/http-exception")
    assert response.status_code == 403
    assert (response.json()["code"], response.json()["message"]) == ("FORBIDDEN", "금지")


def test_validation_error_lists_fields_without_location_prefix(handler_client):
    response = handler_client.post("/validation/abc", json={"nickname": "a"})
    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "INVALID_INPUT"
    assert {e["field"] for e in body["data"]} == {"item_id", "nickname"}


def test_unhandled_exception_returns_standard_500(handler_client):
    response = handler_client.get("/boom")
    assert response.status_code == 500
    assert response.json()["code"] == "INTERNAL_SERVER_ERROR"


def test_unknown_route_and_method_use_korean_default_message(client):
    not_found = client.get("/no-such-route")
    assert (not_found.status_code, not_found.json()["code"]) == (404, "NOT_FOUND")
    assert not_found.json()["message"] == ErrorCode.NOT_FOUND.message

    not_allowed = client.post("/health")
    assert (not_allowed.status_code, not_allowed.json()["code"]) == (405, "METHOD_NOT_ALLOWED")
