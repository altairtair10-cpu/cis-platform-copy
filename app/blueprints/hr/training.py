"""Обучение и развитие (фаза 9 дорожной карты).

Заявка на обучение → согласование бюджета → обучение → сертификат (с датой
выдачи и сроком действия). Сертификаты показываются в карточке сотрудника;
истекающие подсвечиваются и попадают в HR-аналитику (фаза 12).
"""
from datetime import datetime, timedelta
from flask import render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from app import db
from app.models import Employee, TrainingRecord, Notification, User
from app.decorators import requires_permission
from app.audit import log_action
from . import hr


def _parse_date(name):
    raw = request.form.get(name)
    if not raw:
        return None
    try:
        return datetime.strptime(raw, '%Y-%m-%d').date()
    except ValueError:
        return None


def _to_int(raw):
    try:
        return int(str(raw).replace(' ', ''))
    except (ValueError, TypeError):
        return None


@hr.route('/training')
@login_required
@requires_permission('hr')
def training_list():
    records = (TrainingRecord.query.join(Employee)
               .order_by(TrainingRecord.created_at.desc()).all())
    # истекающие сертификаты (в ближайшие 60 дней или уже истёкшие)
    soon = datetime.utcnow().date() + timedelta(days=60)
    expiring = [r for r in records
                if r.cert_expires and r.cert_expires <= soon]
    return render_template('hr/training.html', records=records,
                           expiring=expiring)


@hr.route('/training/<int:emp_id>/new', methods=['GET'])
@login_required
@requires_permission('hr')
def training_new(emp_id):
    emp = Employee.query.get_or_404(emp_id)
    return render_template('hr/training_new.html', emp=emp)


@hr.route('/training/<int:emp_id>/create', methods=['POST'])
@login_required
@requires_permission('hr')
def training_create(emp_id):
    emp = Employee.query.get_or_404(emp_id)
    course = (request.form.get('course_name') or '').strip()
    if not course:
        flash('Укажите название обучения.', 'warning')
        return redirect(url_for('hr.training_new', emp_id=emp.id))
    rec = TrainingRecord(
        employee_id  = emp.id,
        course_name  = course[:256],
        provider     = (request.form.get('provider') or '')[:160] or None,
        start_date   = _parse_date('start_date'),
        end_date     = _parse_date('end_date'),
        budget       = _to_int(request.form.get('budget')),
        status       = 'requested',
    )
    db.session.add(rec)
    log_action('training_created', 'employee', emp.id, details=course)
    db.session.commit()
    flash('Заявка на обучение создана.', 'success')
    return redirect(url_for('hr.employee_card', emp_id=emp.id))


@hr.route('/training/<int:rec_id>/status', methods=['POST'])
@login_required
@requires_permission('hr')
def training_status(rec_id):
    rec = TrainingRecord.query.get_or_404(rec_id)
    new_status = request.form.get('status')
    if new_status not in TrainingRecord.STATUS_DISPLAY:
        flash('Неизвестный статус.', 'warning')
        return redirect(url_for('hr.employee_card', emp_id=rec.employee_id))
    rec.status = new_status
    log_action('training_status', 'employee', rec.employee_id, details=new_status)
    db.session.commit()
    flash('Статус обучения обновлён.', 'success')
    return redirect(url_for('hr.employee_card', emp_id=rec.employee_id) + '#training')


@hr.route('/training/<int:rec_id>/certificate', methods=['POST'])
@login_required
@requires_permission('hr')
def training_certificate(rec_id):
    rec = TrainingRecord.query.get_or_404(rec_id)
    rec.cert_number  = (request.form.get('cert_number') or '')[:64] or None
    rec.cert_issued  = _parse_date('cert_issued')
    rec.cert_expires = _parse_date('cert_expires')
    rec.effectiveness = (request.form.get('effectiveness') or '')[:160] or None
    if rec.cert_number:
        rec.status = 'completed'
    log_action('training_certificate', 'employee', rec.employee_id,
               details=rec.cert_number or '')
    db.session.commit()
    flash('Сертификат сохранён.', 'success')
    return redirect(url_for('hr.employee_card', emp_id=rec.employee_id) + '#training')
