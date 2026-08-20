"""replace menu_items with products

The app is being repurposed from a cafe menu-browsing assistant into
Leafly, a tea-catalog assistant. menu_items (veg/vegan/gluten-free/
spice_level fields) no longer fits the domain, so it's replaced with a
products table (origin/tea_type/caffeine_level/size_options/badge/
is_hamper) - see app.models.product.Product.

Revision ID: a1b2c3d4e5f6
Revises: d4e6f8a0b2c4
Create Date: 2026-08-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'd4e6f8a0b2c4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table('menu_items')

    op.create_table('products',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('description', sa.String(length=500), nullable=True),
    sa.Column('price', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('compare_at_price', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('origin', sa.String(length=50), nullable=True),
    sa.Column('tea_type', sa.String(length=20), nullable=True),
    sa.Column('caffeine_level', sa.String(length=10), nullable=True),
    sa.Column('size_options', sa.JSON(), nullable=False),
    sa.Column('badge', sa.String(length=20), nullable=True),
    sa.Column('is_hamper', sa.Boolean(), nullable=False),
    sa.Column('hamper_contents', sa.JSON(), nullable=False),
    sa.Column('tags', sa.JSON(), nullable=False),
    sa.Column('image_url', sa.String(length=300), nullable=True),
    sa.Column('available', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('products')

    op.create_table('menu_items',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('description', sa.String(length=500), nullable=True),
    sa.Column('price', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('category', sa.String(length=50), nullable=False),
    sa.Column('is_veg', sa.Boolean(), nullable=False),
    sa.Column('is_vegan', sa.Boolean(), nullable=False),
    sa.Column('is_gluten_free', sa.Boolean(), nullable=False),
    sa.Column('spice_level', sa.Integer(), nullable=False),
    sa.Column('tags', sa.JSON(), nullable=False),
    sa.Column('image_url', sa.String(length=300), nullable=True),
    sa.Column('available', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
