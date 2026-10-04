from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
import enum
from app.core.database import Base

class AppointmentStatus(str, enum.Enum):
    SCHEDULED = "SCHEDULED"          # 약속 생성 후 레이더 시작 전 대기 상태
    RADAR_ACTIVE = "RADAR_ACTIVE"    # 레이더 시작 ~ 약속 진행 중 (위치 공유 활성)
    COMPLETED = "COMPLETED"          # 전원 도착 또는 정산 완료
    CANCELLED = "CANCELLED"          # 약속 취소

class RadarStartType(str, enum.Enum):
    M10_BEFORE = "10M_BEFORE"
    M20_BEFORE = "20M_BEFORE"
    M30_BEFORE = "30M_BEFORE"
    H1_BEFORE = "1H_BEFORE"
    CUSTOM = "CUSTOM"

class PenaltyType(str, enum.Enum):
    PENALTY = "PENALTY"  # 특정 벌칙 문구 (예: "커피 쏘기")
    FEE = "FEE"          # 분당 지각비 누적 (예: 분당 1,000원)

class Appointment(Base):
    """
    [API-04] 새 약속 생성 및 약속 정보 엔티티
    """
    __tablename__ = "appointments"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, comment="약속 고유 식별자 PK")
    host_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, comment="방장 유저 ID FK")
    title = Column(String(100), nullable=False, comment="약속 이름 (예: 강남역 맛집 탐방)")

    # 목적지 정보
    target_place_name = Column(String(150), nullable=False, comment="도착 장소명")
    target_address = Column(String(255), nullable=True, comment="도착 장소 도로명/지번 주소")
    target_latitude = Column(Float, nullable=False, comment="도착지 위도 (Latitude)")
    target_longitude = Column(Float, nullable=False, comment="도착지 경도 (Longitude)")

    # 약속 시간 및 레이더
    meet_at = Column(DateTime, nullable=False, comment="약속 일시 (UTC)")
    radar_start_type = Column(String(20), nullable=False, default="30M_BEFORE", comment="레이더 시작 시점 유형")
    custom_radar_minutes_before = Column(Integer, nullable=True, default=30, comment="CUSTOM 시 약속 N분 전 시작")
    radar_start_at = Column(DateTime, nullable=False, comment="계산된 실제 위치 공유(레이더) 시작 시각")

    # 벌칙 설정
    penalty_type = Column(String(20), nullable=False, default="PENALTY", comment="벌칙 유형 (PENALTY/FEE)")
    penalty_content = Column(String(150), nullable=True, comment="벌칙 내용 문구 (예: 오늘 커피 쏘기)")
    fine_per_minute = Column(Integer, nullable=False, default=0, comment="분당 지각 벌금 (원)")

    # 초대 및 상태
    invite_code = Column(String(12), unique=True, index=True, nullable=False, comment="6자리 초대 난수 코드 (예: ETA99K)")
    status = Column(String(20), nullable=False, default="SCHEDULED", comment="약속 상태 (SCHEDULED, RADAR_ACTIVE, COMPLETED, CANCELLED)")

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # 관계 정의
    participants = relationship("Participant", back_populates="appointment", cascade="all, delete-orphan")
    warrant = relationship("Warrant", back_populates="appointment", uselist=False, cascade="all, delete-orphan")
