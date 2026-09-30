from fastapi import APIRouter

router = APIRouter()

@router.get("/home")
async def get_home_appointments():
    """[API-02] 홈 화면 약속 목록 조회"""
    return {"success": True, "data": {"activeAppointments": [], "upcomingAppointments": []}}

@router.post("")
async def create_appointment():
    """[API-04] 새 약속 생성하기"""
    return {"success": True, "data": {"appointmentId": 12, "inviteCode": "ETA99K"}}

@router.get("/invite/{invite_code}")
async def preview_invite(invite_code: str):
    """[API-05] 초대 링크 정보 미리보기"""
    return {"success": True, "data": {"appointmentId": 12, "title": "약속"}}

@router.post("/invite/{invite_code}/join")
async def join_appointment(invite_code: str):
    """[API-06] 초대받은 약속 참여하기"""
    return {"success": True, "data": {"appointmentId": 12, "participantId": 45}}

@router.get("/{appointment_id}")
async def get_appointment_detail(appointment_id: int):
    """[API-07] 약속 대기 및 상세 화면 조회"""
    return {"success": True, "data": {"appointmentId": appointment_id}}

@router.post("/{appointment_id}/leave")
async def leave_appointment(appointment_id: int):
    """[API-08] 약속 나가기"""
    return {"success": True, "data": {"joinStatus": "LEFT"}}
