"""Counterparty directory + link on documents

Revision ID: a3b4c5d60012
Revises: f2a3b4c50011
Create Date: 2026-07-11
"""
from alembic import op
import sqlalchemy as sa

revision = 'a3b4c5d60012'
down_revision = 'f2a3b4c50011'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'counterparties',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(length=256), nullable=False, unique=True),
        sa.Column('bin', sa.String(length=32), nullable=True),
        sa.Column('address', sa.String(length=256), nullable=True),
        sa.Column('phone', sa.String(length=64), nullable=True),
        sa.Column('email', sa.String(length=128), nullable=True),
        sa.Column('contact_person', sa.String(length=128), nullable=True),
        sa.Column('materials', sa.String(length=256), nullable=True),
        sa.Column('currency', sa.String(length=8), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )
    with op.batch_alter_table('documents') as batch:
        batch.add_column(sa.Column('counterparty_id', sa.Integer(), nullable=True))
        batch.create_foreign_key('fk_documents_counterparty', 'counterparties',
                                 ['counterparty_id'], ['id'])
    # наполняем справочник уникальными контрагентами из уже созданных ПО
    bind = op.get_bind()
    rows = bind.execute(sa.text(
        "SELECT DISTINCT justification FROM documents "
        "WHERE doc_type IN ('po_services', 'po_trebovanie') AND justification IS NOT NULL"
    )).fetchall()
    seen = set()
    for (just,) in rows:
        for line in (just or '').split('\n'):
            if line.startswith('Контрагент: '):
                name = line.split(': ', 1)[1].strip()
                if name and name not in seen:
                    seen.add(name)
                    bind.execute(sa.text(
                        "INSERT INTO counterparties (name, is_active) VALUES (:n, TRUE)"),
                        {'n': name[:256]})


def downgrade():
    with op.batch_alter_table('documents') as batch:
        batch.drop_constraint('fk_documents_counterparty', type_='foreignkey')
        batch.drop_column('counterparty_id')
    op.drop_table('counterparties')
