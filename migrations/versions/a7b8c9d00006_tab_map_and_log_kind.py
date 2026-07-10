"""Manual register tab mapping + kind on site maintenance logs

Revision ID: a7b8c9d00006
Revises: f6a7b8c90005
Create Date: 2026-07-10
"""
from alembic import op
import sqlalchemy as sa

revision = 'a7b8c9d00006'
down_revision = 'f6a7b8c90005'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'maintenance_tab_map',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('tab_title', sa.String(length=128), nullable=False, unique=True),
        sa.Column('equipment_id', sa.Integer(), sa.ForeignKey('equipment.id'), nullable=True),
        sa.Column('is_ignored', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    with op.batch_alter_table('maintenance_logs') as batch:
        batch.add_column(sa.Column('kind', sa.String(length=4), nullable=True))


def downgrade():
    with op.batch_alter_table('maintenance_logs') as batch:
        batch.drop_column('kind')
    op.drop_table('maintenance_tab_map')
