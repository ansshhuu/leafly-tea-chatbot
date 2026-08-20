from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'fa75a0edd0a2'
down_revision: Union[str, None] = '7ef96c7ee8a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('customer_profiles',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('phone', sa.String(length=20), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=True),
    sa.Column('loyalty_points', sa.Integer(), nullable=False),
    sa.Column('dietary_preference', sa.String(length=30), nullable=True),
    sa.Column('preferred_seating', sa.String(length=60), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_customer_profiles_phone'), 'customer_profiles', ['phone'], unique=True)
    op.create_table('feedback',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('session_id', sa.String(length=64), nullable=False),
    sa.Column('guest_phone', sa.String(length=20), nullable=True),
    sa.Column('feedback_text', sa.Text(), nullable=False),
    sa.Column('sentiment', sa.String(length=20), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_feedback_session_id'), 'feedback', ['session_id'], unique=False)
    op.add_column('orders', sa.Column('upsell_shown', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('orders', sa.Column('coupon_code', sa.String(length=20), nullable=True))
    op.add_column(
        'orders', sa.Column('discount_amount', sa.Numeric(precision=10, scale=2), nullable=False, server_default='0')
    )


def downgrade() -> None:
    op.drop_column('orders', 'discount_amount')
    op.drop_column('orders', 'coupon_code')
    op.drop_column('orders', 'upsell_shown')
    op.drop_index(op.f('ix_feedback_session_id'), table_name='feedback')
    op.drop_table('feedback')
    op.drop_index(op.f('ix_customer_profiles_phone'), table_name='customer_profiles')
    op.drop_table('customer_profiles')
