"""PO payment cycle: paid_at timestamp

Revision ID: f2a3b4c50011
Revises: e1f2a3b40010
Create Date: 2026-07-11
"""
from alembic import op
import sqlalchemy as sa

revision = 'f2a3b4c50011'
down_revision = 'e1f2a3b40010'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('documents') as batch:
        batch.add_column(sa.Column('paid_at', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('documents') as batch:
        batch.drop_column('paid_at')
