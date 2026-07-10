"""Phase 0 hardening: audit log, doc sequences, numeric money, must_change_password

Revision ID: a1c0f0d0e001
Revises: b7114853c997
Create Date: 2026-07-09
"""
from alembic import op
import sqlalchemy as sa

revision = 'a1c0f0d0e001'
down_revision = 'b7114853c997'
branch_labels = None
depends_on = None


def upgrade():
    # 1. forced password change flag
    op.add_column('users', sa.Column('must_change_password', sa.Boolean(),
                                     nullable=False, server_default=sa.false()))

    # 2. audit trail
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('action', sa.String(length=64), nullable=False),
        sa.Column('entity_type', sa.String(length=64), nullable=True),
        sa.Column('entity_id', sa.Integer(), nullable=True),
        sa.Column('details', sa.Text(), nullable=True),
        sa.Column('ip', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_audit_logs_action', 'audit_logs', ['action'])
    op.create_index('ix_audit_logs_created_at', 'audit_logs', ['created_at'])

    # 3. race-safe document numbering
    op.create_table(
        'document_sequences',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('doc_type', sa.String(length=32), nullable=False),
        sa.Column('year', sa.Integer(), nullable=False),
        sa.Column('counter', sa.Integer(), nullable=False, server_default='0'),
        sa.UniqueConstraint('doc_type', 'year', name='uq_docseq_type_year'),
    )
    # Backfill: old numbering used a global per-type count, so seeding the current
    # year's counter with the total per-type count guarantees no collisions.
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        bind.execute(sa.text(
            "INSERT INTO document_sequences (doc_type, year, counter) "
            "SELECT doc_type, EXTRACT(YEAR FROM NOW())::int, COUNT(*) "
            "FROM documents GROUP BY doc_type"
        ))
    else:  # sqlite (dev)
        bind.execute(sa.text(
            "INSERT INTO document_sequences (doc_type, year, counter) "
            "SELECT doc_type, CAST(strftime('%Y','now') AS INTEGER), COUNT(*) "
            "FROM documents GROUP BY doc_type"
        ))

    # 4. money as exact decimals
    with op.batch_alter_table('document_items') as batch:
        batch.alter_column('price', existing_type=sa.Float(),
                           type_=sa.Numeric(14, 2), existing_nullable=True)
    with op.batch_alter_table('maintenance_logs') as batch:
        batch.alter_column('cost', existing_type=sa.Float(),
                           type_=sa.Numeric(14, 2), existing_nullable=True)


def downgrade():
    with op.batch_alter_table('maintenance_logs') as batch:
        batch.alter_column('cost', existing_type=sa.Numeric(14, 2),
                           type_=sa.Float(), existing_nullable=True)
    with op.batch_alter_table('document_items') as batch:
        batch.alter_column('price', existing_type=sa.Numeric(14, 2),
                           type_=sa.Float(), existing_nullable=True)
    op.drop_table('document_sequences')
    op.drop_index('ix_audit_logs_created_at', table_name='audit_logs')
    op.drop_index('ix_audit_logs_action', table_name='audit_logs')
    op.drop_table('audit_logs')
    op.drop_column('users', 'must_change_password')
