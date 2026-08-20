"""remove reservation/order/checkout/loyalty/feedback tables and columns

Reservation and order/cart/checkout functionality (including loyalty,
customer profiles, and post-order feedback, which only existed to support
those flows) is being removed as part of repurposing this app into a
menu-browsing/recommendation assistant. Drops the now-unused tables
entirely, plus the reservation/checkout/feedback/addon-suggestion draft
columns that were living on chat_sessions.

Revision ID: d4e6f8a0b2c4
Revises: 5b8a6821bd20
Create Date: 2026-08-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4e6f8a0b2c4'
down_revision: Union[str, None] = '5b8a6821bd20'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column('chat_sessions', 'pending_addon_language')
    op.drop_column('chat_sessions', 'pending_addon_item_name')
    op.drop_column('chat_sessions', 'pending_addon_item_id')
    op.drop_column('chat_sessions', 'feedback_pending')
    op.drop_column('chat_sessions', 'checkout_draft')
    op.drop_column('chat_sessions', 'reservation_draft')

    op.drop_index(op.f('ix_feedback_session_id'), table_name='feedback')
    op.drop_table('feedback')

    op.drop_index(op.f('ix_customer_profiles_phone'), table_name='customer_profiles')
    op.drop_table('customer_profiles')

    op.drop_table('order_items')

    op.drop_index(op.f('ix_orders_session_id'), table_name='orders')
    op.drop_table('orders')

    op.drop_table('reservations')


def downgrade() -> None:
    op.create_table('reservations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('date', sa.Date(), nullable=False),
    sa.Column('time', sa.Time(), nullable=False),
    sa.Column('guests', sa.Integer(), nullable=False),
    sa.Column('special_requests', sa.String(length=500), nullable=True),
    sa.Column('status', sa.String(length=30), nullable=False),
    sa.Column('location', sa.String(length=60), nullable=True),
    sa.Column('guest_email', sa.String(length=255), nullable=True),
    sa.Column('is_birthday', sa.Boolean(), nullable=False, server_default=sa.false()),
    sa.Column('reminder_sent', sa.Boolean(), nullable=False, server_default=sa.false()),
    sa.Column('guest_name', sa.String(length=120), nullable=True),
    sa.Column('guest_phone', sa.String(length=20), nullable=True),
    sa.Column('payment_status', sa.String(length=20), nullable=False, server_default='pending'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )

    op.create_table('orders',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('status', sa.String(length=30), nullable=False),
    sa.Column('total_amount', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('tax_amount', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('session_id', sa.String(length=64), nullable=True),
    sa.Column('cart_reminder_sent', sa.Boolean(), nullable=False, server_default=sa.false()),
    sa.Column('upsell_shown', sa.Boolean(), nullable=False, server_default=sa.false()),
    sa.Column('coupon_code', sa.String(length=20), nullable=True),
    sa.Column('discount_amount', sa.Numeric(precision=10, scale=2), nullable=False, server_default='0'),
    sa.Column('location', sa.String(length=60), nullable=True),
    sa.Column('guest_email', sa.String(length=255), nullable=True),
    sa.Column('is_birthday', sa.Boolean(), nullable=False, server_default=sa.false()),
    sa.Column('payment_status', sa.String(length=20), nullable=False, server_default='pending'),
    sa.Column('fulfillment', sa.String(length=20), nullable=True),
    sa.Column('delivery_address', sa.String(length=300), nullable=True),
    sa.Column('guest_name', sa.String(length=120), nullable=True),
    sa.Column('guest_phone', sa.String(length=20), nullable=True),
    sa.Column('delivery_flat_number', sa.String(length=200), nullable=True),
    sa.Column('delivery_unverified', sa.Boolean(), nullable=False, server_default=sa.false()),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_orders_session_id'), 'orders', ['session_id'], unique=False)

    op.create_table('order_items',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('order_id', sa.Integer(), nullable=False),
    sa.Column('menu_item_id', sa.Integer(), nullable=False),
    sa.Column('quantity', sa.Integer(), nullable=False),
    sa.Column('price_at_order', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.ForeignKeyConstraint(['menu_item_id'], ['menu_items.id'], ),
    sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ),
    sa.PrimaryKeyConstraint('id')
    )

    op.create_table('customer_profiles',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('phone', sa.String(length=20), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=True),
    sa.Column('loyalty_points', sa.Integer(), nullable=False),
    sa.Column('dietary_preference', sa.String(length=30), nullable=True),
    sa.Column('preferred_seating', sa.String(length=60), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('last_delivery_address', sa.String(length=300), nullable=True),
    sa.Column('last_delivery_lat', sa.Float(), nullable=True),
    sa.Column('last_delivery_lon', sa.Float(), nullable=True),
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

    op.add_column('chat_sessions', sa.Column('reservation_draft', sa.JSON(), nullable=True))
    op.add_column('chat_sessions', sa.Column('checkout_draft', sa.JSON(), nullable=True))
    op.add_column('chat_sessions', sa.Column('feedback_pending', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('chat_sessions', sa.Column('pending_addon_item_id', sa.Integer(), nullable=True))
    op.add_column('chat_sessions', sa.Column('pending_addon_item_name', sa.String(length=120), nullable=True))
    op.add_column('chat_sessions', sa.Column('pending_addon_language', sa.String(length=10), nullable=True))
