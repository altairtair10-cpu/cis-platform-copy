"""HR module phase 2: employee salary column for kadровые приказы
(изменение з/п и др.).

Revision ID: h3c4d5e60019
Revises: g2b3c4d50018
Create Date: 2026-07-21
"""
from alembic import op
import sqlalchemy as sa

revision = 'h3c4d5e60019'
down_revision = 'g2b3c4d50018'
branch_labels = None
depends_on = None


def upgrade():
    # оклад в целых тенге (без float — валюта не хранится в плавающей точке)
    op.add_column('employees',
                  sa.Column('current_salary', sa.Integer(), nullable=True))


def downgrade():
    op.drop_column('employees', 'current_salary')
