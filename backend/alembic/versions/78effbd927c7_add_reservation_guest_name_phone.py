from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '78effbd927c7'
down_revision: Union[str, None] = 'b7049823d218'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('reservations', sa.Column('guest_name', sa.String(length=120), nullable=True))
    op.add_column('reservations', sa.Column('guest_phone', sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column('reservations', 'guest_phone')
    op.drop_column('reservations', 'guest_name')
