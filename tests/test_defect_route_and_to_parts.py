from conftest import login
from app import db
from app.models import Document, DocumentApproval, Equipment, ToPart, User


def _mk_eq(app):
    with app.app_context():
        eq = Equipment(unit_id='Б1', name='Насос', eq_type='Насос ГРП')
        db.session.add(eq); db.session.commit()
        return eq.id


def test_defect_act_uses_full_route(client, app):
    eq_id = _mk_eq(app)
    a_id = None
    with app.app_context():
        head = User.query.filter_by(email='head@test.kz').first()
        admin = User.query.filter_by(email='admin@test.kz').first()
        head_id, admin_id = head.id, admin.id
    login(client, 'mech@test.kz', 'mechpass123')
    client.post('/documents/defect-act/submit', data={
        'equipment_id': str(eq_id), 'description': 'Течь', 'action': 'submit',
        'signatory_id': str(head_id),
        'stage_no[]': ['1'], 'stage_type[]': ['parallel'],
        'stage_reviewer_1[]': [str(admin_id)],
        'part_name[]': [''], 'part_spec[]': [''], 'part_qty[]': [''],
        'part_unit[]': [''], 'part_cost[]': [''],
    })
    with app.app_context():
        doc = Document.query.filter_by(doc_type='defect_act').first()
        steps = {a.approver_id: a.step for a in doc.approvals}
        assert steps[admin_id] == 0     # согласующий первым
        assert steps[head_id] == 1      # утверждающий последним
        # запчасти опциональны — документ создан без позиций
        assert doc.items.count() == 0


def test_defect_without_route_falls_back(client, app):
    eq_id = _mk_eq(app)
    login(client, 'mech@test.kz', 'mechpass123')
    client.post('/documents/defect-act/submit', data={
        'equipment_id': str(eq_id), 'description': 'Стук', 'action': 'submit',
        'part_name[]': [''], 'part_spec[]': [''], 'part_qty[]': [''],
        'part_unit[]': [''], 'part_cost[]': [''],
    })
    with app.app_context():
        doc = Document.query.filter_by(doc_type='defect_act').first()
        assert doc.status == 'pending'
        assert DocumentApproval.query.filter_by(document_id=doc.id).count() == 1


def test_requisition_prefilled_from_defect_parts(client, app):
    eq_id = _mk_eq(app)
    login(client, 'mech@test.kz', 'mechpass123')
    client.post('/documents/defect-act/submit', data={
        'equipment_id': str(eq_id), 'description': 'Течь', 'action': 'draft',
        'part_name[]': ['Сальник', 'Клапан ИМЗ'], 'part_spec[]': ['P/N 123', ''],
        'part_qty[]': ['2', '6'], 'part_unit[]': ['шт', 'шт'],
        'part_cost[]': ['5000', ''],
    })
    with app.app_context():
        defect_id = Document.query.filter_by(doc_type='defect_act').first().id
    body = client.get(f'/documents/trebovanie-new/new?from_defect={defect_id}')\
                 .get_data(as_text=True)
    import json as _json
    assert 'PREFILL_ITEMS = [' in body
    assert _json.dumps('Сальник')[1:-1] in body      # json экранирует кириллицу
    assert _json.dumps('Клапан ИМЗ')[1:-1] in body


def test_index_plus_button_follows_type(client):
    login(client, 'admin@test.kz', 'adminpass123')
    body = client.get('/documents/?doc_type=po_services').get_data(as_text=True)
    assert 'po-services/new' in body
    body = client.get('/documents/?doc_type=defect_act').get_data(as_text=True)
    assert 'defect-act/new' in body
    body = client.get('/documents/').get_data(as_text=True)
    assert 'Новый документ' in body


def test_to_parts_add_and_stock_check(client, app, monkeypatch):
    eq_id = _mk_eq(app)
    login(client, 'mech@test.kz', 'mechpass123')
    client.post(f'/equipment/{eq_id}/to-parts/add',
                data={'name': 'LF17473', 'qty': '4', 'unit': 'шт'})
    client.post(f'/equipment/{eq_id}/to-parts/add',
                data={'name': 'Масло Shell 10W30', 'qty': '200', 'unit': 'л'})
    rows = [
        {'Материал': 'LF17473', 'База Атырау': '10', 'Поле': '2'},
        {'Материал': 'масло shell 10w30', 'База Атырау': '150', 'Поле': ''},
    ]
    monkeypatch.setattr('app.services.to_stock._stock_rows', lambda: rows)
    body = client.get(f'/equipment/{eq_id}').get_data(as_text=True)
    assert 'LF17473' in body
    assert 'есть' in body            # 12 >= 4
    assert 'не хватает' in body      # 150 < 200
    # удаление
    with app.app_context():
        part_id = ToPart.query.filter_by(name='LF17473').first().id
    client.post(f'/equipment/to-parts/{part_id}/delete')
    with app.app_context():
        assert ToPart.query.filter_by(name='LF17473').count() == 0


def test_to_parts_no_stock_configured(client, app, monkeypatch):
    eq_id = _mk_eq(app)
    login(client, 'mech@test.kz', 'mechpass123')
    client.post(f'/equipment/{eq_id}/to-parts/add', data={'name': 'FF105', 'qty': '1'})
    monkeypatch.setattr('app.services.to_stock._stock_rows', lambda: None)
    body = client.get(f'/equipment/{eq_id}').get_data(as_text=True)
    assert 'нет данных склада' in body


def test_demo_blocks_removed_from_forms(client, app):
    _mk_eq(app)
    login(client, 'mech@test.kz', 'mechpass123')
    body = client.get('/documents/defect-act/new').get_data(as_text=True)
    assert 'Начальник механического отдела' not in body   # статичный маршрут
    assert 'ИИ автоматически проверит' not in body
    assert 'Имеет ссылку с' not in body
    body = client.get('/documents/trebovanie-new/new').get_data(as_text=True)
    assert 'Удерживайте Ctrl' not in body                  # секция «Получатели»


def test_copy_table_button_on_document(client, app):
    login(client, 'mech@test.kz', 'mechpass123')
    client.post('/documents/trebovanie-new/submit', data={
        'summary': 'Копитест', 'action': 'draft',
        'item_name[]': ['Товар'], 'item_spec[]': [''], 'item_qty[]': ['1'],
        'item_unit[]': ['шт'], 'item_date[]': [''], 'item_note[]': [''],
        'item_cost[]': ['5'],
    })
    with app.app_context():
        doc_id = Document.query.filter_by(title='Копитест').first().id
    body = client.get(f'/documents/{doc_id}').get_data(as_text=True)
    assert 'copyItemsTable' in body and 'items-copy-table' in body
