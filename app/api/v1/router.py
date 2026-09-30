from fastapi import APIRouter
from app.api.v1.endpoints import users, appointments, places, settlement, websocket

api_router = APIRouter()

api_router.include_router(users.router, prefix="/users", tags=["Users (온보딩)"])
api_router.include_router(places.router, prefix="/places", tags=["Places (장소 검색)"])
api_router.include_router(appointments.router, prefix="/appointments", tags=["Appointments (약속)"])
api_router.include_router(settlement.router, prefix="/appointments", tags=["Settlement (정산 및 영장)"])
api_router.include_router(websocket.router, tags=["WebSocket (실시간 지도/찌르기/체크인)"])
