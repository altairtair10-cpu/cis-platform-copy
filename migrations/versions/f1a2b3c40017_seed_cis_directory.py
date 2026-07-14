"""Seed CIS staff directory (from Documentolog «Структура») as picker users

Idempotent: skips anyone already present (matched by name-token set or email),
so re-runs and existing accounts (incl. the owner) are never duplicated.
All seeded users get the least-privilege 'field' role, is_active=True (so they
appear in Получатели / Подписывающий / Согласующие pickers) and a random,
unusable password + must_change_password=True. Emails are auto-generated
placeholders — the owner should set real emails/roles in Админ → Пользователи.

Revision ID: f1a2b3c40017
Revises: e7f8a9b00016
Create Date: 2026-07-14
"""
import os, re
from alembic import op
import sqlalchemy as sa

revision = 'f1a2b3c40017'
down_revision = 'e7f8a9b00016'
branch_labels = None
depends_on = None

# (Ф.И.О. как в справочнике, Должность, Подразделение)
PEOPLE = [
    ('Абилханов Н.М.', 'Управляющий директор по финансам', 'Руководство'),
    ('Амангелдиева Мунира', 'Начальник ОКиМТС', 'Отдел контрактов и МТС'),
    ('Ауэзов Б.', 'Администратор', 'Отдел управления персоналом'),
    ('Байниязов Марат Фархадович', 'Заместитель генерального директора по экономике и финансам', 'Руководство'),
    ('Байтлеу А.', 'Экономист-казначей', 'Отдел контрактов и МТС'),
    ('Байшуаков Б.', 'Зам. начальника ПТО', 'Руководство'),
    ('Бекишев Рустем Жумагалиевич', 'Генеральный директор', 'Генеральный директор'),
    ('Джумагазиев Аслан', 'Управляющий директор по производственному обеспечению', 'Производственная база'),
    ('Досмагамбетова А.Е.', 'Главный бухгалтер', 'Руководство'),
    ('Дуйсалиев А.Б.', 'Управляющий директор по ПЗР ГРП', 'Производственно-техн. отдел'),
    ('Дуйсалиев А.М.', 'Эксперт по стратегии и развитию бизнеса', 'CASPIAN INTEGRATED SERVICES'),
    ('Елеу Т.А.', 'Заместитель генерального директора по производству', 'Производственно-техн. отдел'),
    ('Жайдарбек М.Ә.', 'Инженер по тех. обслуживанию в ПТО', 'Производственно-техн. отдел'),
    ('Жулмаганбетов Н.Б.', 'Начальник ПТО ГРП', 'Хозяйственно-транспортный отдел'),
    ('Имангалиева Л.М.', 'Специалист по кадрам', 'Отдел управления персоналом'),
    ('Исалиев Б.Ж.', 'Исполнительный директор', 'Руководство'),
    ('Кәдірханов Ғ.Қ.', 'Инженер-проектировщик ГРП', 'Инженерно-технический отдел ГРП'),
    ('Координатор ПТО', 'Координатор ПТО', 'Хозяйственно-транспортный отдел'),
    ('Кузнецов Александр Павлович', 'Главный специалист финансово-экономической службы', 'Руководство'),
    ('Мастер по ГРП', 'Мастер по ГРП', 'Участок ГРП'),
    ('Мацак С.Ю.', 'Заведующий складом', 'Центральный склад'),
    ('Мубинов Жанибек', 'Старший инженер по сервису и контрактам', 'Отдел контрактов и МТС'),
    ('Продан А.С.', 'Заместитель генерального директора по технологическому развитию', 'Руководство'),
    ('Серікбай Мардан Ералыұлы', 'Полевой-инженер ГРП', 'Инженерно-технический отдел ГРП'),
    ('Сундетов А.М.', 'Юрист', 'Руководство'),
    ('Тлеуджанова А.', 'Офис-менеджер', 'Руководство'),
    ('Уайысова Б.С.', 'Менеджер QHSE', 'Служба качества, ТБ, ОТ и ООС'),
    ('Умерзаков Нургожа Викторович', 'Начальник ПТО ПЗР ГРП', 'Руководство'),
    ('Уразбаева Г.К.', 'Главный бухгалтер', 'Бухгалтерия'),
    ('Уразов Д.С.', 'Начальник ИТО', 'Инженерно-технический отдел ГРП'),
    ('Үмітқалиева Динара', 'Координатор Департамента Бурения', 'Департамент сервиса и бурения'),
    ('Шаймарданов А.А.', 'Специалист по снабжению и IT-поддержке', 'Отдел контрактов и МТС'),
]

_TRANSLIT = {
    'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'e','ж':'zh','з':'z',
    'и':'i','й':'i','к':'k','л':'l','м':'m','н':'n','о':'o','п':'p','р':'r',
    'с':'s','т':'t','у':'u','ф':'f','х':'kh','ц':'ts','ч':'ch','ш':'sh',
    'щ':'sch','ъ':'','ы':'y','ь':'','э':'e','ю':'yu','я':'ya',
    'ә':'a','ғ':'g','қ':'k','ң':'ng','ө':'o','ұ':'u','ү':'u','һ':'h','і':'i',
}


def _translit(s):
    out = []
    for ch in s.lower():
        if ch in _TRANSLIT:
            out.append(_TRANSLIT[ch])
        elif ch.isalnum():
            out.append(ch)
    return ''.join(out)


def _name_key(name):
    """Order-independent set of lowercased alnum name tokens."""
    return frozenset(t for t in re.split(r'\s+', name.lower()) if t)


def upgrade():
    from werkzeug.security import generate_password_hash
    conn = op.get_bind()

    existing_emails = {r[0].lower() for r in conn.execute(sa.text('SELECT email FROM users')) if r[0]}
    existing_keys = set()
    for fn, ln in conn.execute(sa.text('SELECT first_name, last_name FROM users')):
        existing_keys.add(_name_key(f'{fn or ""} {ln or ""}'))

    users_tbl = sa.table(
        'users',
        sa.column('first_name', sa.String), sa.column('last_name', sa.String),
        sa.column('email', sa.String), sa.column('password_hash', sa.String),
        sa.column('role', sa.String), sa.column('position', sa.String),
        sa.column('department', sa.String), sa.column('language', sa.String),
        sa.column('is_active', sa.Boolean), sa.column('must_change_password', sa.Boolean),
    )

    rows, used_emails = [], set()
    for name, position, dept in PEOPLE:
        if _name_key(name) in existing_keys:
            continue
        parts = name.split(' ', 1)
        first = parts[0]
        last = parts[1] if len(parts) > 1 else ''
        base = _translit(first) + ('.' + _translit(last).replace('.', '')[:4] if last else '')
        email = f'{base}@cis.kz'
        n = 2
        while email in existing_emails or email in used_emails:
            email = f'{base}{n}@cis.kz'; n += 1
        used_emails.add(email)
        rows.append({
            'first_name': first[:64], 'last_name': last[:64], 'email': email[:120],
            'password_hash': generate_password_hash(os.urandom(16).hex()),
            'role': 'field', 'position': position[:128], 'department': dept[:32],
            'language': 'ru', 'is_active': True, 'must_change_password': True,
        })

    if rows:
        op.bulk_insert(users_tbl, rows)


def downgrade():
    # Remove only the auto-seeded placeholder accounts (@cis.kz created here).
    conn = op.get_bind()
    emails = []
    used = set()
    for name, position, dept in PEOPLE:
        parts = name.split(' ', 1)
        first = parts[0]; last = parts[1] if len(parts) > 1 else ''
        base = _translit(first) + ('.' + _translit(last).replace('.', '')[:4] if last else '')
        email = f'{base}@cis.kz'; n = 2
        while email in used:
            email = f'{base}{n}@cis.kz'; n += 1
        used.add(email); emails.append(email)
    if emails:
        conn.execute(
            sa.text('DELETE FROM users WHERE email = ANY(:emails) AND must_change_password = true'),
            {'emails': emails},
        )
