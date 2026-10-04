import json
import logging

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api.deps import GUEST_UUID_HEADER
from app.core.database import get_session_factory
from app.core.exceptions import AppException, ErrorCode
from app.core.websocket_manager import manager
from app.services import realtime_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/appointments/{appointment_id}")
async def appointment_websocket_endpoint(
    websocket: WebSocket,
    appointment_id: int,
    participant_id: int = Query(..., description="참가자 식별자 ID"),
    guest_uuid: str | None = Query(None, alias="guestUuid", description=f"기기 UUID ({GUEST_UUID_HEADER} 헤더로도 전달 가능)"),
    session_factory: async_sessionmaker = Depends(get_session_factory),
):
    """
    [WS-01 ~ WS-06] 약속 실시간 위치 공유, 찌르기, 체크인 웹소켓 엔드포인트

    메시지 형식: {"type": "<이벤트명>", ...명세 payload}
    처리 중 오류는 {"type": "error", "code": "...", "message": "..."}로 응답하고 연결은 유지
    """
    guest_uuid = guest_uuid or websocket.headers.get(GUEST_UUID_HEADER)
    async with session_factory() as db:
        try:
            await realtime_service.authorize_connection(db, appointment_id, participant_id, guest_uuid)
        except AppException as exc:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason=exc.code)
            return

    # 같은 참가자가 다시 연결하면 이전 연결은 닫음
    previous = manager.active_connections.get(appointment_id, {}).get(participant_id)
    await manager.connect(appointment_id, participant_id, websocket)
    if previous is not None:
        try:
            await previous.close()
        except Exception:
            pass

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json(
                    realtime_service.error_event(AppException(ErrorCode.INVALID_INPUT, "JSON 형식이 아닙니다."))
                )
                continue

            async with session_factory() as db:
                try:
                    await realtime_service.dispatch(db, appointment_id, participant_id, message)
                except AppException as exc:
                    await websocket.send_json(realtime_service.error_event(exc))
    except WebSocketDisconnect:
        pass
    finally:
        # 재연결로 교체된 경우 새 연결을 지우지 않도록 본인 연결일 때만 해제
        if manager.active_connections.get(appointment_id, {}).get(participant_id) is websocket:
            manager.disconnect(appointment_id, participant_id)
