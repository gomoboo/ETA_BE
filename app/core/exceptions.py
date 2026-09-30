from enum import Enum
from typing import Optional


class ErrorCode(Enum):
    """표준 에러 코드 정의 (HTTP 상태 코드, 기본 메시지)"""

    # 공통 (Common)
    INVALID_INPUT = (400, "요청 값이 올바르지 않습니다.")
    UNAUTHORIZED = (401, "인증이 필요합니다.")
    FORBIDDEN = (403, "접근 권한이 없습니다.")
    NOT_FOUND = (404, "요청한 리소스를 찾을 수 없습니다.")
    METHOD_NOT_ALLOWED = (405, "허용되지 않은 요청 메서드입니다.")
    CONFLICT = (409, "요청이 현재 리소스 상태와 충돌합니다.")
    INTERNAL_SERVER_ERROR = (500, "서버 내부 오류가 발생했습니다.")

    # 사용자 (Users)
    INVALID_NICKNAME_LENGTH = (400, "닉네임은 2~10자로 입력해주세요.")
    USER_NOT_FOUND = (404, "등록되지 않은 사용자입니다.")

    # 약속 (Appointments)
    APPOINTMENT_NOT_FOUND = (404, "존재하지 않는 약속입니다.")
    INVITE_CODE_NOT_FOUND = (404, "유효하지 않은 초대 코드입니다.")
    INVITE_LINK_EXPIRED = (410, "만료된 초대 링크입니다.")
    ALREADY_JOINED = (409, "이미 참여 중인 약속입니다.")
    NOT_PARTICIPANT = (403, "해당 약속의 참가자가 아닙니다.")
    APPOINTMENT_ALREADY_ENDED = (409, "이미 종료되었거나 취소된 약속입니다.")

    # 정산 (Settlement)
    SETTLEMENT_NOT_READY = (409, "아직 정산할 수 없는 약속입니다.")
    WARRANT_NOT_FOUND = (404, "발부된 체포 영장이 없습니다.")

    # 외부 API (External)
    KAKAO_API_ERROR = (502, "장소 검색 서비스에 일시적인 문제가 발생했습니다.")

    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message


class AppException(Exception):
    """비즈니스 로직에서 발생시키는 커스텀 예외"""

    def __init__(self, error_code: ErrorCode, message: Optional[str] = None):
        self.error_code = error_code
        self.status_code = error_code.status_code
        self.code = error_code.name
        self.message = message or error_code.message
        super().__init__(self.message)
