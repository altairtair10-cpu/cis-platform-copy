"""Адаптация и онбординг (фаза 8 дорожной карты).

После приёма сотруднику назначают наставника и план адаптации с контрольными
точками; по итогам — «пройдена / не пройдена» (испытательный срок). План и его
прогресс отображаются в единой карточке сотрудника.
"""
from datetime import datetime
from flask import render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from app import db
from app.models import (Employee, User, AdaptationPlan, AdaptationItem,
                        Notification)
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


@hr.route('/adaptation/<int:emp_id>/new', methods=['GET'])
@login_required
@requires_permission('hr')
def adaptation_new(emp_id):
    emp = Employee.query.get_or_404(emp_id)
    users = (User.query.filter_by(is_active=True)
             .order_by(User.first_name, User.last_name).all())
    return render_template('hr/adaptation_new.html', emp=emp, users=users)


@hr.route('/adaptation/<int:emp_id>/create', methods=['POST'])
@login_required
@requires_permission('hr')
def adaptation_create(emp_id):
    emp = Employee.query.get_or_404(emp_id)
    plan = AdaptationPlan(
        employee_id = emp.id,
        mentor_id   = request.form.get('mentor_id', type=int) or None,
        start_date  = _parse_date('start_date'),
        end_date    = _parse_date('end_date'),
        status      = 'active',
    )
    db.session.add(plan)
    db.session.flush()

    # контрольные точки — по одной на непустую строку textarea
    for line in (request.form.get('items') or '').splitlines():
        text = line.strip()
        if text:
            db.session.add(AdaptationItem(plan_id=plan.id, text=text[:256]))

    if plan.mentor_id:
        db.session.add(Notification(
            user_id=plan.mentor_id,
            title=f'Вы назначены наставником: {emp.full_name_ru}',
            body='План адаптации создан.',
            link=url_for('hr.employee_card', emp_id=emp.id), is_read=False))

    log_action('adaptation_created', 'employee', emp.id, details=emp.full_name_ru)
    db.session.commit()
    flash('План адаптации создан.', 'success')
    return redirect(url_for('hr.employee_card', emp_id=emp.id))


@hr.route('/adaptation/item/<int:item_id>/toggle', methods=['POST'])
@login_required
@requires_permission('hr')
def adaptation_item_toggle(item_id):
    item = AdaptationItem.query.get_or_404(item_id)
    item.done = not item.done
    item.done_at = datetime.utcnow() if item.done else None
    db.session.commit()
    return redirect(url_for('hr.employee_card',
                            emp_id=item.plan.employee_id) + '#adaptation')


@hr.route('/adaptation/<int:plan_id>/complete', methods=['POST'])
@login_required
@requires_permission('hr')
def adaptation_complete(plan_id):
    plan = AdaptationPlan.query.get_or_404(plan_id)
    result = request.form.get('result')
    if result not in ('passed', 'failed'):
        flash('Укажите итог адаптации.', 'warning')
        return redirect(url_for('hr.employee_card', emp_id=plan.employee_id))
    plan.status = result
    plan.result_note = (request.form.get('result_note') or '').strip() or None
    log_action('adaptation_completed', 'employee', plan.employee_id, details=result)
    db.session.commit()
    flash('Итог адаптации сохранён.', 'success')
    return redirect(url_for('hr.employee_card', emp_id=plan.employee_id))
