"""Indexes for the growing document registry

Revision ID: d0e1f2a30009
Revises: c9d0e1f20008
Create Date: 2026-07-11
"""
from alembic import op

revision = 'd0e1f2a30009'
down_revision = 'c9d0e1f20008'
branch_labels = None
depends_on = None


def upgrade():
    op.create_index('ix_documents_doc_type', 'documents', ['doc_type'])
    op.create_index('ix_documents_status', 'documents', ['status'])
    op.create_index('ix_documents_created_at', 'documents', ['created_at'])
    op.create_index('ix_documents_author_id', 'documents', ['author_id'])
    op.create_index('ix_documents_type_status', 'documents', ['doc_type', 'status'])
    op.create_index('ix_document_items_document_id', 'document_items', ['document_id'])
    op.create_index('ix_document_approvals_document_id', 'document_approvals', ['document_id'])
    op.create_index('ix_document_approvals_approver_id', 'document_approvals', ['approver_id'])
    op.create_index('ix_notifications_user_id_is_read', 'notifications', ['user_id', 'is_read'])


def downgrade():
    for name, table in [
        ('ix_notifications_user_id_is_read', 'notifications'),
        ('ix_document_approvals_approver_id', 'document_approvals'),
        ('ix_document_approvals_document_id', 'document_approvals'),
        ('ix_document_items_document_id', 'document_items'),
        ('ix_documents_type_status', 'documents'),
        ('ix_documents_author_id', 'documents'),
        ('ix_documents_created_at', 'documents'),
        ('ix_documents_status', 'documents'),
        ('ix_documents_doc_type', 'documents'),
    ]:
        op.drop_index(name, table_name=table)
