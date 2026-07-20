"""HR module phase 1: employees (единая карточка), HR orders (приказы),
acknowledgement recipients.

Revision ID: g2b3c4d50018
Revises: f1a2b3c40017
Create Date: 2026-07-20
"""
from alembic import op
import sqlalchemy as sa

revision = 'g2b3c4d50018'
down_revision = 'f1a2b3c40017'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'employees',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('full_name_ru', sa.String(length=160), nullable=False),
        sa.Column('full_name_kz', sa.String(length=160), nullable=True),
        sa.Column('iin', sa.String(length=12), nullable=True),
        sa.Column('position_ru', sa.String(length=160), nullable=True),
        sa.Column('position_kz', sa.String(length=160), nullable=True),
        sa.Column('department', sa.String(length=120), nullable=True),
        sa.Column('manager_id', sa.Integer(), sa.ForeignKey('employees.id'), nullable=True),
        sa.Column('hire_date', sa.Date(), nullable=True),
        sa.Column('contract_number', sa.String(length=64), nullable=True),
        sa.Column('contract_date', sa.Date(), nullable=True),
        sa.Column('contract_end', sa.Date(), nullable=True),
        sa.Column('probation_months', sa.Integer(), nullable=True),
        sa.Column('schedule', sa.String(length=16), nullable=True),
        sa.Column('status', sa.String(length=24), nullable=False, server_default='candidate'),
        sa.Column('vacation_entitled', sa.Integer(), nullable=True, server_default='24'),
        sa.Column('termination_date', sa.Date(), nullable=True),
        sa.Column('phone', sa.String(length=32), nullable=True),
        sa.Column('email', sa.String(length=120), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_employees_status', 'employees', ['status'])
    op.create_index('ix_employees_user_id', 'employees', ['user_id'])

    op.create_table(
        'hr_order_details',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('document_id', sa.Integer(),
                  sa.ForeignKey('documents.id'), nullable=False, unique=True),
        sa.Column('category', sa.String(length=24), nullable=False, server_default='ls'),
        sa.Column('order_kind', sa.String(length=32), nullable=False, server_default='hire'),
        sa.Column('reg_number', sa.String(length=32), nullable=True),
        sa.Column('reg_date', sa.Date(), nullable=True),
        sa.Column('effective_date', sa.Date(), nullable=True),
        sa.Column('fields_json', sa.Text(), nullable=True),
    )
    op.create_index('ix_hr_order_details_reg_number', 'hr_order_details', ['reg_number'])

    op.create_table(
        'hr_order_employees',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('detail_id', sa.Integer(),
                  sa.ForeignKey('hr_order_details.id'), nullable=False),
        sa.Column('employee_id', sa.Integer(),
                  sa.ForeignKey('employees.id'), nullable=False),
    )
    op.create_index('ix_hr_order_employees_employee_id',
                    'hr_order_employees', ['employee_id'])

    # получатели документов получают роль: execute (исполнение) /
    # acknowledge (ознакомление — HR-приказы)
    op.add_column('document_recipients',
                  sa.Column('kind', sa.String(length=16), nullable=False,
                            server_default='execute'))


def downgrade():
    op.drop_column('document_recipients', 'kind')
    op.drop_index('ix_hr_order_employees_employee_id', table_name='hr_order_employees')
    op.drop_table('hr_order_employees')
    op.drop_index('ix_hr_order_details_reg_number', table_name='hr_order_details')
    op.drop_table('hr_order_details')
    op.drop_index('ix_employees_user_id', table_name='employees')
    op.drop_index('ix_employees_status', table_name='employees')
    op.drop_table('employees')
