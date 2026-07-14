"""Internal documents (Documentolog-style): recipients, body, case index

Revision ID: e7f8a9b00016
Revises: d6e7f8a90015
Create Date: 2026-07-14
"""
from alembic import op
import sqlalchemy as sa

revision = 'e7f8a9b00016'
down_revision = 'd6e7f8a90015'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('documents', sa.Column('body_html', sa.Text(), nullable=True))
    op.add_column('documents', sa.Column('doc_language', sa.String(length=8), nullable=True))
    op.add_column('documents', sa.Column('case_index', sa.String(length=64), nullable=True))
    op.add_column('documents',
                  sa.Column('in_reply_to_id', sa.Integer(),
                            sa.ForeignKey('documents.id'), nullable=True))
    op.add_column('documents', sa.Column('registered_at', sa.DateTime(), nullable=True))

    op.create_table(
        'document_recipients',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('document_id', sa.Integer(),
                  sa.ForeignKey('documents.id'), nullable=False),
        sa.Column('user_id', sa.Integer(),
                  sa.ForeignKey('users.id'), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=True),
        sa.Column('done_at', sa.DateTime(), nullable=True),
        sa.Column('note', sa.String(length=256), nullable=True),
    )
    op.create_index('ix_document_recipients_document_id',
                    'document_recipients', ['document_id'])
    op.create_index('ix_document_recipients_user_id',
                    'document_recipients', ['user_id'])


def downgrade():
    op.drop_index('ix_document_recipients_user_id', table_name='document_recipients')
    op.drop_index('ix_document_recipients_document_id', table_name='document_recipients')
    op.drop_table('document_recipients')
    op.drop_column('documents', 'registered_at')
    op.drop_column('documents', 'in_reply_to_id')
    op.drop_column('documents', 'case_index')
    op.drop_column('documents', 'doc_language')
    op.drop_column('documents', 'body_html')
