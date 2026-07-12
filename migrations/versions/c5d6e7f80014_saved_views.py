"""Saved registry views

Revision ID: c5d6e7f80014
Revises: b4c5d6e70013
Create Date: 2026-07-12
"""
from alembic import op
import sqlalchemy as sa

revision = 'c5d6e7f80014'
down_revision = 'b4c5d6e70013'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'saved_views',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('params', sa.Text(), nullable=False, server_default=''),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_saved_views_user_id', 'saved_views', ['user_id'])


def downgrade():
    op.drop_index('ix_saved_views_user_id', table_name='saved_views')
    op.drop_table('saved_views')
