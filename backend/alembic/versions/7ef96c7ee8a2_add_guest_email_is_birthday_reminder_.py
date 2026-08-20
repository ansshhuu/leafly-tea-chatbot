from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '7ef96c7ee8a2'
down_revision: Union[str, None] = 'eab94ab99aff'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('orders', sa.Column('guest_email', sa.String(length=255), nullable=True))
    op.add_column('orders', sa.Column('is_birthday', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('reservations', sa.Column('guest_email', sa.String(length=255), nullable=True))
    op.add_column('reservations', sa.Column('is_birthday', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('reservations', sa.Column('reminder_sent', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column('reservations', 'reminder_sent')
    op.drop_column('reservations', 'is_birthday')
    op.drop_column('reservations', 'guest_email')
    op.drop_column('orders', 'is_birthday')
    op.drop_column('orders', 'guest_email')
