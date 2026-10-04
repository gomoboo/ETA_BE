import httpx
import pytest

from app.core.config import settings
from app.services import kakao_place_service


@pytest.fixture
def kakao(monkeypatch):
    """카카오 API 호출을 MockTransport로 대체. handler를 지정해서 사용"""
    monkeypatch.setattr(settings, "KAKAO_REST_API_KEY", "test-key")
    real_client = httpx.AsyncClient
    requests = []

    def use(handler):
        def recording_handler(request):
            requests.append(request)
            return handler(request)

        monkeypatch.setattr(
            kakao_place_service.httpx,
            "AsyncClient",
            lambda **kw: real_client(transport=httpx.MockTransport(recording_handler), **kw),
        )
        return requests

    return use


def test_search_formats_places_and_prefers_road_address(client, kakao):
    requests = kakao(lambda request: httpx.Response(200, json={"documents": [
        {"place_name": "스타벅스 강남역점", "road_address_name": "서울 강남구 강남대로 396",
         "address_name": "서울 강남구 역삼동 1", "x": "127.027619", "y": "37.497952"},
        {"place_name": "지번만", "road_address_name": "", "address_name": "서울 어딘가 2", "x": "127.1", "y": "37.5"},
    ]}))

    response = client.get("/api/v1/places/search", params={"query": " 강남역 "})

    assert response.status_code == 200
    assert response.json()["data"]["places"] == [
        {"placeName": "스타벅스 강남역점", "address": "서울 강남구 강남대로 396", "latitude": 37.497952, "longitude": 127.027619},
        {"placeName": "지번만", "address": "서울 어딘가 2", "latitude": 37.5, "longitude": 127.1},
    ]
    assert requests[0].headers["authorization"] == "KakaoAK test-key"
    assert requests[0].url.params["query"] == "강남역"


@pytest.mark.parametrize("handler", [
    lambda request: httpx.Response(401, json={"msg": "bad key"}),
    lambda request: (_ for _ in ()).throw(httpx.ConnectTimeout("timeout")),
])
def test_search_returns_502_when_kakao_fails(client, kakao, handler):
    kakao(handler)
    response = client.get("/api/v1/places/search", params={"query": "강남역"})
    assert (response.status_code, response.json()["code"]) == (502, "KAKAO_API_ERROR")


def test_search_returns_502_without_api_key(client, monkeypatch):
    monkeypatch.setattr(settings, "KAKAO_REST_API_KEY", None)
    response = client.get("/api/v1/places/search", params={"query": "강남역"})
    assert response.status_code == 502


@pytest.mark.parametrize("params", [{}, {"query": "   "}])
def test_search_requires_query(client, params):
    response = client.get("/api/v1/places/search", params=params)
    assert (response.status_code, response.json()["code"]) == (400, "INVALID_INPUT")
