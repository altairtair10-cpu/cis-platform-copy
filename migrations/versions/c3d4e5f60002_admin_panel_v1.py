"""Admin panel v1: locations, app settings, doc number prefixes

Revision ID: c3d4e5f60002
Revises: f2a8c9d3e100
Create Date: 2026-07-10
"""
from alembic import op
import sqlalchemy as sa

revision = 'c3d4e5f60002'
down_revision = 'f2a8c9d3e100'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'locations',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(length=128), nullable=False, unique=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )
    op.create_table(
        'app_settings',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('key', sa.String(length=64), nullable=False, unique=True),
        sa.Column('value', sa.Text(), nullable=True),
    )
    op.create_table(
        'doc_number_settings',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('doc_type', sa.String(length=32), nullable=False, unique=True),
        sa.Column('prefix', sa.String(length=16), nullable=True),
    )

    # Seed locations from every distinct location already used on equipment
    bind = op.get_bind()
    bind.execute(sa.text(
        "INSERT INTO locations (name, is_active) "
        "SELECT DISTINCT location, TRUE FROM equipment "
        "WHERE location IS NOT NULL AND location <> '' "
        "AND location NOT IN (SELECT name FROM locations)"
    ))
    # Seed default company name
    bind.execute(sa.text(
        "INSERT INTO app_settings (key, value) VALUES ('company_name', 'CIS Platform')"
    ))


def downgrade():
    op.drop_table('doc_number_settings')
    op.drop_table('app_settings')
    op.drop_table('locations')
