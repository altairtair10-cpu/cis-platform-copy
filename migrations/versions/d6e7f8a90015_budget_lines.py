"""Budget lines reference with yearly limits

Revision ID: d6e7f8a90015
Revises: c5d6e7f80014
Create Date: 2026-07-12
"""
from alembic import op
import sqlalchemy as sa

revision = 'd6e7f8a90015'
down_revision = 'c5d6e7f80014'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'budget_lines',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(length=128), nullable=False, unique=True),
        sa.Column('yearly_limit', sa.Numeric(14, 2), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
    )
    op.add_column('documents',
                  sa.Column('budget_line_id', sa.Integer(),
                            sa.ForeignKey('budget_lines.id'), nullable=True))
    op.create_index('ix_documents_budget_line_id', 'documents', ['budget_line_id'])


def downgrade():
    op.drop_index('ix_documents_budget_line_id', table_name='documents')
    op.drop_column('documents', 'budget_line_id')
    op.drop_table('budget_lines')
