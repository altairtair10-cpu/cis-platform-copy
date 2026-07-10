"""AI agents framework + seeded ИИ механик

Revision ID: e1f2a3b40010
Revises: d0e1f2a30009
Create Date: 2026-07-11
"""
from alembic import op
import sqlalchemy as sa

revision = 'e1f2a3b40010'
down_revision = 'd0e1f2a30009'
branch_labels = None
depends_on = None

MECHANIC_PROMPT = (
    'Ты — «ИИ механик», технический ассистент компании Caspian Integrated Services '
    '(нефтесервис, Атырау). Помогаешь механикам и инженерам: диагностика техники '
    '(насосы ГРП, блендеры, гидратационные установки, тягачи), порядок ТО, подбор '
    'запчастей, работа с реестром ТО. Отвечай кратко и практично, шагами, на языке '
    'вопроса. Если в базе знаний есть релевантный документ — опирайся на него и '
    'называй источник. Если данных не хватает — честно скажи и предложи, что проверить. '
    'Используй инструменты платформы, чтобы смотреть актуальный статус техники, '
    'открытые дефекты и историю ТО.'
)


def upgrade():
    op.create_table(
        'ai_agents',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(length=128), nullable=False, unique=True),
        sa.Column('description', sa.String(length=256), nullable=True),
        sa.Column('system_prompt', sa.Text(), nullable=False, server_default=''),
        sa.Column('model', sa.String(length=64), nullable=False,
                  server_default='claude-haiku-4-5-20251001'),
        sa.Column('allowed_roles', sa.Text(), nullable=True),
        sa.Column('use_platform_tools', sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )
    op.create_table(
        'agent_knowledge_files',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('agent_id', sa.Integer(), sa.ForeignKey('ai_agents.id'), nullable=False),
        sa.Column('original_filename', sa.String(length=256), nullable=False),
        sa.Column('stored_filename', sa.String(length=64), nullable=True),
        sa.Column('storage_backend', sa.String(length=16), nullable=True),
        sa.Column('size_bytes', sa.Integer(), nullable=True),
        sa.Column('extracted_text', sa.Text(), nullable=True),
        sa.Column('uploaded_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )
    op.get_bind().execute(sa.text(
        "INSERT INTO ai_agents (name, description, system_prompt, model, "
        "allowed_roles, use_platform_tools, is_active) VALUES "
        "('ИИ механик', 'Диагностика, ТО и запчасти — по мануалам и живым данным техники', "
        ":prompt, 'claude-haiku-4-5-20251001', NULL, TRUE, TRUE)"), {'prompt': MECHANIC_PROMPT})


def downgrade():
    op.drop_table('agent_knowledge_files')
    op.drop_table('ai_agents')
