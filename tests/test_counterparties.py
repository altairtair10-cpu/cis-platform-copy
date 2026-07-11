from conftest import login
from app import db
from app.models import Counterparty, Document, User


def test_add_and_list_counterparty(client, app):
    login(client, 'mech@test.kz', 'mechpass123')
    r = client.post('/documents/counterparties/add', json={
        'name': 'ТОО SafetyLine', 'bin': '123456789012', 'phone': '77015237105',
        'contact_person': 'Сергей Жуков', 'materials': 'СИЗ', 'currency': 'KZT',
    })
    assert r.status_code == 200 and r.get_json()['ok']
    rows = client.get('/documents/counterparties.json').get_json()
    assert any(c['name'] == 'ТОО SafetyLine' for c in rows)
    # дубль по имени не создаётся
    r2 = client.post('/documents/counterparties/add', json={'name': 'ТОО SafetyLine'})
    assert r2.get_json().get('existed')
    with app.app_context():
        assert Counterparty.query.count() == 1


def test_empty_name_rejected(client):
    login(client, 'mech@test.kz', 'mechpass123')
    assert client.post('/documents/counterparties/add', json={'name': ''}).status_code == 400


def test_po_goods_links_counterparty_and_requisition(client, app):
    with app.app_context():
        cp = Counterparty(name='ТОО УралМеталлинвест')
        db.session.add(cp)
        db.session.commit()
        cp_id = cp.id
        sig_id = User.query.filter_by(email='head@test.kz').first().id
    login(client, 'mech@test.kz', 'mechpass123')
    # создаём требование, чтобы было что выбрать
    client.post('/documents/trebovanie-new/submit', data={
        'summary': 'Заявка на трубы', 'action': 'submit', 'signatory_id': str(sig_id),
        'item_name[]': ['труба'], 'item_spec[]': [''], 'item_qty[]': ['1'],
        'item_unit[]': ['м'], 'item_date[]': [''], 'item_note[]': [''],
        'item_cost[]': ['100'],
    })
    with app.app_context():
        req = Document.query.filter_by(doc_type='purchase_req').first()
        req_id, req_num = req.id, req.doc_number
    # форма показывает требование в выпадашке
    body = client.get('/documents/po-trebovanie/new').get_data(as_text=True)
    assert req_num in body
    assert 'cpOpen()' in body           # пикер контрагента
    assert body.count('Прочие условия') == 1   # дубль убран
    assert 'Группа материалов' in body
    # сабмит с контрагентом из справочника и связанным требованием
    client.post('/documents/po-trebovanie/submit', data={
        'summary': 'Закуп труб', 'action': 'draft',
        'counterparty_id': str(cp_id), 'related_req_id': str(req_id),
        'item_name[]': ['труба'], 'item_qty[]': ['10'], 'item_unit[]': ['м'],
        'item_cost[]': ['1000'], 'item_code[]': [''],
    }, content_type='multipart/form-data')
    with app.app_context():
        po = Document.query.filter_by(doc_type='po_trebovanie').first()
        assert po.counterparty_id == cp_id
        assert po.related_req_id == req_id
        assert 'Контрагент: ТОО УралМеталлинвест' in po.justification
        assert req_num in po.justification


def test_po_services_counterparty_from_directory(client, app):
    with app.app_context():
        cp = Counterparty(name='TOO Elsab')
        db.session.add(cp); db.session.commit()
        cp_id = cp.id
    login(client, 'mech@test.kz', 'mechpass123')
    client.post('/documents/po-services/submit', data={
        'summary': 'Питание', 'action': 'draft', 'counterparty_id': str(cp_id),
        'item_name[]': ['обед'], 'item_qty[]': ['1'], 'item_unit[]': ['усл'],
        'item_cost[]': ['2625'], 'item_note[]': [''],
    }, content_type='multipart/form-data')
    with app.app_context():
        po = Document.query.filter_by(doc_type='po_services').first()
        assert po.counterparty_id == cp_id
        assert 'Контрагент: TOO Elsab' in po.justification


def test_ordered_by_dropdown_rendered(client):
    login(client, 'mech@test.kz', 'mechpass123')
    body = client.get('/documents/po-services/new').get_data(as_text=True)
    assert 'Выбрать сотрудника' in body
