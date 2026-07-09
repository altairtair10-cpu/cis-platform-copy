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
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)
    last_login    = db.Column(db.DateTime, nullable=True)

    documents     = db.relationship('Document', backref='author', lazy='dynamic',
                                    foreign_keys='Document.author_id')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password, method="pbkdf2:sha256")

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def has_permission(self, module):
        perms = PERMISSIONS.get(self.role, [])
        return '*' in perms or module in perms

    def can_access(self, module):
        return self.has_permission(module)

    @property
    def full_name(self):
        return f'{self.first_name} {self.last_name}'

    @property
    def initials(self):
        return f'{self.first_name[0]}{self.last_name[0]}'.upper()

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
    'purchase_req': 'Требование на приобретение',
    'memo':         'Служебная записка',
    'order':        'Приказ',
    'act':          'Акт',
    'incoming':     'Входящее письмо',
    'outgoing':     'Исходящее письмо',
}

DOC_STATUSES = {
    'draft':    'Draft',
    'pending':  'Pending approval',
    'returned': 'Returned for revision',
    'approved': 'Approved',
    'rejected': 'Rejected',
    'archived': 'Archived',
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
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at    = db.Column(db.DateTime, default=datetime.utcnow,
                              onupdate=datetime.utcnow)

    items         = db.relationship('DocumentItem', backref='document',
                                    lazy='dynamic', cascade='all, delete-orphan')
    approvals     = db.relationship('DocumentApproval', backref='document',
                                    lazy='dynamic', cascade='all, delete-orphan')
    comments      = db.relationship('DocumentComment', backref='document',
                                    lazy='dynamic', cascade='all, delete-orphan')

    def generate_number(self):
        prefix_map = {
            'purchase_req': 'ТМЦ',
            'trebovanie':   'ТРБ',
            'po_services':  'РОУ',
            'defect_act':   'ДА',
            'memo':         'СЗ',
            'order':        'ПР',
            'act':          'АКТ',
            'incoming':     'ВХ',
            'outgoing':     'ИСХ',
        }
        prefix = prefix_map.get(self.doc_type, 'ДОК')
        year   = datetime.utcnow().year
        count  = Document.query.filter_by(doc_type=self.doc_type).count()
        self.doc_number = f'{prefix}-{year}-{count+1:03d}'

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
    price       = db.Column(db.Float, nullable=True)   # unit price

    @property
    def line_total(self):
        """quantity × unit price, or None if either is missing."""
        if self.quantity is not None and self.price is not None:
            return self.quantity * self.price
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
    cost         = db.Column(db.Float, nullable=True)
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