import asyncio
import sqlite3
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.models  # noqa: F401  모델을 Base.metadata에 등록
from app.core.database import Base, get_db
from app.main import app
from tests.helpers import auth, future_iso


class Database:
    """테스트에서 DB 상태를 직접 조작/검증하기 위한 동기 sqlite3 헬퍼"""

    def __init__(self, path):
        self.path = path

    def execute(self, sql: str, *params) -> None:
        with sqlite3.connect(self.path) as conn:
            conn.execute(sql, params)

    def fetchone(self, sql: str, *params):
        with sqlite3.connect(self.path) as conn:
            return conn.execute(sql, params).fetchone()

    def scalar(self, sql: str, *params):
        row = self.fetchone(sql, *params)
        return row[0] if row else None


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "test.db"


@pytest.fixture
def db(db_path) -> Database:
    return Database(db_path)


@pytest.fixture
def client(db_path):
    """테스트마다 새 SQLite DB를 만들고 get_db 의존성을 교체한 TestClient"""
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", poolclass=NullPool)

    async def create_tables():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(create_tables())
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.pop(get_db, None)
    asyncio.run(engine.dispose())


@pytest.fixture
def onboard(client):
    def _onboard(guest_uuid: str, nickname: str = "지민", **fields) -> dict:
        response = client.post(
            "/api/v1/users/onboarding",
            json={"guestUuid": guest_uuid, "nickname": nickname, **fields},
        )
        assert response.status_code == 200, response.json()
        return response.json()["data"]

    return _onboard


@pytest.fixture
def create_appointment(client):
    def _create(host_uuid: str, **fields) -> dict:
        body = {
            "title": "강남역 맛집 탐방",
            "targetPlaceName": "스타벅스 강남역점",
            "targetAddress": "서울 강남구 강남대로 396",
            "targetLatitude": 37.497952,
            "targetLongitude": 127.027619,
            "meetAt": future_iso(),
            "radarStartType": "30M_BEFORE",
            "penaltyType": "PENALTY",
            "penaltyContent": "커피 쏘기",
            "finePerMinute": 0,
            **fields,
        }
        response = client.post("/api/v1/appointments", json=body, headers=auth(host_uuid))
        assert response.status_code == 200, response.json()
        return response.json()["data"]

    return _create


@pytest.fixture
def join(client):
    def _join(guest_uuid: str, invite_code: str, **body):
        return client.post(
            f"/api/v1/appointments/invite/{invite_code}/join", json=body, headers=auth(guest_uuid)
        )

    return _join
