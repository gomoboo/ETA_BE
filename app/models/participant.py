from app.core.time import utcnow
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, UniqueConstraint, false
from sqlalchemy.orm import relationship
import enum
from app.core.database import Base

class JoinStatus(str, enum.Enum):
    JOINED = "JOINED"  # 참여 중
    LEFT = "LEFT"      # 방 나가기 완료

class ArrivalStatus(str, enum.Enum):
    NOT_ARRIVED = "NOT_ARRIVED"  # 미도착 (이동 중 또는 미출발)
    EARLY = "EARLY"              # 일찍 도착
    ON_TIME = "ON_TIME"          # 정시 도착
    LATE = "LATE"                # 지각 도착

class Participant(Base):
    """
    약속 참가자 엔티티 (User와 Appointment의 N:M 매핑 및 참가 상태 관리)
    """
    __tablename__ = "participants"
    __table_args__ = (
        UniqueConstraint("appointment_id", "user_id", name="uq_participant_appointment_user"),
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, comment="참가자 고유 식별자 PK")
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, comment="유저 식별자 FK")
    appointment_id = Column(Integer, ForeignKey("appointments.id", ondelete="CASCADE"), nullable=False, comment="약속 식별자 FK")

    # 약속 내 프로필 & 권한
    nickname = Column(String(20), nullable=False, comment="약속 내 표시 닉네임")
    is_host = Column(Boolean, nullable=False, default=False, comment="방장 여부")
    is_ready = Column(Boolean, nullable=False, default=True, comment="준비 완료 여부")
    join_status = Column(String(20), nullable=False, default="JOINED", comment="참여 상태 (JOINED, LEFT)")

    # 도착 및 지각 결과
    arrival_status = Column(String(20), nullable=False, default="NOT_ARRIVED", comment="도착 상태 (NOT_ARRIVED, EARLY, ON_TIME, LATE)")
    is_arrived = Column(Boolean, nullable=False, default=False, server_default=false(), comment="도착(체크인) 여부")
    arrived_at = Column(DateTime, nullable=True, comment="실제 도착 인증 시각")
    left_at = Column(DateTime, nullable=True, comment="방 나간(퇴장) 시각")
    final_late_minutes = Column(Integer, nullable=False, default=0, comment="최종 지각 시간 (분)")
    final_fine_amount = Column(Integer, nullable=False, default=0, comment="최종 정산 지각비 (원)")

    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    # 관계 정의
    user = relationship("User", back_populates="participations")
    appointment = relationship("Appointment", back_populates="participants")
