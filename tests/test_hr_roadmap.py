"""HR дорожная карта, фазы 3-12: карточка (баланс отпуска, больничный),
все приказы компании, заявления сотрудников + связь «на основании»,
адаптация, обучение/сертификаты, аттестация, резерв/оффбординг/KPI, аналитика.
"""
from tests.conftest import login
from tests.test_hr_orders import _make_active_employee, _run_order
from app import db
from app.models import (Document, Employee, HROrderDetail, AdaptationPlan,
                        AdaptationItem, TrainingRecord, Attestation,
                        OffboardingItem, EmployeeKpi)


# ── ФАЗА 3: карточка — баланс отпуска, больничный ────────────────────────────

def test_vacation_balance(client, app):
    emp_id = _make_active_employee(client, app)
    _run_order(client, app, 'vacation', emp_id, {
        'period_from': '2026-08-01', 'period_to': '2026-08-14', 'days': '14',
    }, 'О-50')
    with app.app_context():
        emp = db.session.get(Employee, emp_id)
        assert emp.vacation_days_used == 14
        assert emp.vacation_days_remaining == emp.vacation_entitled - 14


def test_sick_leave_sets_status(client, app):
    emp_id = _make_active_employee(client, app)
    _run_order(client, app, 'sick_leave', emp_id, {
        'sick_note_number': 'БЛ-7', 'period_from': '2026-08-01',
        'period_to': '2026-08-05', 'days': '5',
    }, 'ЛС-77')
    with app.app_context():
        assert db.session.get(Employee, emp_id).status == 'sick_leave'


def test_employee_card_opens(client, app):
    emp_id = _make_active_employee(client, app)
    r = client.get(f'/hr/employees/{emp_id}')
    assert r.status_code == 200
    assert 'Адаптация' in r.data.decode()


# ── ФАЗА 4: все приказы компании ────────────────────────────────────────────

def test_company_orders_page(client, app):
    emp_id = _make_active_employee(client, app)
    r = client.get('/hr/orders/all')
    assert r.status_code == 200


# ── ФАЗА 6: заявления сотрудников + связь «на основании» ─────────────────────

def test_employee_request_flow(client, app):
    login(client, 'admin@test.kz', 'adminpass123')
    r = client.post('/hr/requests/submit', data={
        'kind': 'leave', 'summary': 'Прошу отпуск', 'period_from': '2026-09-01',
    }, content_type='multipart/form-data', follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        doc = Document.query.filter_by(doc_type='employee_request').first()
        assert doc is not None and doc.sub_type == 'leave'
        doc_id = doc.id
    # руководитель (в тестах — admin) согласует
    client.post(f'/documents/{doc_id}/approve', data={'action': 'approve'},
                follow_redirects=True)
    with app.app_context():
        assert db.session.get(Document, doc_id).status == 'approved'
    # витрина «создать приказ на основании» открывается
    assert client.get(f'/hr/order/new?source={doc_id}').status_code == 200


def test_order_from_source_links_back(client, app):
    emp_id = _make_active_employee(client, app)
    # создаём заявление-источник
    login(client, 'admin@test.kz', 'adminpass123')
    client.post('/hr/requests/submit', data={
        'kind': 'financial', 'summary': 'Матпомощь',
    }, content_type='multipart/form-data', follow_redirects=True)
    with app.app_context():
        src = Document.query.filter_by(doc_type='employee_request').first()
        src_id = src.id
    # приказ «прочее» на основании заявления
    client.post('/hr/order/other/submit', data={
        'action': 'draft', 'employee_id': str(emp_id),
        'subject': 'Выплата матпомощи', 'source_document_id': str(src_id),
    }, content_type='multipart/form-data', follow_redirects=True)
    with app.app_context():
        detail = (HROrderDetail.query.filter_by(order_kind='other')
                  .order_by(HROrderDetail.id.desc()).first())
        assert detail.source_document_id == src_id


# ── ФАЗА 8: адаптация ───────────────────────────────────────────────────────

def test_adaptation_plan(client, app):
    emp_id = _make_active_employee(client, app)
    client.post(f'/hr/adaptation/{emp_id}/create', data={
        'mentor_id': '2', 'start_date': '2026-08-01', 'end_date': '2026-11-01',
        'items': 'Знакомство с командой\nИнструктаж по ОТ',
    }, follow_redirects=True)
    with app.app_context():
        plan = AdaptationPlan.query.filter_by(employee_id=emp_id).first()
        assert plan is not None
        items = plan.items.all()
        assert len(items) == 2
        item_id = items[0].id
    # отметить пункт
    client.post(f'/hr/adaptation/item/{item_id}/toggle', follow_redirects=True)
    with app.app_context():
        assert db.session.get(AdaptationItem, item_id).done is True
    # завершить план
    with app.app_context():
        plan_id = AdaptationPlan.query.filter_by(employee_id=emp_id).first().id
    client.post(f'/hr/adaptation/{plan_id}/complete',
                data={'result': 'passed'}, follow_redirects=True)
    with app.app_context():
        assert db.session.get(AdaptationPlan, plan_id).status == 'passed'


# ── ФАЗА 9: обучение и сертификаты ──────────────────────────────────────────

def test_training_and_certificate(client, app):
    emp_id = _make_active_employee(client, app)
    client.post(f'/hr/training/{emp_id}/create', data={
        'course_name': 'Промбезопасность', 'provider': 'УЦ', 'budget': '150000',
    }, follow_redirects=True)
    with app.app_context():
        rec = TrainingRecord.query.filter_by(employee_id=emp_id).first()
        assert rec is not None and rec.budget == 150000
        rec_id = rec.id
    client.post(f'/hr/training/{rec_id}/certificate', data={
        'cert_number': 'СРТ-1', 'cert_issued': '2026-08-01',
        'cert_expires': '2027-08-01',
    }, follow_redirects=True)
    with app.app_context():
        rec = db.session.get(TrainingRecord, rec_id)
        assert rec.cert_number == 'СРТ-1' and rec.status == 'completed'


# ── ФАЗА 10: аттестация ─────────────────────────────────────────────────────

def test_attestation(client, app):
    emp_id = _make_active_employee(client, app)
    client.post(f'/hr/attestation/{emp_id}/create', data={
        'att_date': '2026-08-01', 'protocol_number': 'П-1',
        'result': 'Соответствует занимаемой должности',
    }, follow_redirects=True)
    with app.app_context():
        att = Attestation.query.filter_by(employee_id=emp_id).first()
        assert att is not None and att.protocol_number == 'П-1'


# ── ФАЗА 11: резерв, оффбординг, KPI ────────────────────────────────────────

def test_talent_reserve_toggle(client, app):
    emp_id = _make_active_employee(client, app)
    client.post(f'/hr/employees/{emp_id}/reserve-toggle', follow_redirects=True)
    with app.app_context():
        assert db.session.get(Employee, emp_id).in_talent_reserve is True


def test_offboarding_checklist(client, app):
    emp_id = _make_active_employee(client, app)
    client.post(f'/hr/employees/{emp_id}/offboarding/start', follow_redirects=True)
    with app.app_context():
        items = OffboardingItem.query.filter_by(employee_id=emp_id).all()
        assert len(items) >= 1
        item_id = items[0].id
    client.post(f'/hr/offboarding/item/{item_id}/toggle', follow_redirects=True)
    with app.app_context():
        assert db.session.get(OffboardingItem, item_id).done is True


def test_kpi_add(client, app):
    emp_id = _make_active_employee(client, app)
    client.post(f'/hr/employees/{emp_id}/kpi/add', data={
        'period': 'Q1 2026', 'metric': 'Выполнение плана', 'value': '95%',
    }, follow_redirects=True)
    with app.app_context():
        assert EmployeeKpi.query.filter_by(employee_id=emp_id).count() == 1


# ── ФАЗА 12: аналитика ──────────────────────────────────────────────────────

def test_analytics_page(client, app):
    _make_active_employee(client, app)
    r = client.get('/hr/analytics')
    assert r.status_code == 200
    assert 'Текучесть' in r.data.decode()
