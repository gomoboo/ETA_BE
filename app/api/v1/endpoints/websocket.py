from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from app.core.websocket_manager import manager

router = APIRouter()

@router.websocket("/ws/appointments/{appointment_id}")
async def appointment_websocket_endpoint(
    websocket: WebSocket,
    appointment_id: int,
    participant_id: int = Query(..., description="참가자 식별자 ID")
):
    """
    [WS-01 ~ WS-06] 약속 실시간 위치 공유, 찌르기, 체크인 웹소켓 엔드포인트
    """
    await manager.connect(appointment_id, participant_id, websocket)
    try:
        while True:
            data = await websocket.receive_json()
            event_type = data.get("type")

            # 1. 위치 업데이트 수신 (WS-01 -> WS-02 브로드캐스트)
            if event_type == "location:update":
                # TODO: Redis GEO 캐시 업데이트 및 map:sync 브로드캐스트
                pass

            # 2. 찌르기 전송 수신 (WS-03 -> WS-04 개인 전송)
            elif event_type == "poke:send":
                target_id = data.get("targetParticipantId")
                if target_id:
                    # TODO: poke_received 메시지 구성 후 타겟에게 전송
                    pass

            # 3. 찌르기 응답 수신 (WS-05)
            elif event_type == "poke:respond":
                # TODO: 응답 상태 갱신 처리
                pass

    except WebSocketDisconnect:
        manager.disconnect(appointment_id, participant_id)
