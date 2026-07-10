from conftest import login
from app import db
from app.models import Equipment, Document


def _make_pump(app, unit_id='Б1'):
    with app.app_context():
        eq = Equipment(unit_id=unit_id, name='Насос', eq_type='Насос ГРП',
                       gos_number='882 AHDE 06')
        db.session.add(eq); db.session.commit()
        return eq.id


def _submit_defect(client, eq_id, desc='Течь клапана'):
    return client.post('/documents/defect-act/submit', data={
        'equipment_id': str(eq_id), 'description': desc, 'department': 'mechanic',
        'action': 'draft', 'part_name[]': [''], 'part_spec[]': [''],
        'part_qty[]': [''], 'part_unit[]': [''], 'part_cost[]': [''],
    }, follow_redirects=True)


def test_event_codes_sequential_per_unit(client, app):
    eq_id = _make_pump(app)
    login(client, 'mech@test.kz', 'mechpass123')
    _submit_defect(client, eq_id, 'Первый')
    _submit_defect(client, eq_id, 'Второй')
    with app.app_context():
        codes = [d.event_code for d in
                 Document.query.filter_by(doc_type='defect_act').order_by(Document.id)]
        assert codes == ['Б1-ДА1', 'Б1-ДА2']


def test_open_defect_shown_on_unit_page(client, app):
    eq_id = _make_pump(app)
    login(client, 'mech@test.kz', 'mechpass123')
    _submit_defect(client, eq_id)
    body = client.get(f'/equipment/{eq_id}').get_data(as_text=True)
    assert 'Б1-ДА1' in body and 'Открытые дефекты' in body


def test_manual_close(client, app):
    eq_id = _make_pump(app)
    login(client, 'mech@test.kz', 'mechpass123')
    _submit_defect(client, eq_id)
    with app.app_context():
        doc_id = Document.query.filter_by(doc_type='defect_act').first().id
    client.post(f'/documents/{doc_id}/close-defect')
    with app.app_context():
        doc = db.session.get(Document, doc_id)
        assert doc.defect_closed is True
    body = client.get(f'/equipment/{eq_id}').get_data(as_text=True)
    assert 'Открытые дефекты' not in body


def test_register_repair_autocloses_defect(client, app):
    from app.services.maintenance_sync import sync_maintenance
    eq_id = _make_pump(app)
    login(client, 'mech@test.kz', 'mechpass123')
    _submit_defect(client, eq_id)
    register = {'№1 Насос 882AHDE ': [
        ['№1 Насос 882AHDE', '', 'инв № 306'],
        ['Дата', 'Вид обслуживания (ТО, Р)', 'Основание', 'Оценка', 'Описание  работы',
         'Пробег /Моточас'],
        ['1', '2', '3', '4', '5', '6'],
        ['12.07.2026', 'Р', 'дефектный акт', 'рабочее',
         'Замена клапана по Б1-ДефА1-Р', '13300'],
    ]}
    with app.app_context():
        sync_maintenance(register=register)
        doc = Document.query.filter_by(doc_type='defect_act').first()
        assert doc.defect_closed is True
        assert doc.defect_closed_at is not None


def test_requisition_links_to_defect(client, app):
    eq_id = _make_pump(app)
    login(client, 'mech@test.kz', 'mechpass123')
    _submit_defect(client, eq_id)
    with app.app_context():
        defect = Document.query.filter_by(doc_type='defect_act').first()
        defect_id, code = defect.id, defect.event_code
    # GET prefilled form shows the code
    body = client.get(f'/documents/trebovanie/new?from_defect={defect_id}').get_data(as_text=True)
    assert code in body
    # POST stores the FK
    client.post('/documents/trebovanie/submit', data={
        'summary': 'Клапан для ремонта', 'urgency': 'standard', 'action': 'draft',
        'related_defect_id': str(defect_id),
        'item_name[]': ['Клапан ИМЗ'], 'item_unit[]': ['шт'], 'item_qty[]': ['3'],
        'item_note[]': [''], 'item_cost[]': ['100000'],
    })
    with app.app_context():
        req = Document.query.filter_by(doc_type='purchase_req').first()
        assert req is not None and req.related_defect_id == defect_id
    # requisition page shows the link
    with app.app_context():
        req_id = Document.query.filter_by(doc_type='purchase_req').first().id
    body = client.get(f'/documents/{req_id}').get_data(as_text=True)
    assert code in body


def test_log_form_removed_from_unit_page(client, app):
    eq_id = _make_pump(app)
    login(client, 'mech@test.kz', 'mechpass123')
    body = client.get(f'/equipment/{eq_id}').get_data(as_text=True)
    assert 'Записать ТО' not in body
