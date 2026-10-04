import sqlite3

import pytest
from alembic import command
from alembic.config import Config

from app.core.config import settings

# host_id / is_arrived / left_at 컬럼이 추가되기 직전 리비전
BEFORE_NEW_COLUMNS = "a752a1988286"


@pytest.fixture
def alembic_config(tmp_path, monkeypatch):
    db_path = tmp_path / "migration.db"
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    return Config("alembic.ini"), db_path


def test_migrations_upgrade_downgrade_and_match_models(alembic_config):
    config, _ = alembic_config

    command.upgrade(config, "head")
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    command.check(config)  # 모델과 마이그레이션 결과가 다르면 예외 발생


def test_upgrade_with_existing_data_backfills_new_columns(alembic_config):
    # 기존 데이터가 있는 DB에서도 NOT NULL 컬럼 추가가 실패하지 않고, 새 컬럼이 보정되어야 함
    config, db_path = alembic_config
    command.upgrade(config, BEFORE_NEW_COLUMNS)

    with sqlite3.connect(db_path) as conn:
        conn.executescript("""
            INSERT INTO users (guest_uuid, nickname, profile_character, location_terms_agreed,
                               notification_allowed, created_at, updated_at)
            VALUES ('host', '지민', 'char_rabbit', 1, 1, '2026-01-01', '2026-01-01'),
                   ('u2', '민수', 'char_rabbit', 1, 1, '2026-01-01', '2026-01-01');
            INSERT INTO appointments (title, target_place_name, target_latitude, target_longitude, meet_at,
                                      radar_start_type, radar_start_at, penalty_type, fine_per_minute,
                                      invite_code, status, created_at, updated_at)
            VALUES ('t', 'p', 37, 127, '2027-01-01', '30M_BEFORE', '2027-01-01', 'PENALTY', 0,
                    'AAA111', 'SCHEDULED', '2026-01-01', '2026-01-01');
            INSERT INTO participants (user_id, appointment_id, nickname, is_host, is_ready, join_status,
                                      arrival_status, arrived_at, final_late_minutes, final_fine_amount,
                                      created_at, updated_at)
            VALUES (1, 1, '지민', 1, 1, 'JOINED', 'EARLY', '2026-12-31 23:55:00', 0, 0, '2026-01-01', '2026-01-01'),
                   (2, 1, '민수', 0, 1, 'JOINED', 'NOT_ARRIVED', NULL, 0, 0, '2026-01-01', '2026-01-01');
        """)

    command.upgrade(config, "head")

    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT host_id FROM appointments").fetchone() == (1,)
        assert conn.execute("SELECT user_id, is_arrived FROM participants ORDER BY id").fetchall() == [(1, 1), (2, 0)]
