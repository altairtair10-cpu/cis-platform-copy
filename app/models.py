from app import db, login_manager
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

# ── RBAC ──────────────────────────────────────────────────────────────────────

ROLES = {
    'it_admin':    'IT Admin',
    'director':    'Director',
    'dept_head':   'Department Head',
    'mechanic':    'Mechanic',
    'transport':   'Transport',
    'hse':         'HSE',
    'hr':          'HR',
    'accountant':  'Accountant',
    'procurement': 'Procurement',
    'field':       'Field Worker',
}

PERMISSIONS = {
    'it_admin':    ['*'],
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

DEPARTMENTS = [
    'mechanic', 'transport', 'hse', 'engineering',
    'hr', 'finance', 'procurement', 'it', 'admin', 'field'
]

LANGUAGES = ['ru', 'en', 'kz']

# ── MODELS ────────────────────────────────────────────────────────────────────

class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id            = db.Column(db.Integer, primary_key=True)
    first_name    = db.Column(db.String(64), nullable=False)
    last_name     = db.Column(db.String(64), nullable=False)
    email         = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role          = db.Column(db.String(32), nullable=False, default='field')
    position      = db.Column(db.String(128), nullable=True)   # job title (Должность)
    department    = db.Column(db.String(32), nullable=True)
    language      = db.Column(db.String(4), default='ru')
    is_active     = db.Column(db.Boolean, default=True)
    must_change_password = db.Column(db.Boolean, default=False, nullable=False)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)
    last_login    = db.Column(db.DateTime, nullable=True)

    documents     = db.relationship('Document', backref='author', lazy='dynamic',
                                    foreign_keys='Document.author_id')

    def set_password(self, password):
        from flask import current_app
        method = "pbkdf2:sha256"
        try:
            method = current_app.config.get('PASSWORD_HASH_METHOD', method)
        except RuntimeError:
            pass   # вне контекста приложения — безопасный прод-дефолт
        self.password_hash = generate_password_hash(password, method=method)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def has_permission(self, module):
        if self.role == 'it_admin':
            return True   # hardcoded so admins can never lock themselves out
        perms = get_role_permissions(self.role)
        return '*' in perms or module in perms

    def can_access(self, module):
        return self.has_permission(module)

    @property
    def full_name(self):
        return f'{self.first_name} {self.last_name}'

    @property
    def initials(self):
        parts = [p.strip() for p in (self.first_name, self.last_name) if p and p.strip()]
        return ''.join(p[0] for p in parts).upper() or '?'

    @property
    def role_display(self):
        return ROLES.get(self.role, self.role)

    @property
    def position_display(self):
        """Job title if set, otherwise fall back to role."""
        return self.position or ROLES.get(self.role, self.role)

    def __repr__(self):
        return f'<User {self.email} [{self.role}]>'


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ── DOCUMENTS ─────────────────────────────────────────────────────────────────

DOC_TYPES = {
    'purchase_req':  'Требование на приобретение материалов',
    'po_services':   'РО на услуги',
    'po_trebovanie': 'РО на товары',
    'defect_act':    'Дефектный акт',
    'memo':          'Служебная записка',
    'order':         'Приказ',
    'act':           'Акт',
    'incoming':      'Входящее письмо',
    'outgoing':      'Исходящее письмо',
    'hr_order':      'Приказ (кадровый)',
}

DOC_STATUSES = {
    'draft':        'Draft',
    'pending':      'Pending approval',
    'returned':     'Returned for revision',
    'approved':     'Approved',
    'in_execution': 'In execution',
    'executed':     'Executed',
    'awaiting_payment': 'На оплате',
    'paid':         'Оплачен',
    'closing_docs': 'Закрывающие документы',
    'closed':       'Закрыт',
    'rejected':     'Rejected',
    'archived':     'Archived',
}

class Document(db.Model):
    __tablename__ = 'documents'

    id            = db.Column(db.Integer, primary_key=True)
    doc_number    = db.Column(db.String(32), unique=True, nullable=True)
    doc_type      = db.Column(db.String(32), nullable=False)
    title         = db.Column(db.String(256), nullable=False)
    department    = db.Column(db.String(32), nullable=True)
    urgency       = db.Column(db.String(16), default='standard')
    purpose       = db.Column(db.Text, nullable=True)
    justification = db.Column(db.Text, nullable=True)
    needed_by     = db.Column(db.Date, nullable=True)
    status        = db.Column(db.String(32), default='draft')
    current_step  = db.Column(db.Integer, default=0)
    author_id     = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    executor_id   = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    equipment_id  = db.Column(db.Integer, db.ForeignKey('equipment.id'), nullable=True)
    event_code    = db.Column(db.String(64), unique=True, nullable=True)   # Б1-ДА1
    defect_closed = db.Column(db.Boolean, nullable=False, default=False)
    defect_closed_at = db.Column(db.DateTime, nullable=True)
    related_defect_id = db.Column(db.Integer, db.ForeignKey('documents.id'), nullable=True)
    related_req_id    = db.Column(db.Integer, db.ForeignKey('documents.id'), nullable=True)
    paid_at           = db.Column(db.DateTime, nullable=True)
    counterparty_id   = db.Column(db.Integer, db.ForeignKey('counterparties.id'), nullable=True)
    budget_line_id    = db.Column(db.Integer, db.ForeignKey('budget_lines.id'), nullable=True)
    # Внутренние документы (Documentolog-style): СЗ / приказ / акт / вх / исх
    body_html      = db.Column(db.Text, nullable=True)          # текст документа (rich text)
    doc_language   = db.Column(db.String(8), nullable=True)     # ru / kk / en
    case_index     = db.Column(db.String(64), nullable=True)    # индекс дела
    in_reply_to_id = db.Column(db.Integer, db.ForeignKey('documents.id'), nullable=True)
    registered_at  = db.Column(db.DateTime, nullable=True)      # момент регистрации (после подписи)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at    = db.Column(db.DateTime, default=datetime.utcnow,
                              onupdate=datetime.utcnow)

    items         = db.relationship('DocumentItem', backref='document',
                                    lazy='dynamic', cascade='all, delete-orphan')
    approvals     = db.relationship('DocumentApproval', backref='document',
                                    lazy='dynamic', cascade='all, delete-orphan')
    comments      = db.relationship('DocumentComment', backref='document',
                                    lazy='dynamic', cascade='all, delete-orphan')
    equipment     = db.relationship('Equipment', backref=db.backref('documents', lazy='dynamic'),
                                    foreign_keys=[equipment_id])
    related_defect = db.relationship('Document', remote_side='Document.id',
                                     foreign_keys=[related_defect_id])
    related_req    = db.relationship('Document', remote_side='Document.id',
                                     foreign_keys=[related_req_id],
                                     backref=db.backref('purchase_orders', lazy='dynamic'))
    budget_line    = db.relationship('BudgetLine',
                                     backref=db.backref('documents', lazy='dynamic'))
    in_reply_to    = db.relationship('Document', remote_side='Document.id',
                                     foreign_keys=[in_reply_to_id],
                                     backref=db.backref('replies', lazy='dynamic'))
    recipients     = db.relationship('DocumentRecipient', backref='document',
                                     lazy='dynamic', cascade='all, delete-orphan')

    def assign_event_code(self):
        """Per-unit sequential code for defect acts: <unit_id>-ДА<n>."""
        if self.doc_type != 'defect_act' or not self.equipment_id or self.event_code:
            return
        from app.models import Equipment
        eq = db.session.get(Equipment, self.equipment_id)
        if eq is None:
            return
        seq = DocumentSequence.next_value(f'defda:{eq.unit_id}', 0)
        self.event_code = f'{eq.unit_id}-ДА{seq}'

    def generate_number(self):
        prefix_map = {
            'purchase_req': 'ТМЦ',
            'trebovanie':   'ТРБ',
            'po_services':  'РОУ',
            'po_trebovanie':'РОТ',
            'defect_act':   'ДА',
            'memo':         'СЗ',
            'order':        'ПР',
            'act':          'АКТ',
            'incoming':     'ВХ',
            'outgoing':     'ИСХ',
            'hr_order':     'ПР',
        }
        setting = DocNumberSetting.query.filter_by(doc_type=self.doc_type).first()
        prefix  = (setting.prefix.strip() if setting and setting.prefix and setting.prefix.strip()
                   else prefix_map.get(self.doc_type, 'ДОК'))
        year   = datetime.utcnow().year
        seq    = DocumentSequence.next_value(self.doc_type, year)
        self.doc_number = f'{prefix}-{year}-{seq:03d}'

    @property
    def total_cost(self):
        """Sum of all item line totals on this document."""
        return sum((it.line_total or 0) for it in self.items)

    def __repr__(self):
        return f'<Document {self.doc_number} [{self.status}]>'


class DocumentItem(db.Model):
    __tablename__ = 'document_items'

    id          = db.Column(db.Integer, primary_key=True)
    document_id = db.Column(db.Integer, db.ForeignKey('documents.id'), nullable=False)
    name        = db.Column(db.String(256), nullable=False)
    unit        = db.Column(db.String(32), nullable=True)
    quantity    = db.Column(db.Float, nullable=True)
    note        = db.Column(db.String(256), nullable=True)
    price       = db.Column(db.Numeric(14, 2), nullable=True)   # unit price

    @property
    def line_total(self):
        """quantity × unit price, or None if either is missing."""
        if self.quantity is not None and self.price is not None:
            return float(self.quantity) * float(self.price)
        return None


class DocumentApproval(db.Model):
    __tablename__ = 'document_approvals'

    id          = db.Column(db.Integer, primary_key=True)
    document_id = db.Column(db.Integer, db.ForeignKey('documents.id'), nullable=False)
    approver_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    step        = db.Column(db.Integer, nullable=False)
    status      = db.Column(db.String(16), default='pending')
    comment     = db.Column(db.Text, nullable=True)
    decided_at  = db.Column(db.DateTime, nullable=True)

    approver    = db.relationship('User', foreign_keys=[approver_id])


class DocumentRecipient(db.Model):
    """Получатель внутреннего документа. После регистрации документ уходит
    получателям «На исполнении»; каждый отмечает исполнение — когда все
    отметили, документ становится «Исполнен»."""
    __tablename__ = 'document_recipients'

    id          = db.Column(db.Integer, primary_key=True)
    document_id = db.Column(db.Integer, db.ForeignKey('documents.id'), nullable=False)
    user_id     = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    status      = db.Column(db.String(16), default='pending')   # pending / done
    done_at     = db.Column(db.DateTime, nullable=True)
    note        = db.Column(db.String(256), nullable=True)
    kind        = db.Column(db.String(16), default='execute')   # execute / acknowledge

    user        = db.relationship('User', foreign_keys=[user_id])


class DocumentComment(db.Model):
    __tablename__ = 'document_comments'

    id          = db.Column(db.Integer, primary_key=True)
    document_id = db.Column(db.Integer, db.ForeignKey('documents.id'), nullable=False)
    author_id   = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    text        = db.Column(db.Text, nullable=False)
    is_system   = db.Column(db.Boolean, default=False)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)

    author      = db.relationship('User', foreign_keys=[author_id])


# ── EQUIPMENT ─────────────────────────────────────────────────────────────────

class Equipment(db.Model):
    __tablename__ = 'equipment'

    id           = db.Column(db.Integer, primary_key=True)
    unit_id      = db.Column(db.String(32), unique=True, nullable=False)
    name         = db.Column(db.String(128), nullable=False)
    eq_type      = db.Column(db.String(64), nullable=True)
    location     = db.Column(db.String(128), nullable=True)
    status       = db.Column(db.String(32), default='idle')
    horsepower   = db.Column(db.Integer, nullable=True)
    gos_number   = db.Column(db.String(32), nullable=True)    # гос. номер
    project      = db.Column(db.String(64), nullable=True)    # ЭМГ / CIS / КРС / Простой
    condition    = db.Column(db.Text, nullable=True)          # текущее состояние
    sheet_status = db.Column(db.String(64), nullable=True)    # статус из таблицы, как есть
    synced_at    = db.Column(db.DateTime, nullable=True)      # последняя синхронизация
    current_reading = db.Column(db.Float, nullable=True)      # моточасы/км, последнее известное
    last_to_date    = db.Column(db.Date, nullable=True)
    last_to_reading = db.Column(db.Float, nullable=True)      # наработка на момент последнего ТО
    last_repair_date = db.Column(db.Date, nullable=True)
    to_notified_at  = db.Column(db.DateTime, nullable=True)   # когда отправляли «ТО пора»
    last_service = db.Column(db.Date, nullable=True)
    next_service = db.Column(db.Date, nullable=True)
    notes        = db.Column(db.Text, nullable=True)
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)


class EquipmentMovement(db.Model):
    __tablename__ = 'equipment_movements'

    id            = db.Column(db.Integer, primary_key=True)
    equipment_id  = db.Column(db.Integer, db.ForeignKey('equipment.id'), nullable=False)
    from_location = db.Column(db.String(128), nullable=True)
    to_location   = db.Column(db.String(128), nullable=False)
    status        = db.Column(db.String(32), default='in_transit')
    eta_note      = db.Column(db.String(256), nullable=True)
    notes         = db.Column(db.Text, nullable=True)
    reported_by   = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

    equipment = db.relationship('Equipment', backref='movements')
    reporter  = db.relationship('User', foreign_keys=[reported_by])


class MaintenanceLog(db.Model):
    __tablename__ = 'maintenance_logs'

    id           = db.Column(db.Integer, primary_key=True)
    equipment_id = db.Column(db.Integer, db.ForeignKey('equipment.id'), nullable=False)
    logged_by    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    description  = db.Column(db.Text, nullable=False)
    parts_used   = db.Column(db.Text, nullable=True)
    cost         = db.Column(db.Numeric(14, 2), nullable=True)
    kind         = db.Column(db.String(4), nullable=True)   # 'ТО' | 'Р'
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)

    equipment    = db.relationship('Equipment', backref='maintenance_logs')
    technician   = db.relationship('User', foreign_keys=[logged_by])


# ── TRANSPORT ─────────────────────────────────────────────────────────────────

class TransportRun(db.Model):
    __tablename__ = 'transport_runs'

    id          = db.Column(db.Integer, primary_key=True)
    run_id      = db.Column(db.String(32), unique=True, nullable=False)
    origin      = db.Column(db.String(128), nullable=False)
    destination = db.Column(db.String(128), nullable=False)
    driver_id   = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    cargo       = db.Column(db.String(256), nullable=True)
    status      = db.Column(db.String(32), default='planned')
    scheduled   = db.Column(db.DateTime, nullable=True)
    completed   = db.Column(db.DateTime, nullable=True)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)

    driver      = db.relationship('User', foreign_keys=[driver_id])


# ── HR ────────────────────────────────────────────────────────────────────────

# ── HR: ЕДИНАЯ КАРТОЧКА СОТРУДНИКА И ПРИКАЗЫ ─────────────────────────────────

EMPLOYEE_SCHEDULES = ['5/2', '14/14', '15/15', '28/28']
EMPLOYEE_STATUSES = {
    'candidate':  'Кандидат (приём в процессе)',
    'active':     'Действующий',
    'on_leave':   'В отпуске',
    'trip':       'В командировке',
    'terminated': 'Уволен',
}
HR_ORDER_CATEGORIES = {
    'ls':         'По личному составу',
    'vacation':   'По отпускам',
    'trip':       'По командировкам',
    'production': 'Производственные',
    'main':       'По основной деятельности',
    'other':      'Прочие',
}
HR_ORDER_KINDS = {
    'hire':            ('Приём на работу', 'ls'),
    'transfer':        ('Перевод', 'ls'),
    'salary':          ('Изменение заработной платы', 'ls'),
    'combine':         ('Совмещение / замещение', 'ls'),
    'vacation':        ('Ежегодный трудовой отпуск', 'vacation'),
    'vacation_unpaid': ('Отпуск без сохранения з/п', 'vacation'),
    'recall':          ('Отзыв из отпуска', 'vacation'),
    'trip':            ('Командировка', 'trip'),
    'overtime':        ('Работа в выходной / сверхурочно', 'production'),
    'schedule':        ('Изменение графика / вахты', 'ls'),
    'bonus':           ('Премирование', 'ls'),
    'discipline':      ('Дисциплинарное взыскание', 'ls'),
    'termination':     ('Увольнение', 'ls'),
    'other':           ('Прочее', 'other'),
}


class Employee(db.Model):
    """Единая карточка сотрудника. Отдельно от User: у сотрудника может не
    быть аккаунта в системе (вахтовики и т.п.); user_id — связь при наличии."""
    __tablename__ = 'employees'

    id           = db.Column(db.Integer, primary_key=True)
    user_id      = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    full_name_ru = db.Column(db.String(160), nullable=False)
    full_name_kz = db.Column(db.String(160), nullable=True)
    iin          = db.Column(db.String(12), nullable=True)
    position_ru  = db.Column(db.String(160), nullable=True)
    position_kz  = db.Column(db.String(160), nullable=True)
    department   = db.Column(db.String(120), nullable=True)
    manager_id   = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=True)
    hire_date    = db.Column(db.Date, nullable=True)
    contract_number = db.Column(db.String(64), nullable=True)
    contract_date   = db.Column(db.Date, nullable=True)
    contract_end    = db.Column(db.Date, nullable=True)
    probation_months = db.Column(db.Integer, nullable=True)
    schedule     = db.Column(db.String(16), nullable=True)      # 5/2, 14/14, 15/15, 28/28
    status       = db.Column(db.String(24), nullable=False, default='candidate')
    vacation_entitled = db.Column(db.Integer, default=24)
    current_salary = db.Column(db.Integer, nullable=True)   # оклад, целые тенге (без float)
    termination_date  = db.Column(db.Date, nullable=True)
    phone        = db.Column(db.String(32), nullable=True)
    email        = db.Column(db.String(120), nullable=True)
    notes        = db.Column(db.Text, nullable=True)
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)

    user     = db.relationship('User', foreign_keys=[user_id])
    manager  = db.relationship('Employee', remote_side=[id])
    order_links = db.relationship('HROrderEmployee', back_populates='employee',
                                  lazy='dynamic')

    @property
    def status_display(self):
        return EMPLOYEE_STATUSES.get(self.status, self.status)

    @property
    def tenure_days(self):
        """Стаж в днях (от приёма до увольнения/сегодня)."""
        if not self.hire_date:
            return None
        end = self.termination_date or datetime.utcnow().date()
        return max(0, (end - self.hire_date).days)

    @property
    def tenure_display(self):
        """Стаж по-человечески: «2 г. 4 мес.» / «3 мес.» / «12 дн.»."""
        d = self.tenure_days
        if d is None:
            return None
        years, rem = divmod(d, 365)
        months = rem // 30
        parts = []
        if years:
            parts.append(f'{years} г.')
        if months:
            parts.append(f'{months} мес.')
        return ' '.join(parts) if parts else f'{d} дн.'

    @property
    def initials(self):
        words = (self.full_name_ru or '').split()
        return ''.join(w[0] for w in words[:2]).upper() or '·'

    @property
    def salary_display(self):
        """Оклад с разделителями: «450 000 ₸»."""
        if self.current_salary is None:
            return None
        return f'{self.current_salary:,}'.replace(',', ' ') + ' ₸'


class HROrderDetail(db.Model):
    """Кадровые атрибуты приказа (Document с doc_type='hr_order'):
    категория, вид, ручная регистрация (№ и дата задним числом — требование
    законодательства РК)."""
    __tablename__ = 'hr_order_details'

    id           = db.Column(db.Integer, primary_key=True)
    document_id  = db.Column(db.Integer, db.ForeignKey('documents.id'),
                             nullable=False, unique=True)
    category     = db.Column(db.String(24), nullable=False, default='ls')
    order_kind   = db.Column(db.String(32), nullable=False, default='hire')
    reg_number   = db.Column(db.String(32), nullable=True)   # «ЛС-128» — вручную
    reg_date     = db.Column(db.Date, nullable=True)         # задним числом можно
    effective_date = db.Column(db.Date, nullable=True)
    fields_json  = db.Column(db.Text, nullable=True)         # гибкие поля вида

    document  = db.relationship('Document', backref=db.backref('hr_detail', uselist=False))
    employees = db.relationship('HROrderEmployee', back_populates='detail',
                                lazy='dynamic')

    @property
    def kind_display(self):
        return HR_ORDER_KINDS.get(self.order_kind, (self.order_kind, ''))[0]

    @property
    def category_display(self):
        return HR_ORDER_CATEGORIES.get(self.category, self.category)


class HROrderEmployee(db.Model):
    """Связь приказа с сотрудниками (премирование и т.п. — несколько)."""
    __tablename__ = 'hr_order_employees'

    id          = db.Column(db.Integer, primary_key=True)
    detail_id   = db.Column(db.Integer, db.ForeignKey('hr_order_details.id'),
                            nullable=False)
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'),
                            nullable=False)

    detail   = db.relationship('HROrderDetail', back_populates='employees')
    employee = db.relationship('Employee', back_populates='order_links')


class PTORequest(db.Model):
    __tablename__ = 'pto_requests'

    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    leave_type  = db.Column(db.String(32), default='annual')
    start_date  = db.Column(db.Date, nullable=False)
    end_date    = db.Column(db.Date, nullable=False)
    reason      = db.Column(db.Text, nullable=True)
    status      = db.Column(db.String(16), default='pending')
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)

    employee    = db.relationship('User', foreign_keys=[user_id])
    approver    = db.relationship('User', foreign_keys=[approved_by])


class WorkLog(db.Model):
    __tablename__ = 'work_logs'

    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    date       = db.Column(db.Date, nullable=False)
    check_in   = db.Column(db.DateTime, nullable=True)
    check_out  = db.Column(db.DateTime, nullable=True)
    notes      = db.Column(db.String(256), nullable=True)

    employee   = db.relationship('User', foreign_keys=[user_id])


# ── NOTIFICATIONS ─────────────────────────────────────────────────────────────

class Notification(db.Model):
    __tablename__ = 'notifications'

    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title      = db.Column(db.String(256), nullable=False)
    body       = db.Column(db.Text, nullable=True)
    link       = db.Column(db.String(256), nullable=True)
    is_read    = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user       = db.relationship('User', foreign_keys=[user_id])

# ── AUDIT TRAIL ───────────────────────────────────────────────────────────────

class AuditLog(db.Model):
    """Who did what, when — written via app.audit.log_action()."""
    __tablename__ = 'audit_logs'

    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    action      = db.Column(db.String(64), nullable=False, index=True)
    entity_type = db.Column(db.String(64), nullable=True)
    entity_id   = db.Column(db.Integer, nullable=True)
    details     = db.Column(db.Text, nullable=True)
    ip          = db.Column(db.String(64), nullable=True)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    user        = db.relationship('User', foreign_keys=[user_id])

    def __repr__(self):
        return f'<AuditLog {self.action} by user {self.user_id}>'


# ── DOCUMENT NUMBERING ────────────────────────────────────────────────────────

class DocumentSequence(db.Model):
    """Race-safe per-type, per-year document number counter."""
    __tablename__ = 'document_sequences'

    id       = db.Column(db.Integer, primary_key=True)
    doc_type = db.Column(db.String(32), nullable=False)
    year     = db.Column(db.Integer, nullable=False)
    counter  = db.Column(db.Integer, nullable=False, default=0)

    __table_args__ = (
        db.UniqueConstraint('doc_type', 'year', name='uq_docseq_type_year'),
    )

    @classmethod
    def next_value(cls, doc_type, year):
        """Increment and return the counter under a row lock (SELECT ... FOR UPDATE)."""
        row = cls.query.filter_by(doc_type=doc_type, year=year)\
                       .with_for_update().first()
        if row is None:
            row = cls(doc_type=doc_type, year=year, counter=0)
            db.session.add(row)
            db.session.flush()
            row = cls.query.filter_by(doc_type=doc_type, year=year)\
                           .with_for_update().first()
        row.counter += 1
        return row.counter
    # ── ADMIN: REFERENCE DATA ──────────────────────────────────────────────────────
# Editable lists that used to be hardcoded constants. Both models share the
# same simple shape (name + active flag) on purpose, so the admin CRUD screens
# can reuse one template.

class EquipmentType(db.Model):
    __tablename__ = 'equipment_types'

    id        = db.Column(db.Integer, primary_key=True)
    name      = db.Column(db.String(64), unique=True, nullable=False)
    is_active = db.Column(db.Boolean, default=True)


class ReferenceDepartment(db.Model):
    """DB-backed department list. Existing code keeps using the DEPARTMENTS
    constant for now; this table is what the new admin panel manages and is
    meant to replace it once every screen that reads DEPARTMENTS is migrated."""
    __tablename__ = 'reference_departments'

    id        = db.Column(db.Integer, primary_key=True)
    name      = db.Column(db.String(64), unique=True, nullable=False)
    is_active = db.Column(db.Boolean, default=True)


class BudgetLine(db.Model):
    """Справочник статей бюджета с годовым лимитом (идея из ERPNext Budget:
    контроль на этапе создания РО в режиме Warn — предупреждаем, не блокируем).
    yearly_limit = None означает «без лимита» (статья только для унификации)."""
    __tablename__ = 'budget_lines'

    id           = db.Column(db.Integer, primary_key=True)
    name         = db.Column(db.String(128), unique=True, nullable=False)
    yearly_limit = db.Column(db.Numeric(14, 2), nullable=True)
    is_active    = db.Column(db.Boolean, default=True)

    def __repr__(self):
        return f'<BudgetLine {self.name} limit={self.yearly_limit}>'


# ── DOCUMENT ATTACHMENTS ────────────────────────────────────────────────────────

class DocumentAttachment(db.Model):
    __tablename__ = 'document_attachments'

    id               = db.Column(db.Integer, primary_key=True)
    document_id      = db.Column(db.Integer, db.ForeignKey('documents.id'), nullable=False)
    original_filename = db.Column(db.String(256), nullable=False)
    stored_filename  = db.Column(db.String(256), nullable=False)  # disk name or Azure blob name
    storage_backend  = db.Column(db.String(16), nullable=False, default='local')  # 'local' or 'azure'
    content_type     = db.Column(db.String(128), nullable=True)
    size_bytes       = db.Column(db.Integer, nullable=True)
    uploaded_by      = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    uploaded_at      = db.Column(db.DateTime, default=datetime.utcnow)

    document  = db.relationship('Document', backref=db.backref('attachments', cascade='all, delete-orphan'))
    uploader  = db.relationship('User', foreign_keys=[uploaded_by])


# ── CONTRACTS ─────────────────────────────────────────────────────────────────
# Was a hardcoded dict in the contracts blueprint; now real, editable rows.

class Contract(db.Model):
    __tablename__ = 'contracts'

    id         = db.Column(db.Integer, primary_key=True)
    client     = db.Column(db.String(128), nullable=False)
    period     = db.Column(db.String(128), nullable=False)   # display string, e.g. "Q1 2026 · Январь — Март"
    updated_at = db.Column(db.Date, nullable=True)

    summary_rows = db.relationship('ContractSummaryRow', backref='contract',
                                   lazy='dynamic', cascade='all, delete-orphan',
                                   order_by='ContractSummaryRow.sort_order')
    detail_groups = db.relationship('ContractDetailGroup', backref='contract',
                                    lazy='dynamic', cascade='all, delete-orphan',
                                    order_by='ContractDetailGroup.sort_order')


class ContractSummaryRow(db.Model):
    __tablename__ = 'contract_summary_rows'

    id          = db.Column(db.Integer, primary_key=True)
    contract_id = db.Column(db.Integer, db.ForeignKey('contracts.id'), nullable=False)
    name        = db.Column(db.String(128), nullable=False)
    plan_year   = db.Column(db.Integer, nullable=False, default=0)
    plan_q      = db.Column(db.Integer, nullable=False, default=0)
    fact_q      = db.Column(db.Integer, nullable=False, default=0)
    unit        = db.Column(db.String(32), nullable=True)
    color       = db.Column(db.String(16), nullable=False, default='blue')  # red/amber/blue
    sort_order  = db.Column(db.Integer, nullable=False, default=0)


class ContractDetailGroup(db.Model):
    __tablename__ = 'contract_detail_groups'

    id          = db.Column(db.Integer, primary_key=True)
    contract_id = db.Column(db.Integer, db.ForeignKey('contracts.id'), nullable=False)
    name        = db.Column(db.String(128), nullable=False)
    sort_order  = db.Column(db.Integer, nullable=False, default=0)

    rows = db.relationship('ContractDetailRow', backref='group',
                           lazy='dynamic', cascade='all, delete-orphan',
                           order_by='ContractDetailRow.sort_order')


class ContractDetailRow(db.Model):
    __tablename__ = 'contract_detail_rows'

    id         = db.Column(db.Integer, primary_key=True)
    group_id   = db.Column(db.Integer, db.ForeignKey('contract_detail_groups.id'), nullable=False)
    name       = db.Column(db.String(256), nullable=False)
    contract_qty = db.Column(db.Integer, nullable=False, default=0)
    done       = db.Column(db.Integer, nullable=False, default=0)
    remainder  = db.Column(db.Integer, nullable=False, default=0)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    


# ── ADMIN-MANAGED REFERENCE DATA (Phase 1) ────────────────────────────────────

class Location(db.Model):
    """Flat list of company locations (bases, fields, wells, offices)."""
    __tablename__ = 'locations'

    id         = db.Column(db.Integer, primary_key=True)
    name       = db.Column(db.String(128), unique=True, nullable=False)
    is_active  = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class AppSetting(db.Model):
    """Key-value store for site-wide settings (branding, etc.)."""
    __tablename__ = 'app_settings'

    id    = db.Column(db.Integer, primary_key=True)
    key   = db.Column(db.String(64), unique=True, nullable=False)
    value = db.Column(db.Text, nullable=True)

    @classmethod
    def get(cls, key, default=None):
        row = cls.query.filter_by(key=key).first()
        return row.value if row and row.value else default

    @classmethod
    def set(cls, key, value):
        row = cls.query.filter_by(key=key).first()
        if row is None:
            row = cls(key=key)
            db.session.add(row)
        row.value = value


class DocNumberSetting(db.Model):
    """Admin-editable document number prefix per document type."""
    __tablename__ = 'doc_number_settings'

    id       = db.Column(db.Integer, primary_key=True)
    doc_type = db.Column(db.String(32), unique=True, nullable=False)
    prefix   = db.Column(db.String(16), nullable=True)


# ── EDITABLE ROLE PERMISSIONS ─────────────────────────────────────────────────

class RolePermission(db.Model):
    """One row = role X may access module Y. Seeded from PERMISSIONS defaults;
    editable in the admin panel. it_admin is hardcoded to full access."""
    __tablename__ = 'role_permissions'

    id     = db.Column(db.Integer, primary_key=True)
    role   = db.Column(db.String(32), nullable=False, index=True)
    module = db.Column(db.String(64), nullable=False)

    __table_args__ = (
        db.UniqueConstraint('role', 'module', name='uq_roleperm_role_module'),
    )


def all_permission_modules():
    """Union of every module used in the default permission map (excl. '*')."""
    mods = set()
    for perms in PERMISSIONS.values():
        mods.update(p for p in perms if p != '*')
    return sorted(mods)


def get_role_permissions(role):
    """Effective permission set for a role: DB rows if the table is populated
    for that role, otherwise code defaults. Cached per request."""
    from flask import g, has_app_context
    if has_app_context():
        cache = getattr(g, '_role_perms_cache', None)
        if cache is None:
            cache = g._role_perms_cache = {}
        if role in cache:
            return cache[role]
    try:
        rows = RolePermission.query.filter_by(role=role).all()
        perms = ({r.module for r in rows} - {'__none__'}) if rows else set(PERMISSIONS.get(role, []))
    except Exception:
        # table missing (pre-migration) — fall back to defaults
        perms = set(PERMISSIONS.get(role, []))
    if has_app_context():
        g._role_perms_cache[role] = perms
    return perms


# ── MAINTENANCE (ТО / РЕМОНТ) ─────────────────────────────────────────────────

class MaintenancePolicy(db.Model):
    """Per-category service rule: ТО every N motohours / N km, or repair-only."""
    __tablename__ = 'maintenance_policies'

    id       = db.Column(db.Integer, primary_key=True)
    eq_type  = db.Column(db.String(64), unique=True, nullable=False)  # категория из дэшборда
    mode     = db.Column(db.String(16), nullable=False, default='repair_only')  # hours | km | repair_only
    interval = db.Column(db.Integer, nullable=True)   # 400 (м/ч) or 10000 (км)


class MaintenanceTabMap(db.Model):
    """Manual mapping: register worksheet title -> equipment unit.
    Takes priority over automatic gos-number matching."""
    __tablename__ = 'maintenance_tab_map'

    id           = db.Column(db.Integer, primary_key=True)
    tab_title    = db.Column(db.String(128), unique=True, nullable=False)
    equipment_id = db.Column(db.Integer, db.ForeignKey('equipment.id'), nullable=True)
    is_ignored   = db.Column(db.Boolean, default=False, nullable=False)

    equipment    = db.relationship('Equipment')


class ServiceRecord(db.Model):
    """One row of the maintenance register (Реестр учёта ТО и ремонтных работ)."""
    __tablename__ = 'service_records'

    id           = db.Column(db.Integer, primary_key=True)
    equipment_id = db.Column(db.Integer, db.ForeignKey('equipment.id'), nullable=False, index=True)
    date         = db.Column(db.Date, nullable=True)
    kind         = db.Column(db.String(4), nullable=False)      # 'ТО' | 'Р'
    kind_raw     = db.Column(db.String(16), nullable=True)      # 'ТО 1', 'ТО2', 'Р'...
    description  = db.Column(db.Text, nullable=True)
    reading      = db.Column(db.Float, nullable=True)           # пробег/моточасы в строке
    executor     = db.Column(db.String(128), nullable=True)
    row_hash     = db.Column(db.String(40), unique=True, nullable=False)  # дедупликация
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)

    equipment    = db.relationship('Equipment',
                                   backref=db.backref('service_records', lazy='dynamic'))


# ── APPROVAL ROUTE TEMPLATES ──────────────────────────────────────────────────

class RouteTemplate(db.Model):
    """Saved approval route: signatory + stages, applied to new documents.
    data JSON: {"signatory": {"id":..,"name":..},
                "stages": [{"type":"parallel|sequential",
                            "reviewers":[{"id":..,"name":..}]}]}"""
    __tablename__ = 'route_templates'

    id         = db.Column(db.Integer, primary_key=True)
    name       = db.Column(db.String(128), unique=True, nullable=False)
    data       = db.Column(db.Text, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ── AI AGENTS ─────────────────────────────────────────────────────────────────

class AiAgent(db.Model):
    """Configurable department assistant: prompt + knowledge files + optional
    live platform tools. Managed in the admin panel."""
    __tablename__ = 'ai_agents'

    id            = db.Column(db.Integer, primary_key=True)
    name          = db.Column(db.String(128), unique=True, nullable=False)
    description   = db.Column(db.String(256), nullable=True)
    system_prompt = db.Column(db.Text, nullable=False, default='')
    model         = db.Column(db.String(64), nullable=False,
                              default='claude-haiku-4-5-20251001')
    allowed_roles = db.Column(db.Text, nullable=True)   # csv; empty/null = все роли
    use_platform_tools = db.Column(db.Boolean, nullable=False, default=False)
    is_active     = db.Column(db.Boolean, nullable=False, default=True)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

    files         = db.relationship('AgentKnowledgeFile', backref='agent',
                                    lazy='dynamic', cascade='all, delete-orphan')

    def role_allowed(self, user):
        if user.role == 'it_admin':
            return True
        if not self.is_active:
            return False
        roles = [r.strip() for r in (self.allowed_roles or '').split(',') if r.strip()]
        return not roles or user.role in roles


class AgentKnowledgeFile(db.Model):
    __tablename__ = 'agent_knowledge_files'

    id                = db.Column(db.Integer, primary_key=True)
    agent_id          = db.Column(db.Integer, db.ForeignKey('ai_agents.id'), nullable=False)
    original_filename = db.Column(db.String(256), nullable=False)
    stored_filename   = db.Column(db.String(64), nullable=True)
    storage_backend   = db.Column(db.String(16), nullable=True)
    size_bytes        = db.Column(db.Integer, nullable=True)
    extracted_text    = db.Column(db.Text, nullable=True)   # что читает агент
    uploaded_by       = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at        = db.Column(db.DateTime, default=datetime.utcnow)


# ── КОНТРАГЕНТЫ ───────────────────────────────────────────────────────────────

class Counterparty(db.Model):
    """Справочник контрагентов для ПО (поставщики товаров и услуг)."""
    __tablename__ = 'counterparties'

    id             = db.Column(db.Integer, primary_key=True)
    name           = db.Column(db.String(256), unique=True, nullable=False)
    bin            = db.Column(db.String(32), nullable=True)      # БИН/ИИН
    address        = db.Column(db.String(256), nullable=True)
    phone          = db.Column(db.String(64), nullable=True)
    email          = db.Column(db.String(128), nullable=True)
    contact_person = db.Column(db.String(128), nullable=True)
    materials      = db.Column(db.String(256), nullable=True)     # что поставляет
    currency       = db.Column(db.String(8), nullable=True, default='KZT')
    is_active      = db.Column(db.Boolean, nullable=False, default=True)
    created_by     = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at     = db.Column(db.DateTime, default=datetime.utcnow)


class ToPart(db.Model):
    """Материалы для ТО конкретной единицы техники (фильтры, масла...).
    Название должно совпадать с колонкой «Материал» складской таблицы —
    тогда система сама проверяет наличие на складе."""
    __tablename__ = 'to_parts'

    id           = db.Column(db.Integer, primary_key=True)
    equipment_id = db.Column(db.Integer, db.ForeignKey('equipment.id'),
                             nullable=False, index=True)
    name         = db.Column(db.String(256), nullable=False)
    qty          = db.Column(db.Float, nullable=True)      # сколько нужно на одно ТО
    unit         = db.Column(db.String(32), nullable=True)
    note         = db.Column(db.String(256), nullable=True)
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)

    equipment    = db.relationship('Equipment',
                                   backref=db.backref('to_parts', lazy='dynamic'))


class SavedView(db.Model):
    """Сохранённый вид реестра документов: имя + параметры фильтров пользователя."""
    __tablename__ = 'saved_views'

    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    name       = db.Column(db.String(128), nullable=False)
    params     = db.Column(db.Text, nullable=False, default='')   # querystring
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
