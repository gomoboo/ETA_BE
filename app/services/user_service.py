from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException, ErrorCode
from app.models import JoinStatus, Participant, User
from app.services.location_cleanup_service import clear_location_cache
from app.schemas.user import OnboardingRequest

NICKNAME_MIN_LENGTH = 2
NICKNAME_MAX_LENGTH = 10


def validate_nickname(nickname: str) -> str:
    nickname = nickname.strip()
    if not NICKNAME_MIN_LENGTH <= len(nickname) <= NICKNAME_MAX_LENGTH:
        raise AppException(ErrorCode.INVALID_NICKNAME_LENGTH)
    return nickname


def _apply_onboarding(user: User, request: OnboardingRequest, nickname: str) -> None:
    user.nickname = nickname
    if "location_terms_agreed" in request.model_fields_set:
        user.location_terms_agreed = request.location_terms_agreed
    user.notification_allowed = request.notification_allowed
    # 선택 값은 전달된 경우에만 갱신
    if request.profile_character is not None:
        user.profile_character = request.profile_character
    if request.fcm_token is not None:
        user.fcm_token = request.fcm_token


async def _get_by_guest_uuid(db: AsyncSession, guest_uuid: str) -> User | None:
    result = await db.execute(select(User).where(User.guest_uuid == guest_uuid))
    return result.scalar_one_or_none()


async def onboard_user(db: AsyncSession, request: OnboardingRequest) -> User:
    """[API-01] guestUuid 기준으로 유저가 있으면 갱신, 없으면 생성"""
    nickname = validate_nickname(request.nickname)

    user = await _get_by_guest_uuid(db, request.guest_uuid)
    if user is None:
        user = User(guest_uuid=request.guest_uuid)
        db.add(user)
    _apply_onboarding(user, request, nickname)

    try:
        await db.commit()
    except IntegrityError:
        # 같은 기기에서 동시에 요청해 먼저 생성된 경우 해당 유저를 갱신
        await db.rollback()
        user = await _get_by_guest_uuid(db, request.guest_uuid)
        if user is None:
            raise
        _apply_onboarding(user, request, nickname)
        await db.commit()

    await db.refresh(user)
    if not user.location_terms_agreed:
        participants = await db.scalars(select(Participant).where(
            Participant.user_id == user.id, Participant.join_status == JoinStatus.JOINED.value
        ))
        for participant in participants:
            await clear_location_cache(participant.appointment_id, participant.id)
    return user
