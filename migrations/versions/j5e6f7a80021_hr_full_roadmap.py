"""HR full roadmap (phases 3-12): card fields, memo/request links, adaptation,
training, attestation, offboarding, KPI, talent reserve.

Idempotent by design: every add_column / create_table is guarded by an
inspector check, so `flask db upgrade` is safe whatever state the DB is in
(fresh, partially migrated, or already carrying some of these objects).

Revision ID: j5e6f7a80021
Revises: h3c4d5e60019
"""
from alembic import op
import sqlalchemy as sa


revision = 'j5e6f7a80021'
down_revision = 'h3c4d5e60019'
branch_labels = None
depends_on = None


def _insp():
    return sa.inspect(op.get_bind())


def _has_table(name):
    return name in _insp().get_table_names()


def _has_col(table, col):
    if not _has_table(table):
        return False
    return col in {c['name'] for c in _insp().get_columns(table)}


def upgrade():
    # ── новые колонки на существующих таблицах ───────────────────────────────
    if _has_table('documents'):
        if not _has_col('documents', 'sub_type'):
            op.add_column('documents',
                          sa.Column('sub_type', sa.String(length=32), nullable=True))
        if not _has_col('documents', 'related_employee_id'):
            op.add_column('documents',
                          sa.Column('related_employee_id', sa.Integer(), nullable=True))

    if _has_table('hr_order_details') and not _has_col('hr_order_details', 'source_document_id'):
        op.add_column('hr_order_details',
                      sa.Column('source_document_id', sa.Integer(), nullable=True))

    if _has_table('employees') and not _has_col('employees', 'in_talent_reserve'):
        op.add_column('employees',
                      sa.Column('in_talent_reserve', sa.Boolean(),
                                nullable=False, server_default=sa.text('false')))

    # ── новые таблицы (фазы 8-11) ────────────────────────────────────────────
    if not _has_table('adaptation_plans'):
        op.create_table(
            'adaptation_plans',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('employee_id', sa.Integer(),
                      sa.ForeignKey('employees.id'), nullable=False),
            sa.Column('mentor_id', sa.Integer(),
                      sa.ForeignKey('users.id'), nullable=True),
            sa.Column('start_date', sa.Date(), nullable=True),
            sa.Column('end_date', sa.Date(), nullable=True),
            sa.Column('status', sa.String(length=16), nullable=False,
                      server_default='active'),
            sa.Column('result_note', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
        )

    if not _has_table('adaptation_items'):
        op.create_table(
            'adaptation_items',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('plan_id', sa.Integer(),
                      sa.ForeignKey('adaptation_plans.id'), nullable=False),
            sa.Column('text', sa.String(length=256), nullable=False),
            sa.Column('due_date', sa.Date(), nullable=True),
            sa.Column('done', sa.Boolean(), nullable=False,
                      server_default=sa.text('false')),
            sa.Column('done_at', sa.DateTime(), nullable=True),
        )

    if not _has_table('training_records'):
        op.create_table(
            'training_records',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('employee_id', sa.Integer(),
                      sa.ForeignKey('employees.id'), nullable=False),
            sa.Column('course_name', sa.String(length=256), nullable=False),
            sa.Column('provider', sa.String(length=160), nullable=True),
            sa.Column('start_date', sa.Date(), nullable=True),
            sa.Column('end_date', sa.Date(), nullable=True),
            sa.Column('budget', sa.Integer(), nullable=True),
            sa.Column('status', sa.String(length=16), nullable=False,
                      server_default='requested'),
            sa.Column('cert_number', sa.String(length=64), nullable=True),
            sa.Column('cert_issued', sa.Date(), nullable=True),
            sa.Column('cert_expires', sa.Date(), nullable=True),
            sa.Column('effectiveness', sa.String(length=160), nullable=True),
            sa.Column('expiry_notified_at', sa.DateTime(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
        )

    if not _has_table('attestations'):
        op.create_table(
            'attestations',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('employee_id', sa.Integer(),
                      sa.ForeignKey('employees.id'), nullable=False),
            sa.Column('att_date', sa.Date(), nullable=True),
            sa.Column('commission', sa.Text(), nullable=True),
            sa.Column('protocol_number', sa.String(length=64), nullable=True),
            sa.Column('result', sa.String(length=32), nullable=True),
            sa.Column('recommendation', sa.Text(), nullable=True),
            sa.Column('recheck_date', sa.Date(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
        )

    if not _has_table('offboarding_items'):
        op.create_table(
            'offboarding_items',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('employee_id', sa.Integer(),
                      sa.ForeignKey('employees.id'), nullable=False),
            sa.Column('text', sa.String(length=256), nullable=False),
            sa.Column('done', sa.Boolean(), nullable=False,
                      server_default=sa.text('false')),
            sa.Column('done_at', sa.DateTime(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
        )

    if not _has_table('employee_kpis'):
        op.create_table(
            'employee_kpis',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('employee_id', sa.Integer(),
                      sa.ForeignKey('employees.id'), nullable=False),
            sa.Column('period', sa.String(length=32), nullable=True),
            sa.Column('metric', sa.String(length=160), nullable=False),
            sa.Column('value', sa.String(length=64), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
        )


def downgrade():
    for t in ('employee_kpis', 'offboarding_items', 'attestations',
              'training_records', 'adaptation_items', 'adaptation_plans'):
        if _has_table(t):
            op.drop_table(t)
    if _has_col('employees', 'in_talent_reserve'):
        op.drop_column('employees', 'in_talent_reserve')
    if _has_col('hr_order_details', 'source_document_id'):
        op.drop_column('hr_order_details', 'source_document_id')
    if _has_col('documents', 'related_employee_id'):
        op.drop_column('documents', 'related_employee_id')
    if _has_col('documents', 'sub_type'):
        op.drop_column('documents', 'sub_type')
