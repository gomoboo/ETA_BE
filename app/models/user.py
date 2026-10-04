from app.core.time import utcnow
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.orm import relationship
from app.core.database import Base

class User(Base):
    """
    [API-01] 기기 등록 및 온보딩 사용자 엔티티
    회원가입 없이 기기 고유 UUID를 기반으로 식별합니다.
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, comment="유저 고유 식별자 PK")
    guest_uuid = Column(String(64), unique=True, index=True, nullable=False, comment="클라이언트 기기 고유 UUID")
    nickname = Column(String(20), nullable=False, comment="사용자 닉네임 (2~10자)")
    profile_character = Column(String(50), nullable=False, default="char_rabbit", comment="선택한 프로필 캐릭터 ID")
    location_terms_agreed = Column(Boolean, nullable=False, default=True, comment="위치 정보 수집 약관 동의 여부")
    notification_allowed = Column(Boolean, nullable=False, default=True, comment="FCM 푸시 알림 허용 여부")
    fcm_token = Column(String(255), nullable=True, comment="푸시 알림 전송용 FCM 기기 토큰")

    created_at = Column(DateTime, default=utcnow, nullable=False, comment="생성 일시")
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False, comment="수정 일시")

    # 관계 정의
    participations = relationship("Participant", back_populates="user", cascade="all, delete-orphan")
