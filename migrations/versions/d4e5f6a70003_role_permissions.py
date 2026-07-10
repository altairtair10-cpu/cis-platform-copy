"""Editable role permissions

Revision ID: d4e5f6a70003
Revises: c3d4e5f60002
Create Date: 2026-07-10
"""
from alembic import op
import sqlalchemy as sa

revision = 'd4e5f6a70003'
down_revision = 'c3d4e5f60002'
branch_labels = None
depends_on = None

DEFAULTS = {
    'director':    ['dashboard','briefing','equipment','maintenance','transport',
                    'jobs','inventory','documents','hr','pto','worklog',
                    '1c_financial','1c_inventory','sharepoint','kpi','ai','audit'],
    'dept_head':   ['dashboard','briefing','equipment','transport','jobs',
                    'documents','hr_read','pto','worklog','sharepoint','kpi','ai'],
    'mechanic':    ['dashboard','equipment','maintenance','inventory',
                    'documents_own','pto_own','ai_mechanic'],
    'transport':   ['dashboard','transport','documents_own','pto_own','ai'],
    'hse':         ['dashboard','equipment_read','inventory_read',
                    'documents_own','sharepoint','pto_own','ai'],
    'hr':          ['dashboard','hr','pto','worklog','sharepoint','ai'],
    'accountant':  ['dashboard','1c_financial','inventory_read',
                    'documents_read','sharepoint','kpi_read','ai'],
    'procurement': ['dashboard','inventory','1c_inventory',
                    'documents_procurement','sharepoint','ai_procure'],
    'field':       ['dashboard_limited','documents_own','pto_own'],
}


def upgrade():
    table = op.create_table(
        'role_permissions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('role', sa.String(length=32), nullable=False, index=True),
        sa.Column('module', sa.String(length=64), nullable=False),
        sa.UniqueConstraint('role', 'module', name='uq_roleperm_role_module'),
    )
    rows = [{'role': role, 'module': m} for role, mods in DEFAULTS.items() for m in mods]
    op.bulk_insert(table, rows)


def downgrade():
    op.drop_table('role_permissions')
