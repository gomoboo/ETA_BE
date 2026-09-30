from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from app.core.database import Base

class PokeLog(Base):
    """
    [WS-03 ~ WS-05] 미출발 참가자 찌르기(Poke) 송수신 및 응답 이력 엔티티
    """
    __tablename__ = "poke_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, comment="찌르기 로그 PK")
    appointment_id = Column(Integer, ForeignKey("appointments.id", ondelete="CASCADE"), nullable=False, comment="약속 FK")
    sender_participant_id = Column(Integer, ForeignKey("participants.id", ondelete="CASCADE"), nullable=False, comment="찌른 사람 FK")
    target_participant_id = Column(Integer, ForeignKey("participants.id", ondelete="CASCADE"), nullable=False, comment="찔린 사람 FK")

    response_action = Column(String(30), nullable=True, comment="응답 액션 (NOW_DEPARTING, DISMISSED, NO_RESPONSE)")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, comment="찌르기 전송 일시")
    responded_at = Column(DateTime, nullable=True, comment="응답 일시")
