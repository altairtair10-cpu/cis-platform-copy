"""Requisition workflow: route templates, ПО link, unified doc type

Revision ID: c9d0e1f20008
Revises: b8c9d0e10007
Create Date: 2026-07-11
"""
from alembic import op
import sqlalchemy as sa

revision = 'c9d0e1f20008'
down_revision = 'b8c9d0e10007'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'route_templates',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(length=128), nullable=False, unique=True),
        sa.Column('data', sa.Text(), nullable=False),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )
    with op.batch_alter_table('documents') as batch:
        batch.add_column(sa.Column('related_req_id', sa.Integer(), nullable=True))
        batch.create_foreign_key('fk_documents_related_req', 'documents',
                                 ['related_req_id'], ['id'])
    # unify: старые документы типа 'trebovanie' — это те же требования на материалы
    op.get_bind().execute(sa.text(
        "UPDATE documents SET doc_type = 'purchase_req' WHERE doc_type = 'trebovanie'"))


def downgrade():
    with op.batch_alter_table('documents') as batch:
        batch.drop_constraint('fk_documents_related_req', type_='foreignkey')
        batch.drop_column('related_req_id')
    op.drop_table('route_templates')
