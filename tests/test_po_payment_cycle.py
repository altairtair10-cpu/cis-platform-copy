from conftest import login
from app import db
from app.models import Document, User, Notification


def _fin(app):
    with app.app_context():
        u = User(first_name='Fin', last_name='Treasurer', email='fin@test.kz',
                 role='accountant', is_active=True)
        u.set_password('finpass12345')
        db.session.add(u); db.session.commit()
        return u.id


def _signed_po(client, app):
    with app.app_context():
        sig_id = User.query.filter_by(email='head@test.kz').first().id
    login(client, 'mech@test.kz', 'mechpass123')
    client.post('/documents/po-services/submit', data={
        'summary': 'Услуги крана', 'action': 'submit', 'signatory_id': str(sig_id),
        'vat_payer': 'yes',
        'item_name[]': ['Кран'], 'item_qty[]': ['1'], 'item_unit[]': ['усл'],
        'item_cost[]': ['100000'], 'item_note[]': [''],
    }, content_type='multipart/form-data')
    client.get('/auth/logout')
    login(client, 'head@test.kz', 'headpass123')
    with app.app_context():
        doc_id = Document.query.filter_by(doc_type='po_services').first().id
    client.post(f'/documents/{doc_id}/approve', data={'action': 'approve'})
    client.get('/auth/logout')
    return doc_id


def test_signed_po_goes_to_payment_and_notifies_finance(client, app):
    fin_id = _fin(app)
    doc_id = _signed_po(client, app)
    with app.app_context():
        doc = db.session.get(Document, doc_id)
        assert doc.status == 'awaiting_payment'
        assert Notification.query.filter_by(user_id=fin_id).count() == 1


def test_payments_sheet_marks_paid(client, app):
    _fin(app)
    doc_id = _signed_po(client, app)
    from app.services.payments_sync import sync_payments
    with app.app_context():
        num = db.session.get(Document, doc_id).doc_number
        rows = [['Дата', 'Номер ПО', 'Сумма'],
                ['11.07.2026', num, '100 000'],
                ['11.07.2026', 'РОУ-2020-999', '5']]
        paid = sync_payments(rows=rows)
        assert paid == [num]
        doc = db.session.get(Document, doc_id)
        assert doc.status == 'closing_docs' and doc.paid_at is not None
        # автору пришло уведомление про закрывающие
        author = User.query.filter_by(email='mech@test.kz').first()
        assert Notification.query.filter_by(user_id=author.id)\
            .filter(Notification.title.like('%оплачен%')).count() == 1


def test_payments_sheet_no_match_no_change(client, app):
    doc_id = _signed_po(client, app)
    from app.services.payments_sync import sync_payments
    with app.app_context():
        paid = sync_payments(rows=[['ничего похожего']])
        assert paid == []
        assert db.session.get(Document, doc_id).status == 'awaiting_payment'


def test_manual_paid_and_closing_flow(client, app):
    _fin(app)
    doc_id = _signed_po(client, app)
    login(client, 'fin@test.kz', 'finpass12345')
    client.post(f'/documents/{doc_id}/mark-paid')
    with app.app_context():
        assert db.session.get(Document, doc_id).status == 'closing_docs'
    client.post(f'/documents/{doc_id}/closing-docs-received')
    with app.app_context():
        assert db.session.get(Document, doc_id).status == 'closed'


def test_non_finance_cannot_mark_paid(client, app):
    doc_id = _signed_po(client, app)
    login(client, 'mech@test.kz', 'mechpass123')
    assert client.post(f'/documents/{doc_id}/mark-paid').status_code == 403


def test_dashboards_show_blocks(client, app):
    _fin(app)
    doc_id = _signed_po(client, app)
    login(client, 'fin@test.kz', 'finpass12345')
    body = client.get('/dashboard').get_data(as_text=True)
    assert 'ПО на оплате' in body
    client.get('/auth/logout')
    # после оплаты — блок у автора
    from app.services.payments_sync import sync_payments
    with app.app_context():
        num = db.session.get(Document, doc_id).doc_number
        sync_payments(rows=[[num]])
    login(client, 'mech@test.kz', 'mechpass123')
    body = client.get('/dashboard').get_data(as_text=True)
    assert 'закрывающих документов' in body


def test_print_vat_of_total_and_da(client, app):
    doc_id = _signed_po(client, app)
    login(client, 'mech@test.kz', 'mechpass123')
    body = client.get(f'/documents/{doc_id}/print').get_data(as_text=True)
    assert 'Плательщик НДС:</b> Да' in body
    assert 'В том числе НДС 16%: 16 000.00' in body   # 100000 * 0.16


def test_type_selector_present_on_view_page(client, app):
    doc_id = _signed_po(client, app)
    login(client, 'mech@test.kz', 'mechpass123')
    body = client.get(f'/documents/{doc_id}').get_data(as_text=True)
    assert 'Все виды документов' in body


def test_po_goods_full_payment_cycle(client, app):
    fin_id = _fin(app)
    with app.app_context():
        sig_id = User.query.filter_by(email='head@test.kz').first().id
    login(client, 'mech@test.kz', 'mechpass123')
    client.post('/documents/po-trebovanie/submit', data={
        'summary': 'Трубы', 'action': 'submit', 'signatory_id': str(sig_id),
        'item_name[]': ['труба'], 'item_qty[]': ['10'], 'item_unit[]': ['м'],
        'item_cost[]': ['1000'], 'item_code[]': [''],
    }, content_type='multipart/form-data')
    client.get('/auth/logout')
    login(client, 'head@test.kz', 'headpass123')
    with app.app_context():
        doc_id = Document.query.filter_by(doc_type='po_trebovanie').first().id
    client.post(f'/documents/{doc_id}/approve', data={'action': 'approve'})
    with app.app_context():
        assert db.session.get(Document, doc_id).status == 'awaiting_payment'
    from app.services.payments_sync import sync_payments
    with app.app_context():
        num = db.session.get(Document, doc_id).doc_number
        assert sync_payments(rows=[[num]]) == [num]
        assert db.session.get(Document, doc_id).status == 'closing_docs'
    client.get('/auth/logout')
    login(client, 'fin@test.kz', 'finpass12345')
    client.post(f'/documents/{doc_id}/closing-docs-received')
    with app.app_context():
        assert db.session.get(Document, doc_id).status == 'closed'
