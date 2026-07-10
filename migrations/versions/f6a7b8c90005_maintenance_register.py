"""Maintenance register: service records, policies, equipment readings

Revision ID: f6a7b8c90005
Revises: e5f6a7b80004
Create Date: 2026-07-10
"""
from alembic import op
import sqlalchemy as sa

revision = 'f6a7b8c90005'
down_revision = 'e5f6a7b80004'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'maintenance_policies',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('eq_type', sa.String(length=64), nullable=False, unique=True),
        sa.Column('mode', sa.String(length=16), nullable=False, server_default='repair_only'),
        sa.Column('interval', sa.Integer(), nullable=True),
    )
    op.create_table(
        'service_records',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('equipment_id', sa.Integer(), sa.ForeignKey('equipment.id'), nullable=False),
        sa.Column('date', sa.Date(), nullable=True),
        sa.Column('kind', sa.String(length=4), nullable=False),
        sa.Column('kind_raw', sa.String(length=16), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('reading', sa.Float(), nullable=True),
        sa.Column('executor', sa.String(length=128), nullable=True),
        sa.Column('row_hash', sa.String(length=40), nullable=False, unique=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_service_records_equipment_id', 'service_records', ['equipment_id'])

    with op.batch_alter_table('equipment') as batch:
        batch.add_column(sa.Column('current_reading', sa.Float(), nullable=True))
        batch.add_column(sa.Column('last_to_date', sa.Date(), nullable=True))
        batch.add_column(sa.Column('last_to_reading', sa.Float(), nullable=True))
        batch.add_column(sa.Column('last_repair_date', sa.Date(), nullable=True))
        batch.add_column(sa.Column('to_notified_at', sa.DateTime(), nullable=True))

    # sensible defaults; admin can adjust in Админ-панель → Настройки ТО
    bind = op.get_bind()
    for eq_type, mode, interval in [
        ('Насос ГРП', 'hours', 400),
        ('C-PUMP', 'hours', 400),
        ('Блендер', 'hours', 400),
        ('Гидратационка', 'hours', 400),
        ('Тягачи', 'km', 10000),
    ]:
        bind.execute(sa.text(
            "INSERT INTO maintenance_policies (eq_type, mode, interval) "
            "VALUES (:t, :m, :i)"), {'t': eq_type, 'm': mode, 'i': interval})


def downgrade():
    with op.batch_alter_table('equipment') as batch:
        batch.drop_column('to_notified_at')
        batch.drop_column('last_repair_date')
        batch.drop_column('last_to_reading')
        batch.drop_column('last_to_date')
        batch.drop_column('current_reading')
    op.drop_index('ix_service_records_equipment_id', table_name='service_records')
    op.drop_table('service_records')
    op.drop_table('maintenance_policies')
