"""add delivery landmark/unverified flag and saved customer delivery address

Revision ID: b2f6a1c9d4e7
Revises: 9c1a2e4f7b3d
Create Date: 2026-08-03 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2f6a1c9d4e7'
down_revision: Union[str, None] = '9c1a2e4f7b3d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('orders', sa.Column('delivery_landmark', sa.String(length=200), nullable=True))
    op.add_column('orders', sa.Column('delivery_unverified', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('customer_profiles', sa.Column('last_delivery_address', sa.String(length=300), nullable=True))
    op.add_column('customer_profiles', sa.Column('last_delivery_lat', sa.Float(), nullable=True))
    op.add_column('customer_profiles', sa.Column('last_delivery_lon', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('customer_profiles', 'last_delivery_lon')
    op.drop_column('customer_profiles', 'last_delivery_lat')
    op.drop_column('customer_profiles', 'last_delivery_address')
    op.drop_column('orders', 'delivery_unverified')
    op.drop_column('orders', 'delivery_landmark')
