from fastapi import APIRouter

router = APIRouter()

@router.get("/{appointment_id}/settlement")
async def get_settlement(appointment_id: int):
    """[API-09] 지각비 정산 결과 조회"""
    return {
        "success": True,
        "data": {
            "appointmentId": appointment_id,
            "title": "약속",
            "totalFineAmount": 0,
            "participants": []
        }
    }

@router.get("/{appointment_id}/warrant")
async def get_warrant(appointment_id: int):
    """[API-10] 지각 체포 영장 및 결과 카드 조회"""
    return {
        "success": True,
        "data": {
            "warrantId": 301,
            "defendantNickname": "지원",
            "chargeTitle": "침대 미출발 및 상습 지각죄",
            "lateMinutes": 18,
            "judgmentText": "약속 시간 18분 초과 및 5분간 미출발 검거",
            "finalPenalty": "오늘 전원 커피 쏘기",
            "shareCardImageUrl": "https://eta.app/cards/warrant_301.png",
            "shareLinkUrl": "https://eta.app/result/warrant/301"
        }
    }
