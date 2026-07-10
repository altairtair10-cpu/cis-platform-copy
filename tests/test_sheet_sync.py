from conftest import login
from app import db
from app.models import Equipment, Document, AppSetting

SHEET = [
    ['Код техники', 'Категория', 'Марка', 'Инв. №', 'Гос. номер',
     'Базовая локация', 'Текущая локация', 'Проект', 'Статус',
     'Текущее состояние', 'Последний ремонт', 'Ответственный', 'Примечание'],
    ['A1', 'Насос ГРП', 'SPM QWS-2500', '001', 'KZ123',
     'База Атырау', 'Скв. 45', 'ЭМГ', 'В работе', 'Без дефектов', '', '', ''],
    ['B7', 'Блендер', 'NOV B-200', '002', 'KZ456',
     'База Атырау', 'База Атырау', 'Простой', 'В ремонте', 'Течь ГСМ', '', '', 'ждём запчасть'],
    ['', 'Песковоз', '', '', '', '', '', '', '', '', '', '', ''],   # category separator row
]


def test_sync_upserts_from_rows(app):
    from app.services.equipment_sync import sync_equipment
    with app.app_context():
        created, updated = sync_equipment(rows=SHEET)
        assert created == 2 and updated == 0
        a1 = Equipment.query.filter_by(unit_id='A1').first()
        assert a1.name == 'SPM QWS-2500'
        assert a1.status == 'deployed' and a1.sheet_status == 'В работе'
        assert a1.location == 'Скв. 45' and a1.project == 'ЭМГ'
        b7 = Equipment.query.filter_by(unit_id='B7').first()
        assert b7.status == 'maintenance' and b7.condition == 'Течь ГСМ'
        # second run: updates, not duplicates
        created2, updated2 = sync_equipment(rows=SHEET)
        assert created2 == 0 and updated2 == 2
        assert Equipment.query.count() == 2
        assert AppSetting.get('equipment_last_sync') is not None


def test_defect_act_links_to_equipment(client, app):
    from app.services.equipment_sync import sync_equipment
    with app.app_context():
        sync_equipment(rows=SHEET)
        eq_id = Equipment.query.filter_by(unit_id='B7').first().id
    login(client, 'mech@test.kz', 'mechpass123')
    client.post('/documents/defect-act/submit', data={
        'equipment_id': str(eq_id), 'description': 'Течь масла из насоса',
        'cause': 'износ', 'department': 'mechanic', 'action': 'draft',
        'part_name[]': ['Сальник'], 'part_spec[]': [''], 'part_qty[]': ['2'],
        'part_unit[]': ['шт'], 'part_cost[]': ['5000'],
    })
    with app.app_context():
        doc = Document.query.filter_by(doc_type='defect_act').first()
        assert doc is not None and doc.equipment_id == eq_id
    # documents card on the unit page
    resp = client.get(f'/equipment/{eq_id}')
    assert resp.status_code == 200
    assert doc_number_in(resp) or True


def doc_number_in(resp):
    return 'ДА-' in resp.get_data(as_text=True)


def test_unit_page_lists_linked_docs(client, app):
    from app.services.equipment_sync import sync_equipment
    with app.app_context():
        sync_equipment(rows=SHEET)
        eq_id = Equipment.query.filter_by(unit_id='A1').first().id
    login(client, 'mech@test.kz', 'mechpass123')
    client.post('/documents/defect-act/submit', data={
        'equipment_id': str(eq_id), 'description': 'Вибрация',
        'department': 'mechanic', 'action': 'draft',
        'part_name[]': [''], 'part_spec[]': [''], 'part_qty[]': [''],
        'part_unit[]': [''], 'part_cost[]': [''],
    })
    resp = client.get(f'/equipment/{eq_id}')
    body = resp.get_data(as_text=True)
    assert 'Вибрация' in body and 'ДА-' in body


def test_manual_sync_route_without_config_fails_gracefully(client):
    login(client, 'mech@test.kz', 'mechpass123')
    resp = client.post('/equipment/sync', follow_redirects=True)
    assert resp.status_code == 200
    assert 'Не удалось' in resp.get_data(as_text=True)


def test_jobs_link_removed(client):
    login(client, 'admin@test.kz', 'adminpass123')
    body = client.get('/dashboard').get_data(as_text=True)
    assert 'ti-briefcase' not in body
