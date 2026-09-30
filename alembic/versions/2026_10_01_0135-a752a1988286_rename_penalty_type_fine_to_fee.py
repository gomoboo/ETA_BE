"""rename penalty type FINE to FEE

Revision ID: a752a1988286
Revises: 6a9223df1783
Create Date: 2026-10-01 01:35:16.147357

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a752a1988286'
down_revision: Union[str, Sequence[str], None] = '6a9223df1783'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _set_penalty_type_comment(comment: str, existing_comment: str) -> None:
    # SQLite는 컬럼 comment를 지원하지 않아 건너뜀
    if op.get_bind().dialect.name == "sqlite":
        return
    op.alter_column(
        "appointments",
        "penalty_type",
        existing_type=sa.String(length=20),
        existing_nullable=False,
        comment=comment,
        existing_comment=existing_comment,
    )


def upgrade() -> None:
    """지각비 모드 값을 API 명세에 맞춰 FINE -> FEE로 변경"""
    op.execute("UPDATE appointments SET penalty_type = 'FEE' WHERE penalty_type = 'FINE'")
    _set_penalty_type_comment("벌칙 유형 (PENALTY/FEE)", "벌칙 유형 (PENALTY/FINE)")


def downgrade() -> None:
    op.execute("UPDATE appointments SET penalty_type = 'FINE' WHERE penalty_type = 'FEE'")
    _set_penalty_type_comment("벌칙 유형 (PENALTY/FINE)", "벌칙 유형 (PENALTY/FEE)")
