from conftest import login
from app import db
from app.models import Document, User


def _submit_po_services(client, sig_id):
    return client.post('/documents/po-services/submit', data={
        'summary': 'Питание и проживание', 'action': 'submit',
        'signatory_id': str(sig_id),
        'counterparty': 'TOO Elsab', 'currency': 'KZT', 'vat_payer': 'Да',
        'payment_date': '2026-07-30', 'payment_terms': '100% оплата',
        'service_date': '2026-06-30', 'budget_line': 'Услуги проживания',
        'item_name[]': ['Услуги питания (обед)'], 'item_qty[]': ['29'],
        'item_unit[]': ['услуга'], 'item_cost[]': ['2625'], 'item_note[]': [''],
    }, content_type='multipart/form-data')


def test_po_services_print_layout(client, app):
    with app.app_context():
        sig_id = User.query.filter_by(email='head@test.kz').first().id
    login(client, 'mech@test.kz', 'mechpass123')
    _submit_po_services(client, sig_id)
    with app.app_context():
        doc = Document.query.filter_by(doc_type='po_services').first()
        doc_id = doc.id
    body = client.get(f'/documents/{doc_id}/print').get_data(as_text=True)
    assert 'ЗАЯВКА НА ПОКУПКУ' in body and 'CIS-PO-001' in body
    assert 'TOO Elsab' in body
    assert 'Услуги питания (обед)' in body
    assert '76 125.00' in body                      # 29 × 2625
    assert 'Итого: 76 125.00' in body
    assert 'НДС / VAT 16%: 10 500.00' in body       # 76125*16/116
    # согласований ещё нет — подписывающий в ожидании, это видно на распечатке
    assert 'Ожидает утверждения' in body


def test_po_services_print_shows_real_approvals(client, app):
    with app.app_context():
        sig_id = User.query.filter_by(email='head@test.kz').first().id
    login(client, 'mech@test.kz', 'mechpass123')
    _submit_po_services(client, sig_id)
    with app.app_context():
        doc_id = Document.query.filter_by(doc_type='po_services').first().id
    client.get('/auth/logout')
    login(client, 'head@test.kz', 'headpass123')
    client.post(f'/documents/{doc_id}/approve', data={'action': 'approve'})
    body = client.get(f'/documents/{doc_id}/print').get_data(as_text=True)
    assert 'Утверждено' in body and 'Ожидает утверждения' not in body


def test_po_goods_print_layout(client, app):
    with app.app_context():
        sig_id = User.query.filter_by(email='head@test.kz').first().id
    login(client, 'mech@test.kz', 'mechpass123')
    client.post('/documents/po-trebovanie/submit', data={
        'summary': 'Материалы для СКУ', 'action': 'submit',
        'signatory_id': str(sig_id),
        'counterparty': 'ТОО "УралМеталлинвест"', 'vat_payer': 'Да',
        'basis': 'Новый СКУ', 'payment_terms': '100% предоплата',
        'item_name[]': ['труба проф.40х40х3,0, L=6,0'], 'item_qty[]': ['180'],
        'item_unit[]': ['м'], 'item_cost[]': ['1394'], 'item_code[]': ['7306'],
    }, content_type='multipart/form-data')
    with app.app_context():
        doc_id = Document.query.filter_by(doc_type='po_trebovanie').first().id
    body = client.get(f'/documents/{doc_id}/print').get_data(as_text=True)
    assert 'Заявка на закупку товаров' in body and 'CIS-MR-001' in body
    assert 'труба проф.40х40х3,0' in body and '7306' in body
    assert 'Итого: 250 920.00' in body
    assert 'Ожидает подписи' in body


def test_other_doc_types_keep_generic_print(client, app):
    login(client, 'mech@test.kz', 'mechpass123')
    client.post('/documents/trebovanie-new/submit', data={
        'summary': 'Обычное требование', 'action': 'draft',
        'item_name[]': ['Товар'], 'item_spec[]': [''], 'item_qty[]': ['1'],
        'item_unit[]': ['шт'], 'item_date[]': [''], 'item_note[]': [''],
        'item_cost[]': ['1'],
    })
    with app.app_context():
        doc_id = Document.query.filter_by(doc_type='purchase_req').first().id
    body = client.get(f'/documents/{doc_id}/print').get_data(as_text=True)
    assert 'CASPIAN INTEGRATED SERVICES' in body   # старый бланк работает
