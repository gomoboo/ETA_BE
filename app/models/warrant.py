from app.core.time import utcnow
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from app.core.database import Base

class Warrant(Base):
    """
    [API-10] 지각 체포 영장 및 결과 카드 엔티티
    약속 종료 후 지각자마다 1장씩 발부되는 재미 요소 겸 결과 요약입니다.
    """
    __tablename__ = "warrants"
    __table_args__ = (
        # 동시 정산 요청에도 같은 지각자에게 영장이 두 번 발부되지 않도록
        UniqueConstraint("appointment_id", "defendant_participant_id", name="uq_warrants_appointment_defendant"),
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, comment="영장 고유 식별자 PK")
    appointment_id = Column(Integer, ForeignKey("appointments.id", ondelete="CASCADE"), index=True, nullable=False, comment="대상 약속 FK (1:N, 지각자당 1장)")
    defendant_participant_id = Column(Integer, ForeignKey("participants.id", ondelete="SET NULL"), nullable=True, comment="피고인(지각자) 참가자 FK")

    # 영장 세부 내용
    charge_title = Column(String(100), nullable=False, default="침대 미출발 및 상습 지각죄", comment="죄명")
    late_minutes = Column(Integer, nullable=False, default=0, comment="지각 시간 (분)")
    judgment_text = Column(Text, nullable=False, comment="판결문 요약 (예: 약속 시간 18분 초과 및 5분간 미출발 검거)")
    final_penalty = Column(String(150), nullable=False, comment="최종 집행 벌칙/지각비 문구")
    total_fine_amount = Column(Integer, nullable=False, default=0, comment="약속 전체 지각비 총합")

    # 공유 및 이미지
    share_card_image_url = Column(String(500), nullable=True, comment="생성된 영장 카드 이미지 URL")
    share_link_url = Column(String(255), nullable=True, comment="웹 결과 공유 링크 URL")

    created_at = Column(DateTime, default=utcnow, nullable=False)

    # 관계 정의
    appointment = relationship("Appointment", back_populates="warrants")
    defendant = relationship("Participant")
