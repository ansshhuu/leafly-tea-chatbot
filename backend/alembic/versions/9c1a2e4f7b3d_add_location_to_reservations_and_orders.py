from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '9c1a2e4f7b3d'
down_revision: Union[str, None] = '46038d18e7ba'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('reservations', sa.Column('location', sa.String(length=60), nullable=True))
    op.add_column('orders', sa.Column('location', sa.String(length=60), nullable=True))


def downgrade() -> None:
    op.drop_column('orders', 'location')
    op.drop_column('reservations', 'location')
