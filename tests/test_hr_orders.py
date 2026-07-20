"""HR фаза 1: приём сотрудника — полный цикл.

Заявка → согласование → подпись ГД → ручная регистрация (№ + дата задним
числом) → карточка «Действующий» → ознакомление → «Исполнен».
Плюс: ограниченный доступ к карточкам, черновик без подписывающего.
"""
from tests.conftest import login
from app import db
from app.models import Document, Employee, HROrderDetail, Notification


def _submit_hire(client, signatory='2', action='submit', extra=None):
    data = {
        'action': action,
        'full_name_ru': 'Иванов Иван Иванович',
        'full_name_kz': 'Иванов Иван Иванұлы',
        'iin': '900101300123',
        'position_ru': 'Полевой инженер',
        'position_kz': 'Дала инженері',
        'department': 'Полевые операции',
        'hire_date': '2026-07-17',
        'schedule': '14/14',
        'contract_number': 'ТД-2026-77',
        'probation_months': '3',
        'vacation_entitled': '24',
        'basis': 'Заявление о приёме на работу',
        'signatory_id': signatory,
        'stage_reviewer[]': ['1'],
        'acknowledge_ids[]': ['3'],
    }
    if extra:
        data.update(extra)
    return client.post('/hr/hire/submit', data=data,
                       content_type='multipart/form-data',
                       follow_redirects=True)


def test_hire_full_cycle(client, app):
    login(client, 'admin@test.kz', 'adminpass123')
    r = _submit_hire(client)
    assert r.status_code == 200

    with app.app_context():
        emp = Employee.query.first()
        assert emp is not None and emp.status == 'candidate'
        assert emp.full_name_kz == 'Иванов Иван Иванұлы'
        assert emp.schedule == '14/14'
        doc = Document.query.filter_by(doc_type='hr_order').first()
        assert doc is not None and doc.status == 'pending'
        detail = doc.hr_detail
        assert detail.order_kind == 'hire' and detail.category == 'ls'
        doc_id, emp_id = doc.id, emp.id

    # согласование (admin, шаг 0) → подпись (head, шаг 1)
    client.post(f'/documents/{doc_id}/approve', data={'action': 'approve'},
                follow_redirects=True)
    login(client, 'head@test.kz', 'headpass123')
    client.post(f'/documents/{doc_id}/approve', data={'action': 'approve'},
                follow_redirects=True)

    with app.app_context():
        doc = db.session.get(Document, doc_id)
        # подписан, но НЕ зарегистрирован автоматически
        assert doc.status == 'approved'
        assert doc.hr_detail.reg_number is None
        # сотрудник всё ещё кандидат
        assert db.session.get(Employee, emp_id).status == 'candidate'

    # журнал: приказ в очереди на регистрацию
    login(client, 'admin@test.kz', 'adminpass123')
    r = client.get('/hr/orders')
    assert r.status_code == 200
    assert 'Ожидают регистрации' in r.data.decode()

    # ручная регистрация задним числом
    r = client.post(f'/hr/orders/{doc_id}/register',
                    data={'reg_number': 'ЛС-128', 'reg_date': '2026-07-17'},
                    follow_redirects=True)
    assert 'зарегистрирован' in r.data.decode()

    with app.app_context():
        doc = db.session.get(Document, doc_id)
        emp = db.session.get(Employee, emp_id)
        assert doc.hr_detail.reg_number == 'ЛС-128'
        assert str(doc.hr_detail.reg_date) == '2026-07-17'
        assert emp.status == 'active'            # Действующий
        assert str(emp.hire_date) == '2026-07-17'
        assert doc.status == 'in_execution'      # на ознакомлении (mech)
        note = Notification.query.filter(
            Notification.user_id == 3,
            Notification.title.like('%Ознакомьтесь%')).first()
        assert note is not None

    # ознакомление получателем → Исполнен
    login(client, 'mech@test.kz', 'mechpass123')
    client.post(f'/documents/{doc_id}/recipient-done', data={},
                follow_redirects=True)
    with app.app_context():
        assert db.session.get(Document, doc_id).status == 'executed'


def test_hire_without_signatory_stays_draft(client, app):
    login(client, 'admin@test.kz', 'adminpass123')
    _submit_hire(client, signatory='', action='submit')
    with app.app_context():
        doc = Document.query.filter_by(doc_type='hr_order').first()
        assert doc.status == 'draft'


def test_employee_card_restricted(client, app):
    login(client, 'admin@test.kz', 'adminpass123')
    _submit_hire(client)
    with app.app_context():
        emp_id = Employee.query.first().id

    # it_admin — в списке допущенных ролей
    assert client.get(f'/hr/employees/{emp_id}').status_code == 200

    # механик — карточки закрыты
    login(client, 'mech@test.kz', 'mechpass123')
    assert client.get(f'/hr/employees/{emp_id}').status_code == 403


def test_journal_requires_hr_permission(client):
    login(client, 'mech@test.kz', 'mechpass123')
    r = client.get('/hr/orders')
    assert r.status_code in (302, 403)
