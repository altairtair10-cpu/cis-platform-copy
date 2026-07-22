"""Заявления сотрудников (self-service, фаза 6 дорожной карты).

Сотрудник под своим логином подаёт заявление (отпуск / матпомощь / смена
личных данных / прочее) → заявление уходит его руководителю на согласование
(общий движок согласования) → после согласования кадровик создаёт на его
основании приказ (механизм «на основании», фаза 5).

Заявление = Document(doc_type='employee_request', sub_type=<вид>). Отдельная
таблица не нужна — переиспользуем документо-центричный движок.
"""
from datetime import datetime
from flask import render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from app import db
from app.models import (Document, DocumentComment, DocumentApproval, User,
                        Notification, Employee, EMPLOYEE_REQUEST_KINDS)
from app.audit import log_action
from app.blueprints.documents.helpers import _save_form_attachments
from . import hr


def _my_employee():
    """Карточка сотрудника, привязанная к текущему пользователю (если есть)."""
    return Employee.query.filter_by(user_id=current_user.id).first()


def _manager_user_for(emp):
    """Пользователь-руководитель для маршрутизации заявления.
    Приоритет: руководитель по карточке → иначе первый директор/HR."""
    if emp and emp.manager and emp.manager.user_id:
        u = db.session.get(User, emp.manager.user_id)
        if u and u.is_active:
            return u
    for role in ('director', 'hr', 'it_admin'):
        u = User.query.filter_by(role=role, is_active=True).first()
        if u:
            return u
    return None


@hr.route('/requests')
@login_required
def my_requests():
    """Мои заявления (для любого сотрудника) + очередь согласованных (для HR)."""
    mine = (Document.query
            .filter_by(doc_type='employee_request', author_id=current_user.id)
            .order_by(Document.created_at.desc()).all())
    to_convert = []
    if current_user.can_access('hr'):
        to_convert = (Document.query
                      .filter_by(doc_type='employee_request', status='approved')
                      .order_by(Document.created_at.desc()).all())
    return render_template('hr/requests.html', mine=mine,
                           to_convert=to_convert, kinds=EMPLOYEE_REQUEST_KINDS)


@hr.route('/requests/new', methods=['GET'])
@login_required
def request_new():
    kind = request.args.get('kind', 'leave')
    if kind not in EMPLOYEE_REQUEST_KINDS:
        kind = 'leave'
    return render_template('hr/request_new.html', kind=kind,
                           kinds=EMPLOYEE_REQUEST_KINDS)


@hr.route('/requests/submit', methods=['POST'])
@login_required
def request_submit():
    kind = request.form.get('kind', 'leave')
    if kind not in EMPLOYEE_REQUEST_KINDS:
        kind = 'leave'
    summary = (request.form.get('summary') or '').strip()
    details = (request.form.get('details') or '').strip()
    if not summary:
        flash('Укажите суть заявления.', 'warning')
        return redirect(url_for('hr.request_new', kind=kind))

    emp = _my_employee()
    manager = _manager_user_for(emp)

    doc = Document(
        doc_type   = 'employee_request',
        sub_type   = kind,
        title      = f'{EMPLOYEE_REQUEST_KINDS[kind]} — {current_user.full_name}'[:256],
        purpose    = summary,
        body_html  = details or None,
        department = current_user.department,
        author_id  = current_user.id,
        executor_id = current_user.id,
        related_employee_id = emp.id if emp else None,
        status     = 'pending' if manager else 'approved',
        current_step = 0,
    )
    # даты (для заявления на отпуск)
    period_from = request.form.get('period_from')
    if period_from:
        try:
            doc.needed_by = datetime.strptime(period_from, '%Y-%m-%d').date()
        except ValueError:
            pass
    db.session.add(doc)
    db.session.flush()
    doc.generate_number()

    if manager:
        db.session.add(DocumentApproval(document_id=doc.id,
                                        approver_id=manager.id,
                                        step=0, status='pending'))
        db.session.add(Notification(
            user_id=manager.id,
            title=f'Заявление на согласование: {doc.doc_number}',
            body=(doc.title or '')[:100],
            link=f'/documents/{doc.id}', is_read=False))

    db.session.add(DocumentComment(
        document_id=doc.id, author_id=current_user.id,
        text=(f'Заявление подано ({current_user.full_name})'
              + (f'. На согласование: {manager.full_name}.' if manager
                 else ' — руководитель не найден, направлено сразу в кадры.')),
        is_system=True))
    _save_form_attachments(doc)
    log_action('employee_request_created', 'document', doc.id, details=kind)
    db.session.commit()

    flash(f'Заявление {doc.doc_number} подано'
          + (' и направлено руководителю на согласование.' if manager
             else '.'), 'success')
    return redirect(url_for('documents.view', doc_id=doc.id))
