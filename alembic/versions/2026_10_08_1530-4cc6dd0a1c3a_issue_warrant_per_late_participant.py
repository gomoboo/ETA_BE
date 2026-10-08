"""issue warrant per late participant

Revision ID: 4cc6dd0a1c3a
Revises: 475aafd10212
Create Date: 2026-10-08 15:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = '4cc6dd0a1c3a'
down_revision: Union[str, Sequence[str], None] = '475aafd10212'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# 초기 마이그레이션의 이름 없는 UNIQUE(appointment_id)
# PostgreSQL은 자동으로 warrants_appointment_id_key라는 이름을 붙이고,
# SQLite는 이름이 없어서 batch 모드에서 naming_convention으로 이름을 붙여 찾음
SQLITE_NAMING_CONVENTION = {"uq": "uq_%(table_name)s_%(column_0_name)s"}


def _old_unique_name() -> str:
    if op.get_bind().dialect.name == "sqlite":
        return "uq_warrants_appointment_id"
    return "warrants_appointment_id_key"


def _batch():
    if op.get_bind().dialect.name == "sqlite":
        return op.batch_alter_table("warrants", naming_convention=SQLITE_NAMING_CONVENTION)
    return op.batch_alter_table("warrants")


def upgrade() -> None:
    """약속당 영장 1장(1:1) → 지각자당 영장 1장(1:N)"""
    with _batch() as batch_op:
        batch_op.drop_constraint(_old_unique_name(), type_="unique")
        batch_op.create_index(batch_op.f("ix_warrants_appointment_id"), ["appointment_id"], unique=False)
        batch_op.create_unique_constraint(
            "uq_warrants_appointment_defendant", ["appointment_id", "defendant_participant_id"]
        )
        batch_op.alter_column(
            "appointment_id", existing_type=sa.Integer(), existing_nullable=False,
            comment="대상 약속 FK (1:N, 지각자당 1장)", existing_comment="대상 약속 FK (1:1)",
        )


def downgrade() -> None:
    # 1:1로 되돌리기 전에 약속마다 최다 지각자의 영장 1장만 남김 (기존 발부 기준과 동일)
    op.execute(
        """
        DELETE FROM warrants
        WHERE id NOT IN (
            SELECT (
                SELECT w2.id FROM warrants w2
                WHERE w2.appointment_id = w.appointment_id
                ORDER BY w2.late_minutes DESC, w2.defendant_participant_id ASC, w2.id ASC
                LIMIT 1
            )
            FROM warrants w
            GROUP BY w.appointment_id
        )
        """
    )
    with _batch() as batch_op:
        batch_op.alter_column(
            "appointment_id", existing_type=sa.Integer(), existing_nullable=False,
            comment="대상 약속 FK (1:1)", existing_comment="대상 약속 FK (1:N, 지각자당 1장)",
        )
        batch_op.drop_constraint("uq_warrants_appointment_defendant", type_="unique")
        batch_op.drop_index(batch_op.f("ix_warrants_appointment_id"))
        batch_op.create_unique_constraint(_old_unique_name(), ["appointment_id"])
