from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import AppException, ErrorCode
from app.models import User

# 요청마다 기기 UUID를 전달하는 헤더 (온보딩 시 등록한 guestUuid)
GUEST_UUID_HEADER = "X-Guest-UUID"


async def get_current_user(
    guest_uuid: str | None = Header(None, alias=GUEST_UUID_HEADER, description="온보딩 시 등록한 기기 UUID"),
    db: AsyncSession = Depends(get_db),
) -> User:
    """X-Guest-UUID 헤더로 현재 요청한 유저를 조회"""
    if not guest_uuid:
        raise AppException(ErrorCode.UNAUTHORIZED, f"{GUEST_UUID_HEADER} 헤더가 필요합니다.")

    result = await db.execute(select(User).where(User.guest_uuid == guest_uuid))
    user = result.scalar_one_or_none()
    if user is None:
        raise AppException(ErrorCode.USER_NOT_FOUND)
    return user
