from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b7049823d218'
down_revision: Union[str, None] = 'f3a5c5567c77'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('escalations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('session_id', sa.String(length=64), nullable=False),
    sa.Column('message', sa.String(), nullable=False),
    sa.Column('sentiment', sa.String(length=20), nullable=False),
    sa.Column('resolved', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_escalations_session_id'), 'escalations', ['session_id'], unique=False)
    op.add_column('orders', sa.Column('session_id', sa.String(length=64), nullable=True))
    op.create_index(op.f('ix_orders_session_id'), 'orders', ['session_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_orders_session_id'), table_name='orders')
    op.drop_column('orders', 'session_id')
    op.drop_index(op.f('ix_escalations_session_id'), table_name='escalations')
    op.drop_table('escalations')
