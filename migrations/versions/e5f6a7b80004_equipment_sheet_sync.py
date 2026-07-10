"""Equipment sheet sync fields + document-equipment link

Revision ID: e5f6a7b80004
Revises: d4e5f6a70003
Create Date: 2026-07-10
"""
from alembic import op
import sqlalchemy as sa

revision = 'e5f6a7b80004'
down_revision = 'd4e5f6a70003'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('equipment') as batch:
        batch.add_column(sa.Column('gos_number', sa.String(length=32), nullable=True))
        batch.add_column(sa.Column('project', sa.String(length=64), nullable=True))
        batch.add_column(sa.Column('condition', sa.Text(), nullable=True))
        batch.add_column(sa.Column('sheet_status', sa.String(length=64), nullable=True))
        batch.add_column(sa.Column('synced_at', sa.DateTime(), nullable=True))
    with op.batch_alter_table('documents') as batch:
        batch.add_column(sa.Column('equipment_id', sa.Integer(), nullable=True))
        batch.create_foreign_key('fk_documents_equipment', 'equipment',
                                 ['equipment_id'], ['id'])


def downgrade():
    with op.batch_alter_table('documents') as batch:
        batch.drop_constraint('fk_documents_equipment', type_='foreignkey')
        batch.drop_column('equipment_id')
    with op.batch_alter_table('equipment') as batch:
        batch.drop_column('synced_at')
        batch.drop_column('sheet_status')
        batch.drop_column('condition')
        batch.drop_column('project')
        batch.drop_column('gos_number')
