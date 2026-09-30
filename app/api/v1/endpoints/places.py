from fastapi import APIRouter, Query

from app.core.exceptions import AppException, ErrorCode
from app.schemas.common import BaseResponse
from app.schemas.place import PlaceSearchResponse
from app.services import kakao_place_service

router = APIRouter()

@router.get("/search", response_model=BaseResponse[PlaceSearchResponse])
async def search_places(query: str = Query(..., min_length=1, max_length=100, description="장소 검색어")):
    """[API-03] 장소 키워드 검색 (카카오 로컬 API 연동)"""
    query = query.strip()
    if not query:
        raise AppException(ErrorCode.INVALID_INPUT, "검색어를 입력해주세요.")
    places = await kakao_place_service.search_places(query)
    return BaseResponse(data=PlaceSearchResponse(places=places))
