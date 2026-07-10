"""Defect lifecycle: per-unit event codes, closing, requisition link

Revision ID: b8c9d0e10007
Revises: a7b8c9d00006
Create Date: 2026-07-11
"""
from alembic import op
import sqlalchemy as sa

revision = 'b8c9d0e10007'
down_revision = 'a7b8c9d00006'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('documents') as batch:
        batch.add_column(sa.Column('event_code', sa.String(length=64), nullable=True))
        batch.add_column(sa.Column('defect_closed', sa.Boolean(), nullable=False,
                                   server_default=sa.false()))
        batch.add_column(sa.Column('defect_closed_at', sa.DateTime(), nullable=True))
        batch.add_column(sa.Column('related_defect_id', sa.Integer(), nullable=True))
        batch.create_unique_constraint('uq_documents_event_code', ['event_code'])
        batch.create_foreign_key('fk_documents_related_defect', 'documents',
                                 ['related_defect_id'], ['id'])


def downgrade():
    with op.batch_alter_table('documents') as batch:
        batch.drop_constraint('fk_documents_related_defect', type_='foreignkey')
        batch.drop_constraint('uq_documents_event_code', type_='unique')
        batch.drop_column('related_defect_id')
        batch.drop_column('defect_closed_at')
        batch.drop_column('defect_closed')
        batch.drop_column('event_code')
