"""add_none_penalty_type_comment

Revision ID: bd1989a2899a
Revises: 4cc6dd0a1c3a
Create Date: 2026-11-24 11:47:10.719083

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bd1989a2899a'
down_revision: Union[str, Sequence[str], None] = '4cc6dd0a1c3a'
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
    """PenaltyType.NONE 추가에 맞춰 penalty_type 컬럼 주석 갱신"""
    _set_penalty_type_comment("벌칙 유형 (NONE/PENALTY/FEE)", "벌칙 유형 (PENALTY/FEE)")


def downgrade() -> None:
    _set_penalty_type_comment("벌칙 유형 (PENALTY/FEE)", "벌칙 유형 (NONE/PENALTY/FEE)")
