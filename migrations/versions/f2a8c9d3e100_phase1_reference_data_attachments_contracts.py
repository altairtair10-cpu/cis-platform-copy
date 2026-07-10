"""Phase 1: reference data admin, document attachments, real contracts model

Revision ID: f2a8c9d3e100
Revises: a1c0f0d0e001
Create Date: 2026-07-10
"""
from alembic import op
import sqlalchemy as sa

revision = 'f2a8c9d3e100'
down_revision = 'a1c0f0d0e001'
branch_labels = None
depends_on = None


def upgrade():
    # 1. reference data (admin-managed lists)
    op.create_table(
        'equipment_types',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(length=64), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.true()),
        sa.UniqueConstraint('name', name='uq_equipment_types_name'),
    )
    op.create_table(
        'reference_departments',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(length=64), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.true()),
        sa.UniqueConstraint('name', name='uq_reference_departments_name'),
    )

    # 2. document attachments
    op.create_table(
        'document_attachments',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('document_id', sa.Integer(), sa.ForeignKey('documents.id'), nullable=False),
        sa.Column('original_filename', sa.String(length=256), nullable=False),
        sa.Column('stored_filename', sa.String(length=256), nullable=False),
        sa.Column('storage_backend', sa.String(length=16), nullable=False, server_default='local'),
        sa.Column('content_type', sa.String(length=128), nullable=True),
        sa.Column('size_bytes', sa.Integer(), nullable=True),
        sa.Column('uploaded_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('uploaded_at', sa.DateTime(), nullable=True),
    )

    # 3. contracts (replacing the hardcoded dict in the contracts blueprint)
    op.create_table(
        'contracts',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('client', sa.String(length=128), nullable=False),
        sa.Column('period', sa.String(length=128), nullable=False),
        sa.Column('updated_at', sa.Date(), nullable=True),
    )
    op.create_table(
        'contract_summary_rows',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('contract_id', sa.Integer(), sa.ForeignKey('contracts.id'), nullable=False),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('plan_year', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('plan_q', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('fact_q', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('unit', sa.String(length=32), nullable=True),
        sa.Column('color', sa.String(length=16), nullable=False, server_default='blue'),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
    )
    op.create_table(
        'contract_detail_groups',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('contract_id', sa.Integer(), sa.ForeignKey('contracts.id'), nullable=False),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
    )
    op.create_table(
        'contract_detail_rows',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('group_id', sa.Integer(), sa.ForeignKey('contract_detail_groups.id'), nullable=False),
        sa.Column('name', sa.String(length=256), nullable=False),
        sa.Column('contract_qty', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('done', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('remainder', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
    )

    # 4. seed data so nothing on-screen changes for users after this migration —
    #    the contracts page keeps showing the exact same numbers it always has,
    #    just from the database now instead of a hardcoded dict.
    bind = op.get_bind()

    bind.execute(sa.text(
        "INSERT INTO contracts (client, period, updated_at) "
        "VALUES ('ЭМГ', 'Q1 2026 · Январь — Март', '2026-04-15')"
    ))
    contract_id = bind.execute(sa.text("SELECT id FROM contracts WHERE client = 'ЭМГ'")).scalar()

    summary = [
        ('ГРП (всего)', 131, 51, 23, 'скв.', 'red', 0),
        ('ОГРП', 37, 18, 12, 'скв.', 'amber', 1),
        ('Малотонн. ГРП', 60, 30, 9, 'скв.', 'red', 2),
        ('МГРП', 9, 3, 2, 'скв.', 'amber', 3),
        ('ПЗР к ОГРП', 37, 16, 10, 'скв.', 'blue', 4),
        ('Освоение после ОГРП', 37, 16, 9, 'скв.', 'blue', 5),
    ]
    for name, plan_year, plan_q, fact_q, unit, color, order in summary:
        bind.execute(sa.text(
            "INSERT INTO contract_summary_rows "
            "(contract_id, name, plan_year, plan_q, fact_q, unit, color, sort_order) "
            "VALUES (:cid, :name, :py, :pq, :fq, :unit, :color, :order)"
        ), {'cid': contract_id, 'name': name, 'py': plan_year, 'pq': plan_q,
            'fq': fact_q, 'unit': unit, 'color': color, 'order': order})

    detail = [
        ('ОГРП', 0, [
            ('ЭМГ ОГРП', 30, 9),
            ('С.Нуржанов, Досмухамбетова, ЮВН Подкарниз', 18, 4),
            ('Западная Прорва, Актобе', 6, 2),
            ('ЮВН Подкарниз', 3, 3),
            ('ЮВН Надкарниз, С.Балгымбаева, Акуудук', 3, 0),
        ]),
        ('Малотонн. ГРП / МГРП', 1, [
            ('Малотонн. ГРП', 40, 9),
            ('МГРП', 8, 1),
            ('МГРП КТМ', 1, 1),
            ('ППК', 1, 1),
        ]),
    ]
    for group_name, group_order, rows in detail:
        bind.execute(sa.text(
            "INSERT INTO contract_detail_groups (contract_id, name, sort_order) "
            "VALUES (:cid, :name, :order)"
        ), {'cid': contract_id, 'name': group_name, 'order': group_order})
        group_id = bind.execute(sa.text(
            "SELECT id FROM contract_detail_groups WHERE contract_id = :cid AND name = :name"
        ), {'cid': contract_id, 'name': group_name}).scalar()
        for i, (name, qty, done) in enumerate(rows):
            bind.execute(sa.text(
                "INSERT INTO contract_detail_rows "
                "(group_id, name, contract_qty, done, remainder, sort_order) "
                "VALUES (:gid, :name, :qty, :done, :remainder, :order)"
            ), {'gid': group_id, 'name': name, 'qty': qty, 'done': done,
                'remainder': done - qty, 'order': i})

    # 5. seed initial equipment types from whatever's already in use, so the
    #    admin panel starts populated instead of empty.
    existing_types = bind.execute(sa.text(
        "SELECT DISTINCT eq_type FROM equipment WHERE eq_type IS NOT NULL AND eq_type != ''"
    )).fetchall()
    for (name,) in existing_types:
        bind.execute(sa.text(
            "INSERT INTO equipment_types (name, is_active) VALUES (:name, 1)"
        ), {'name': name})


def downgrade():
    op.drop_table('contract_detail_rows')
    op.drop_table('contract_detail_groups')
    op.drop_table('contract_summary_rows')
    op.drop_table('contracts')
    op.drop_table('document_attachments')
    op.drop_table('reference_departments')
    op.drop_table('equipment_types')