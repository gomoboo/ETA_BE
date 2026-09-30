from fastapi import WebSocket
from typing import Dict, Any

class AppointmentConnectionManager:
    """
    약속(appointment_id)별 참가자(participant_id) 소켓 연결 관리자
    """
    def __init__(self):
        # 구조: { appointment_id: { participant_id: WebSocket } }
        self.active_connections: Dict[int, Dict[int, WebSocket]] = {}

    async def connect(self, appointment_id: int, participant_id: int, websocket: WebSocket):
        await websocket.accept()
        if appointment_id not in self.active_connections:
            self.active_connections[appointment_id] = {}
        self.active_connections[appointment_id][participant_id] = websocket

    def disconnect(self, appointment_id: int, participant_id: int):
        if appointment_id in self.active_connections:
            self.active_connections[appointment_id].pop(participant_id, None)
            if not self.active_connections[appointment_id]:
                del self.active_connections[appointment_id]

    async def broadcast_to_appointment(self, appointment_id: int, message: Dict[str, Any]):
        """해당 약속에 참여 중인 모든 참가자에게 메시지 브로드캐스트 (예: map:sync)"""
        if appointment_id in self.active_connections:
            for participant_id, connection in list(self.active_connections[appointment_id].items()):
                try:
                    await connection.send_json(message)
                except Exception:
                    self.disconnect(appointment_id, participant_id)

    async def send_to_participant(self, appointment_id: int, participant_id: int, message: Dict[str, Any]):
        """특정 참가자에게 1:1 메시지 전송 (예: poke:received)"""
        if appointment_id in self.active_connections:
            websocket = self.active_connections[appointment_id].get(participant_id)
            if websocket:
                await websocket.send_json(message)

manager = AppointmentConnectionManager()
