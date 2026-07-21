"""HR-приказы (кадровые): приём сотрудника, журнал приказов, ручная
регистрация, единая карточка сотрудника.

Дорожная карта HR (фаза 1). Приказ = Document(doc_type='hr_order') +
HROrderDetail — весь движок маршрутов/согласований переиспользуется.

Обязательное правило системы (из ТЗ кадровика): любой подписанный и
зарегистрированный приказ направляется в бухгалтерию; если приказ связан с
сотрудником — появляется в его карточке; кадровые данные обновляются с
сохранением истории.
"""
import json
from datetime import datetime
from flask import render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from app import db
from app.models import (Document, DocumentComment, DocumentRecipient, User,
                        Notification, Employee, HROrderDetail, HROrderEmployee,
                        EMPLOYEE_SCHEDULES, EMPLOYEE_STATUSES,
                        HR_ORDER_KINDS, HR_ORDER_CATEGORIES)
from app.decorators import requires_permission
from app.audit import log_action
from app.blueprints.documents.helpers import (_build_route,
                                              _save_form_attachments,
                                              _notify_approvers)
from .order_specs import ORDER_SPECS
from . import hr

# Кто видит карточки сотрудников (ограниченный список — требование кадровика:
# «я, генеральный директор, главный бухгалтер»; it_admin — сопровождение).
CARD_ROLES = ('hr', 'director', 'accountant', 'it_admin')


def _can_view_cards():
    return current_user.role in CARD_ROLES


def _parse_date(name):
    raw = request.form.get(name)
    if not raw:
        return None
    try:
        return datetime.strptime(raw, '%Y-%m-%d').date()
    except ValueError:
        return None


def _parse_date_value(raw):
    """Как _parse_date, но из готовой строки (значение из fields_json)."""
    if not raw:
        return None
    try:
        return datetime.strptime(raw, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return None


def _to_int(raw):
    try:
        return int(str(raw).replace(' ', '').replace(' ', ''))
    except (ValueError, TypeError):
        return None


# Активные сотрудники для выбора в приказ (все, кроме уволенных)
def _pickable_employees():
    return (Employee.query.filter(Employee.status != 'terminated')
            .order_by(Employee.full_name_ru).all())


def _apply_order_effect(detail, emp, reg_date):
    """Эффект приказа на карточку сотрудника при регистрации.

    Только «твёрдые» изменения состояния применяются автоматически;
    премии/дисциплина/командировочные суммы и т.п. остаются записью в
    приказе (fields_json) и видны в карточке, но не меняют мастер-данные.
    """
    import json as _json
    fj = _json.loads(detail.fields_json or '{}')
    kind = detail.order_kind

    if kind == 'hire':
        emp.status = 'active'
        if detail.effective_date:
            emp.hire_date = detail.effective_date
    elif kind == 'transfer':
        if fj.get('new_position_ru'):
            emp.position_ru = fj['new_position_ru'][:160]
        if fj.get('new_position_kz'):
            emp.position_kz = fj['new_position_kz'][:160]
        if fj.get('new_department'):
            emp.department = fj['new_department'][:120]
    elif kind == 'salary':
        val = _to_int(fj.get('new_salary'))
        if val is not None:
            emp.current_salary = val
    elif kind == 'schedule':
        if fj.get('new_schedule'):
            emp.schedule = fj['new_schedule'][:16]
    elif kind in ('vacation', 'vacation_unpaid'):
        emp.status = 'on_leave'
    elif kind == 'recall':
        if emp.status == 'on_leave':
            emp.status = 'active'
    elif kind == 'trip':
        emp.status = 'trip'
    elif kind == 'termination':
        emp.status = 'terminated'
        emp.termination_date = detail.effective_date or reg_date
    # combine / bonus / discipline / overtime / other — запись без смены мастер-данных


# ── СОТРУДНИКИ ────────────────────────────────────────────────────────────────

@hr.route('/employees')
@login_required
@requires_permission('hr')
def employees():
    q = (request.args.get('q') or '').strip()
    status = request.args.get('status')
    query = Employee.query
    if status:
        query = query.filter_by(status=status)
    if q:
        like = f'%{q.lower()}%'
        from sqlalchemy import func, or_
        query = query.filter(or_(func.lower(Employee.full_name_ru).like(like),
                                 func.lower(Employee.position_ru).like(like)))
    staff = query.order_by(Employee.full_name_ru).all()
    return render_template('hr/employees.html', staff=staff, q=q,
                           sel_status=status, statuses=EMPLOYEE_STATUSES)


@hr.route('/employees/<int:emp_id>')
@login_required
def employee_card(emp_id):
    if not _can_view_cards():
        abort(403)
    emp = Employee.query.get_or_404(emp_id)
    links = emp.order_links.all()
    orders = sorted((l.detail for l in links),
                    key=lambda d: (d.reg_date or d.document.created_at.date()),
                    reverse=True)
    return render_template('hr/employee_card.html', emp=emp, orders=orders,
                           statuses=EMPLOYEE_STATUSES)


# ── ПРИЁМ СОТРУДНИКА (фаза 1 дорожной карты) ─────────────────────────────────

@hr.route('/hire/new', methods=['GET'])
@login_required
@requires_permission('hr')
def hire_new():
    users = User.query.filter_by(is_active=True)\
                      .order_by(User.first_name, User.last_name).all()
    return render_template('hr/hire_new.html', users=users,
                           schedules=EMPLOYEE_SCHEDULES)


@hr.route('/hire/submit', methods=['POST'])
@login_required
@requires_permission('hr')
def hire_submit():
    action = request.form.get('action', 'draft')
    signatory_id = request.form.get('signatory_id', type=int)
    full_name_ru = (request.form.get('full_name_ru') or '').strip()

    if not full_name_ru:
        flash('Укажите ФИО сотрудника.', 'warning')
        return redirect(url_for('hr.hire_new'))
    if action == 'submit' and not signatory_id:
        action = 'draft'
        flash('Приказ сохранён как проект: не выбран подписывающий (ГД).', 'warning')

    # испытательный срок: «три месяца» (прописью, как в Documentolog) +
    # числовое значение для карточки, если удаётся разобрать
    probation_text = (request.form.get('probation_text') or '').strip()
    probation_months = None
    for word, n in (('один', 1), ('два', 2), ('три', 3), ('четыре', 4),
                    ('шесть', 6), ('1', 1), ('2', 2), ('3', 3), ('6', 6)):
        if word in probation_text.lower():
            probation_months = n
            break

    emp = Employee(
        full_name_ru = full_name_ru[:160],
        full_name_kz = (request.form.get('full_name_kz') or '')[:160] or None,
        iin          = (request.form.get('iin') or '')[:12] or None,
        position_ru  = (request.form.get('position_ru') or '')[:160] or None,
        position_kz  = (request.form.get('position_kz') or '')[:160] or None,
        department   = (request.form.get('department') or '')[:120] or None,
        hire_date    = _parse_date('hire_date'),
        contract_number = (request.form.get('contract_number') or '')[:64] or None,
        contract_date   = _parse_date('contract_date'),
        contract_end    = _parse_date('contract_end'),
        probation_months = probation_months,
        schedule     = (request.form.get('schedule') or '')[:16] or None,
        status       = 'candidate',
        vacation_entitled = request.form.get('vacation_entitled', type=int) or 24,
        phone        = (request.form.get('phone') or '')[:32] or None,
        email        = (request.form.get('email') or '')[:120] or None,
    )
    db.session.add(emp)
    db.session.flush()

    doc = Document(
        doc_type   = 'hr_order',
        title      = f'О приёме на работу — {emp.full_name_ru}'[:256],
        purpose    = request.form.get('basis') or 'Заявление о приёме на работу',
        department = emp.department,
        case_index = (request.form.get('case_index') or '')[:64] or None,
        author_id  = current_user.id,
        executor_id = current_user.id,
        status     = 'pending' if action == 'submit' else 'draft',
        current_step = 0,
    )
    db.session.add(doc)
    db.session.flush()
    doc.generate_number()

    detail = HROrderDetail(
        document_id = doc.id,
        category    = 'ls',
        order_kind  = 'hire',
        effective_date = emp.hire_date,
        fields_json = json.dumps({
            'full_name_kz': emp.full_name_kz, 'position_ru': emp.position_ru,
            'position_kz': emp.position_kz, 'schedule': emp.schedule,
            'vid_priema': request.form.get('vid_priema'),
            'work_start': request.form.get('work_start'),
            'contract_number': emp.contract_number,
            'contract_signed': request.form.get('contract_signed'),
            'probation_text': probation_text,
            'statement': request.form.get('statement'),
        }, ensure_ascii=False),
    )
    db.session.add(detail)
    db.session.flush()
    db.session.add(HROrderEmployee(detail_id=detail.id, employee_id=emp.id))

    # Получатели (kind='execute', напр. бухгалтерия) и Список ознакомления
    # (kind='acknowledge') — два отдельных поля, как в Documentolog.
    seen = set()
    for field, kind in (('recipient_ids[]', 'execute'),
                        ('acknowledge_ids[]', 'acknowledge')):
        for rid in request.form.getlist(field):
            if rid.strip().isdigit() and int(rid) not in seen \
                    and db.session.get(User, int(rid)):
                seen.add(int(rid))
                db.session.add(DocumentRecipient(document_id=doc.id,
                                                 user_id=int(rid),
                                                 status='pending', kind=kind))

    _build_route(doc, action, signatory_id)
    _save_form_attachments(doc)

    db.session.add(DocumentComment(
        document_id=doc.id, author_id=current_user.id,
        text=(f'Приказ о приёме ({emp.full_name_ru}) '
              f'{"отправлен на согласование" if action == "submit" else "сохранён как проект"} '
              f'пользователем {current_user.full_name}.'),
        is_system=True))
    log_action('hr_hire_created', 'employee', emp.id, details=emp.full_name_ru)
    db.session.commit()

    if action == 'submit':
        _notify_approvers(doc)
        db.session.commit()

    flash(f'Приказ {doc.doc_number} создан. Карточка сотрудника — статус «Кандидат» '
          f'до регистрации приказа.', 'success')
    return redirect(url_for('documents.view', doc_id=doc.id))


# ── ОСТАЛЬНЫЕ КАДРОВЫЕ ПРИКАЗЫ (фаза 2) — единая форма по спецификации ───────

@hr.route('/order/new')
@login_required
@requires_permission('hr')
def order_picker():
    """Витрина видов приказов, сгруппированных по категориям."""
    groups = {}
    for kind, spec in ORDER_SPECS.items():
        groups.setdefault(spec['category'], []).append((kind, spec))
    return render_template('hr/order_picker.html', groups=groups,
                           categories=HR_ORDER_CATEGORIES)


@hr.route('/order/<kind>/new', methods=['GET'])
@login_required
@requires_permission('hr')
def order_new(kind):
    spec = ORDER_SPECS.get(kind)
    if spec is None:
        abort(404)
    users = User.query.filter_by(is_active=True)\
                      .order_by(User.first_name, User.last_name).all()
    return render_template('hr/order_new.html', kind=kind, spec=spec,
                           users=users, employees=_pickable_employees())


@hr.route('/order/<kind>/submit', methods=['POST'])
@login_required
@requires_permission('hr')
def order_submit(kind):
    spec = ORDER_SPECS.get(kind)
    if spec is None:
        abort(404)

    action = request.form.get('action', 'draft')
    signatory_id = request.form.get('signatory_id', type=int)
    emp = db.session.get(Employee, request.form.get('employee_id', type=int) or 0)
    if emp is None:
        flash('Выберите сотрудника, к которому относится приказ.', 'warning')
        return redirect(url_for('hr.order_new', kind=kind))
    if action == 'submit' and not signatory_id:
        action = 'draft'
        flash('Приказ сохранён как проект: не выбран подписывающий (ГД).', 'warning')

    # значения полей по спецификации → fields_json
    fields = {}
    for f in spec['fields']:
        fields[f['name']] = (request.form.get(f['name']) or '').strip() or None

    effective_date = _parse_date_value(fields.get(spec.get('effective_field')))

    doc = Document(
        doc_type   = 'hr_order',
        title      = f'{spec["label"]} — {emp.full_name_ru}'[:256],
        purpose    = fields.get('basis') or spec['label'],
        department = emp.department,
        case_index = (request.form.get('case_index') or '')[:64] or None,
        author_id  = current_user.id,
        executor_id = current_user.id,
        status     = 'pending' if action == 'submit' else 'draft',
        current_step = 0,
    )
    db.session.add(doc)
    db.session.flush()
    doc.generate_number()

    detail = HROrderDetail(
        document_id = doc.id,
        category    = spec['category'],
        order_kind  = kind,
        effective_date = effective_date,
        fields_json = json.dumps(fields, ensure_ascii=False),
    )
    db.session.add(detail)
    db.session.flush()
    db.session.add(HROrderEmployee(detail_id=detail.id, employee_id=emp.id))

    # Получатели (исполнение) + Список ознакомления — как в приёме
    seen = set()
    for field, rkind in (('recipient_ids[]', 'execute'),
                         ('acknowledge_ids[]', 'acknowledge')):
        for rid in request.form.getlist(field):
            if rid.strip().isdigit() and int(rid) not in seen \
                    and db.session.get(User, int(rid)):
                seen.add(int(rid))
                db.session.add(DocumentRecipient(document_id=doc.id,
                                                 user_id=int(rid),
                                                 status='pending', kind=rkind))

    _build_route(doc, action, signatory_id)
    _save_form_attachments(doc)

    db.session.add(DocumentComment(
        document_id=doc.id, author_id=current_user.id,
        text=(f'{spec["label"]} ({emp.full_name_ru}) '
              f'{"отправлен на согласование" if action == "submit" else "сохранён как проект"} '
              f'пользователем {current_user.full_name}.'),
        is_system=True))
    log_action('hr_order_created', 'document', doc.id,
               details=f'{kind}:{emp.full_name_ru}')
    db.session.commit()

    if action == 'submit':
        _notify_approvers(doc)
        db.session.commit()

    flash(f'{spec["label"]} {doc.doc_number} создан. '
          f'После подписи ГД — регистрация в журнале приказов.', 'success')
    return redirect(url_for('documents.view', doc_id=doc.id))


# ── ЖУРНАЛ ПРИКАЗОВ + РУЧНАЯ РЕГИСТРАЦИЯ ─────────────────────────────────────

@hr.route('/orders')
@login_required
@requires_permission('hr')
def orders():
    details = (HROrderDetail.query.join(Document)
               .order_by(Document.created_at.desc()).all())
    unregistered = [d for d in details
                    if d.reg_number is None and d.document.status == 'approved']
    registered = [d for d in details if d.reg_number is not None]
    return render_template('hr/orders.html', unregistered=unregistered,
                           registered=registered, now=datetime.utcnow(),
                           kinds=HR_ORDER_KINDS, categories=HR_ORDER_CATEGORIES)


@hr.route('/orders/<int:doc_id>/register', methods=['POST'])
@login_required
@requires_permission('hr')
def register_order(doc_id):
    doc = Document.query.get_or_404(doc_id)
    detail = doc.hr_detail
    if detail is None or doc.status != 'approved' or detail.reg_number:
        flash('Этот приказ нельзя зарегистрировать (не подписан или уже '
              'зарегистрирован).', 'warning')
        return redirect(url_for('hr.orders'))

    reg_number = (request.form.get('reg_number') or '').strip()[:32]
    reg_date = _parse_date('reg_date')
    if not reg_number or not reg_date:
        flash('Укажите номер и дату регистрации (дата задним числом допустима).',
              'warning')
        return redirect(url_for('hr.orders'))

    detail.reg_number = reg_number
    detail.reg_date = reg_date
    doc.registered_at = datetime.utcnow()

    # Кадровые эффекты по виду приказа (единый диспетчер)
    for link in detail.employees.all():
        _apply_order_effect(detail, link.employee, reg_date)

    # Обязательное правило: приказ направляется в бухгалтерию
    for acc in User.query.filter_by(role='accountant', is_active=True).all():
        db.session.add(Notification(
            user_id=acc.id,
            title=f'Приказ {reg_number} зарегистрирован (в бухгалтерию)',
            body=(doc.title or '')[:100],
            link=f'/documents/{doc.id}', is_read=False))

    # Ознакомление
    acks = DocumentRecipient.query.filter_by(document_id=doc.id,
                                             status='pending').all()
    if acks:
        doc.status = 'in_execution'
        for r in acks:
            db.session.add(Notification(
                user_id=r.user_id,
                title=f'Ознакомьтесь с приказом {reg_number}',
                body=(doc.title or '')[:100],
                link=f'/documents/{doc.id}', is_read=False))
    else:
        doc.status = 'executed'

    db.session.add(DocumentComment(
        document_id=doc.id, author_id=current_user.id,
        text=(f'Приказ зарегистрирован: {reg_number} от '
              f'{reg_date.strftime("%d.%m.%Y")} ({current_user.full_name}). '
              f'Направлен в бухгалтерию.'
              + (' Отправлен на ознакомление.' if acks else '')),
        is_system=True))
    log_action('hr_order_registered', 'document', doc.id, details=reg_number)
    db.session.commit()
    flash(f'Приказ {reg_number} зарегистрирован.', 'success')
    return redirect(url_for('hr.orders'))
