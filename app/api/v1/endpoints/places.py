from fastapi import APIRouter, Query

router = APIRouter()

@router.get("/search")
async def search_places(query: str = Query(..., description="장소 검색어")):
    """[API-03] 장소 키워드 검색 (카카오 로컬 API 연동 예정)"""
    return {
        "success": True,
        "data": {
            "places": [
                {
                    "placeName": "스타벅스 강남역신분당역사점",
                    "address": "서울 강남구 강남대로 396",
                    "latitude": 37.497952,
                    "longitude": 127.027619
                }
            ]
        }
    }
