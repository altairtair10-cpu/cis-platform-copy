"""Аттестация и оценка (фаза 10 дорожной карты).

Инициирование → комиссия → протокол → результат → рекомендация → повторная
проверка при необходимости. Результаты отображаются в карточке сотрудника и
в HR-аналитике (предстоящие аттестации по recheck_date).
"""
from datetime import datetime
from flask import render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from app import db
from app.models import Employee, Attestation
from app.decorators import requires_permission
from app.audit import log_action
from . import hr

ATT_RESULTS = ['Соответствует занимаемой должности',
               'Условно соответствует',
               'Не соответствует занимаемой должности']


def _parse_date(name):
    raw = request.form.get(name)
    if not raw:
        return None
    try:
        return datetime.strptime(raw, '%Y-%m-%d').date()
    except ValueError:
        return None


@hr.route('/attestation')
@login_required
@requires_permission('hr')
def attestation_list():
    records = (Attestation.query.join(Employee)
               .order_by(Attestation.id.desc()).all())
    return render_template('hr/attestation.html', records=records)


@hr.route('/attestation/<int:emp_id>/new', methods=['GET'])
@login_required
@requires_permission('hr')
def attestation_new(emp_id):
    emp = Employee.query.get_or_404(emp_id)
    return render_template('hr/attestation_new.html', emp=emp,
                           results=ATT_RESULTS)


@hr.route('/attestation/<int:emp_id>/create', methods=['POST'])
@login_required
@requires_permission('hr')
def attestation_create(emp_id):
    emp = Employee.query.get_or_404(emp_id)
    att = Attestation(
        employee_id   = emp.id,
        att_date      = _parse_date('att_date'),
        commission    = (request.form.get('commission') or '').strip() or None,
        protocol_number = (request.form.get('protocol_number') or '')[:64] or None,
        result        = (request.form.get('result') or '').strip() or None,
        recommendation = (request.form.get('recommendation') or '').strip() or None,
        recheck_date  = _parse_date('recheck_date'),
    )
    db.session.add(att)
    log_action('attestation_created', 'employee', emp.id, details=emp.full_name_ru)
    db.session.commit()
    flash('Аттестация сохранена.', 'success')
    return redirect(url_for('hr.employee_card', emp_id=emp.id) + '#attestation')
