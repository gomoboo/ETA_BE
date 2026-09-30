from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.common import BaseResponse
from app.schemas.user import OnboardingRequest, OnboardingResponse
from app.services import user_service

router = APIRouter()

@router.post("/onboarding", response_model=BaseResponse[OnboardingResponse])
async def register_user(request: OnboardingRequest, db: AsyncSession = Depends(get_db)):
    """[API-01] 기기 등록 및 온보딩"""
    user = await user_service.onboard_user(db, request)
    return BaseResponse(
        data=OnboardingResponse(
            user_id=user.id,
            nickname=user.nickname,
            location_terms_agreed=user.location_terms_agreed,
        )
    )
