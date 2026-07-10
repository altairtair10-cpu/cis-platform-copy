from conftest import login
from app import db
from app.models import (Equipment, ServiceRecord, MaintenancePolicy,
                        Notification, User, AppSetting)

HEADER = ['Дата', 'Вид обслуживания (ТО, Р)', 'Основание/причина', 'Оценка', 'Описание  работы',
          'Пробег /\nМоточас', 'Дата', 'Окончания', 'Длит.', 'Мото-часы', 'старое', 'новое',
          'Номер', 'Оценка после', 'Комментарий', 'ФИО, должность исполнителя', 'контролирующий']

REGISTER = {
    '№1 Насос 882AHDE ': [
        ['', '', '', 'ТОО «CIS»'],
        ['№1 Насос 882AHDE', '', 'инв № 306', '', 'модель ALATAU-31'],
        HEADER,
        ['', '', '', '', '', '', '', '', '', '', 'P/N', 'P/N'],
        ['1', '2', '3', '4', '5', '6', '7', '8', '9', '10', '11', '12', '13', '14', '15', '16', '17'],
        ['06.11.2024', 'ТО 1', 'Руководство', 'рабочее', 'Замена масла', '12797', '06.11.2024',
         '', '', 'НП', '', '', '', 'годен', '', 'Нуркуатов.А', ''],
        ['21.04.2025', 'Р', 'информация', 'рабочее', 'Замена форсунок', 'НП', '', '', '', 'НП',
         '', '', '', '', '', 'Нуркуатов.А', ''],
        ['17.08.2025', 'Р', 'информация', 'рабочее', 'Замена седла', '13250', '', '', '', 'НП',
         '', '', '', '', '', 'Нуркуатов.А', ''],
    ],
    'Неизвестная машина': [HEADER],
}


def _make_pump(app):
    with app.app_context():
        eq = Equipment(unit_id='A1', name='SPM', eq_type='Насос ГРП', gos_number='882AHDE')
        db.session.add(eq)
        db.session.add(MaintenancePolicy(eq_type='Насос ГРП', mode='hours', interval=400))
        db.session.commit()
        return eq.id


def test_register_sync_and_aggregates(app):
    from app.services.maintenance_sync import sync_maintenance
    eq_id = _make_pump(app)
    with app.app_context():
        new, matched, unmatched = sync_maintenance(register=REGISTER)
        assert new == 3 and matched == 1 and unmatched == ['Неизвестная машина']
        eq = db.session.get(Equipment, eq_id)
        assert eq.current_reading == 13250.0
        assert eq.last_to_reading == 12797.0
        assert eq.last_to_date.isoformat() == '2024-11-06'
        assert eq.last_repair_date.isoformat() == '2025-08-17'
        kinds = {r.kind for r in ServiceRecord.query.all()}
        assert kinds == {'ТО', 'Р'}
        # idempotent
        new2, _, _ = sync_maintenance(register=REGISTER)
        assert new2 == 0 and ServiceRecord.query.count() == 3


def test_due_notification_mechanics_and_extras(app):
    from app.services.maintenance_sync import sync_maintenance, check_maintenance_due
    eq_id = _make_pump(app)
    with app.app_context():
        sync_maintenance(register=REGISTER)   # used = 13250-12797 = 453 >= 400 -> due
        head = User.query.filter_by(email='head@test.kz').first()
        AppSetting.set('maintenance_notify_user_ids', str(head.id))
        db.session.commit()
        due = check_maintenance_due()
        assert len(due) == 1 and due[0][0].id == eq_id
        mech = User.query.filter_by(email='mech@test.kz').first()
        assert Notification.query.filter_by(user_id=mech.id).count() == 1
        assert Notification.query.filter_by(user_id=head.id).count() == 1
        # no duplicate alerts on next run
        assert check_maintenance_due() == []
        # a fresh ТО resets the cycle
        eq = db.session.get(Equipment, eq_id)
        assert eq.to_notified_at is not None


def test_not_due_below_interval(app):
    from app.services.maintenance_sync import check_maintenance_due
    with app.app_context():
        eq = Equipment(unit_id='B7', name='NOV', eq_type='Насос ГРП',
                       current_reading=100, last_to_reading=0)
        db.session.add(eq)
        db.session.add(MaintenancePolicy(eq_type='Насос ГРП', mode='hours', interval=400))
        db.session.commit()
        assert check_maintenance_due() == []


def test_repair_only_never_due(app):
    from app.services.maintenance_sync import check_maintenance_due
    with app.app_context():
        eq = Equipment(unit_id='T1', name='Трал', eq_type='Тралы',
                       current_reading=99999, last_to_reading=0)
        db.session.add(eq)
        db.session.add(MaintenancePolicy(eq_type='Тралы', mode='repair_only'))
        db.session.commit()
        assert check_maintenance_due() == []


def test_unit_page_shows_register(client, app):
    from app.services.maintenance_sync import sync_maintenance
    eq_id = _make_pump(app)
    with app.app_context():
        sync_maintenance(register=REGISTER)
    login(client, 'mech@test.kz', 'mechpass123')
    body = client.get(f'/equipment/{eq_id}').get_data(as_text=True)
    assert 'Замена масла' in body and 'Замена форсунок' in body
    assert 'ТО просрочено' in body   # 453 из 400
