from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'eab94ab99aff'
down_revision: Union[str, None] = '78effbd927c7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('reservations', sa.Column('payment_status', sa.String(length=20), nullable=False, server_default='pending'))
    op.add_column('orders', sa.Column('payment_status', sa.String(length=20), nullable=False, server_default='pending'))
    op.add_column('orders', sa.Column('fulfillment', sa.String(length=20), nullable=True))
    op.add_column('orders', sa.Column('delivery_address', sa.String(length=300), nullable=True))
    op.add_column('orders', sa.Column('guest_name', sa.String(length=120), nullable=True))
    op.add_column('orders', sa.Column('guest_phone', sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column('orders', 'guest_phone')
    op.drop_column('orders', 'guest_name')
    op.drop_column('orders', 'delivery_address')
    op.drop_column('orders', 'fulfillment')
    op.drop_column('orders', 'payment_status')
    op.drop_column('reservations', 'payment_status')
