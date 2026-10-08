import sqlite3

import pytest
from alembic import command
from alembic.config import Config

from app.core.config import settings

# host_id / is_arrived / left_at 컬럼이 추가되기 직전 리비전
BEFORE_NEW_COLUMNS = "a752a1988286"
# 영장이 약속당 1장(UNIQUE appointment_id)이던 마지막 리비전
BEFORE_WARRANT_PER_LATE = "475aafd10212"

# BEFORE_NEW_COLUMNS 스키마 기준 약속 1개, 참가자 2명
SEED_SQL = """
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
"""

WARRANT_SQL = (
    "INSERT INTO warrants (appointment_id, defendant_participant_id, charge_title, late_minutes, "
    "judgment_text, final_penalty, total_fine_amount, created_at) "
    "VALUES (1, ?, 'c', ?, 'j', 'p', 0, '2026-01-01')"
)


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
        conn.executescript(SEED_SQL)

    command.upgrade(config, "head")

    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT host_id FROM appointments").fetchone() == (1,)
        assert conn.execute("SELECT user_id, is_arrived FROM participants ORDER BY id").fetchall() == [(1, 1), (2, 0)]


def test_warrant_per_late_participant_upgrade_and_downgrade(alembic_config):
    # 1:1 영장 데이터가 있는 DB에서 1:N으로 올리고, 되돌리면 최다 지각자 영장만 남아야 함
    config, db_path = alembic_config
    command.upgrade(config, BEFORE_NEW_COLUMNS)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(SEED_SQL)
    command.upgrade(config, BEFORE_WARRANT_PER_LATE)
    with sqlite3.connect(db_path) as conn:
        conn.execute(WARRANT_SQL, (2, 60))

    command.upgrade(config, "head")

    with sqlite3.connect(db_path) as conn:
        conn.execute(WARRANT_SQL, (1, 5))  # 같은 약속의 다른 지각자
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(WARRANT_SQL, (1, 5))  # 같은 지각자에게 두 번은 불가
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT count(*) FROM warrants").fetchone() == (2,)

    command.downgrade(config, BEFORE_WARRANT_PER_LATE)

    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT defendant_participant_id, late_minutes FROM warrants").fetchall() == [(2, 60)]
