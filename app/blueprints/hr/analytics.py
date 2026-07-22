"""HR-аналитика (фаза 12 дорожной карты).

Только чтение: сводка по всему, что накопили предыдущие фазы — численность,
приёмы, увольнения, кто на испытательном / в отпуске / командировке / на
больничном, истекающие сертификаты, предстоящие аттестации, текучесть.
"""
from datetime import datetime, timedelta
from flask import render_template
from flask_login import login_required
from app import db
from app.models import (Employee, TrainingRecord, Attestation,
                        EMPLOYEE_STATUSES)
from app.decorators import requires_permission
from . import hr


@hr.route('/analytics')
@login_required
@requires_permission('hr')
def analytics():
    today = datetime.utcnow().date()
    year_ago = today - timedelta(days=365)
    soon = today + timedelta(days=60)

    all_emp = Employee.query.all()
    active = [e for e in all_emp if e.status != 'terminated']

    # разбивка по статусам
    by_status = {}
    for e in all_emp:
        by_status[e.status] = by_status.get(e.status, 0) + 1

    # на испытательном сроке = активные с незавершённым планом адаптации
    on_probation = 0
    for e in active:
        if any(p.status == 'active' for p in e.adaptation_plans):
            on_probation += 1

    hires_ytd = sum(1 for e in all_emp if e.hire_date and e.hire_date >= year_ago)
    terms_ytd = sum(1 for e in all_emp
                    if e.termination_date and e.termination_date >= year_ago)

    # текучесть = увольнения за год / среднесписочная (приближённо к активным)
    headcount = max(1, len(active))
    turnover = round(terms_ytd / headcount * 100, 1)

    expiring_certs = (TrainingRecord.query
                      .filter(TrainingRecord.cert_expires.isnot(None),
                              TrainingRecord.cert_expires <= soon)
                      .order_by(TrainingRecord.cert_expires).all())

    upcoming_att = (Attestation.query
                    .filter(Attestation.recheck_date.isnot(None),
                            Attestation.recheck_date >= today,
                            Attestation.recheck_date <= soon)
                    .order_by(Attestation.recheck_date).all())

    reserve = [e for e in active if e.in_talent_reserve]

    return render_template('hr/analytics.html',
                           total=len(all_emp), active=len(active),
                           by_status=by_status, statuses=EMPLOYEE_STATUSES,
                           on_probation=on_probation,
                           hires_ytd=hires_ytd, terms_ytd=terms_ytd,
                           turnover=turnover,
                           expiring_certs=expiring_certs,
                           upcoming_att=upcoming_att,
                           reserve=reserve)
