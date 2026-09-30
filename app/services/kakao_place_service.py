import logging
from typing import List

import httpx

from app.core.config import settings
from app.core.exceptions import AppException, ErrorCode
from app.schemas.place import PlaceItem

logger = logging.getLogger(__name__)

KAKAO_KEYWORD_SEARCH_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"
REQUEST_TIMEOUT_SECONDS = 5.0
MAX_PAGE_SIZE = 15  # 카카오 키워드 검색 size 최댓값


async def search_places(query: str, size: int = MAX_PAGE_SIZE) -> List[PlaceItem]:
    """카카오 로컬 키워드 검색 API로 장소 목록과 좌표를 조회"""
    if not settings.KAKAO_REST_API_KEY:
        logger.error("KAKAO_REST_API_KEY is not configured")
        raise AppException(ErrorCode.KAKAO_API_ERROR)

    headers = {"Authorization": f"KakaoAK {settings.KAKAO_REST_API_KEY}"}
    params = {"query": query, "size": size}

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.get(KAKAO_KEYWORD_SEARCH_URL, headers=headers, params=params)
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        logger.error("Kakao API error: %s %s", exc.response.status_code, exc.response.text)
        raise AppException(ErrorCode.KAKAO_API_ERROR)
    except httpx.HTTPError as exc:
        logger.error("Kakao API request failed: %r", exc)
        raise AppException(ErrorCode.KAKAO_API_ERROR)

    documents = response.json().get("documents", [])
    return [
        PlaceItem(
            place_name=doc["place_name"],
            # 도로명 주소 우선, 없으면 지번 주소
            address=doc.get("road_address_name") or doc.get("address_name", ""),
            latitude=float(doc["y"]),
            longitude=float(doc["x"]),
        )
        for doc in documents
    ]
