from fastapi import APIRouter

router = APIRouter()

@router.post("/onboarding")
async def register_user():
    """[API-01] 기기 등록 및 온보딩"""
    return {"success": True, "data": {"userId": 101, "nickname": "지민", "locationTermsAgreed": True}}
