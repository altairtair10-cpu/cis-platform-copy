"""ТО parts per equipment

Revision ID: b4c5d6e70013
Revises: a3b4c5d60012
Create Date: 2026-07-11
"""
from alembic import op
import sqlalchemy as sa

revision = 'b4c5d6e70013'
down_revision = 'a3b4c5d60012'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'to_parts',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('equipment_id', sa.Integer(), sa.ForeignKey('equipment.id'), nullable=False),
        sa.Column('name', sa.String(length=256), nullable=False),
        sa.Column('qty', sa.Float(), nullable=True),
        sa.Column('unit', sa.String(length=32), nullable=True),
        sa.Column('note', sa.String(length=256), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_to_parts_equipment_id', 'to_parts', ['equipment_id'])


def downgrade():
    op.drop_index('ix_to_parts_equipment_id', table_name='to_parts')
    op.drop_table('to_parts')
