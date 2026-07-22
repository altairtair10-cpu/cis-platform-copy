"""HR-процессы (фаза 11 дорожной карты): кадровый резерв, оффбординг
(обходной лист при увольнении), KPI сотрудника.

Ротация реализуется приказом «Перевод» (фаза 2) — отдельной сущности не
требуется. Развитие сотрудника отражается обучением (фаза 9) и KPI ниже.
"""
from datetime import datetime
from flask import render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from app import db
from app.models import Employee, OffboardingItem, EmployeeKpi
from app.decorators import requires_permission
from app.audit import log_action
from . import hr

# Стандартный обходной лист при увольнении (создаётся по кнопке)
DEFAULT_OFFBOARDING = [
    'Сдача пропуска',
    'Сдача техники (ноутбук, телефон, СИЗ)',
    'Передача дел и документов',
    'Закрытие доступов в системах',
    'Обходной лист подписан бухгалтерией',
    'Окончательный расчёт',
]


@hr.route('/reserve')
@login_required
@requires_permission('hr')
def talent_reserve():
    staff = (Employee.query.filter_by(in_talent_reserve=True)
             .order_by(Employee.full_name_ru).all())
    return render_template('hr/reserve.html', staff=staff)


@hr.route('/employees/<int:emp_id>/reserve-toggle', methods=['POST'])
@login_required
@requires_permission('hr')
def reserve_toggle(emp_id):
    emp = Employee.query.get_or_404(emp_id)
    emp.in_talent_reserve = not emp.in_talent_reserve
    log_action('reserve_toggle', 'employee', emp.id,
               details=str(emp.in_talent_reserve))
    db.session.commit()
    flash('Кадровый резерв обновлён.', 'success')
    return redirect(url_for('hr.employee_card', emp_id=emp.id))


@hr.route('/employees/<int:emp_id>/offboarding/start', methods=['POST'])
@login_required
@requires_permission('hr')
def offboarding_start(emp_id):
    emp = Employee.query.get_or_404(emp_id)
    if emp.offboarding_items.count() == 0:
        for text in DEFAULT_OFFBOARDING:
            db.session.add(OffboardingItem(employee_id=emp.id, text=text))
        log_action('offboarding_started', 'employee', emp.id)
        db.session.commit()
        flash('Обходной лист создан.', 'success')
    else:
        flash('Обходной лист уже создан.', 'info')
    return redirect(url_for('hr.employee_card', emp_id=emp.id) + '#offboarding')


@hr.route('/offboarding/item/<int:item_id>/toggle', methods=['POST'])
@login_required
@requires_permission('hr')
def offboarding_toggle(item_id):
    item = OffboardingItem.query.get_or_404(item_id)
    item.done = not item.done
    item.done_at = datetime.utcnow() if item.done else None
    db.session.commit()
    return redirect(url_for('hr.employee_card',
                            emp_id=item.employee_id) + '#offboarding')


@hr.route('/employees/<int:emp_id>/kpi/add', methods=['POST'])
@login_required
@requires_permission('hr')
def kpi_add(emp_id):
    emp = Employee.query.get_or_404(emp_id)
    metric = (request.form.get('metric') or '').strip()
    if not metric:
        flash('Укажите показатель.', 'warning')
        return redirect(url_for('hr.employee_card', emp_id=emp.id) + '#kpi')
    db.session.add(EmployeeKpi(
        employee_id = emp.id,
        period      = (request.form.get('period') or '')[:32] or None,
        metric      = metric[:160],
        value       = (request.form.get('value') or '')[:64] or None,
    ))
    log_action('kpi_add', 'employee', emp.id, details=metric)
    db.session.commit()
    flash('Показатель добавлен.', 'success')
    return redirect(url_for('hr.employee_card', emp_id=emp.id) + '#kpi')
