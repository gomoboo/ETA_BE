"""backfill host_id and is_arrived

Revision ID: 475aafd10212
Revises: 42d5d0cf4ef1
Create Date: 2026-10-04 14:22:06.425961

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '475aafd10212'
down_revision: Union[str, Sequence[str], None] = '42d5d0cf4ef1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """42d5d0cf4ef1에서 추가된 컬럼을 기존 데이터 기준으로 채움"""
    # 방장 participant의 user_id를 host_id로
    op.execute(
        """
        UPDATE appointments
        SET host_id = (
            SELECT participants.user_id FROM participants
            WHERE participants.appointment_id = appointments.id AND participants.is_host = true
            ORDER BY participants.id
            LIMIT 1
        )
        WHERE host_id IS NULL
        """
    )
    # 도착 시각이 기록된 참가자는 도착 완료로
    op.execute("UPDATE participants SET is_arrived = true WHERE arrived_at IS NOT NULL AND is_arrived = false")


def downgrade() -> None:
    # 데이터 보정만 수행하므로 되돌릴 스키마 변경 없음
    pass
