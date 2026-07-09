from decimal import Decimal
from conftest import login
from app import db
from app.models import Document, DocumentItem, DocumentSequence


def _create_doc(client, purpose='Test purchase'):
    return client.post('/documents/new/purchase-requisition', data={
        'purpose': purpose,
        'department': 'it',
        'urgency': 'standard',
        'justification': 'testing',
        'item_name[]': ['Cable'],
        'item_unit[]': ['m'],
        'item_qty[]': ['10'],
        'item_note[]': [''],
        'item_cost[]': ['125.50'],
        'action': 'draft',
    }, follow_redirects=True)


def test_document_number_generated(client, app):
    login(client, 'admin@test.kz', 'adminpass123')
    _create_doc(client)
    with app.app_context():
        doc = Document.query.first()
        assert doc.doc_number and doc.doc_number.startswith('ТМЦ-')


def test_document_numbers_unique_and_sequential(client, app):
    login(client, 'admin@test.kz', 'adminpass123')
    _create_doc(client, 'First')
    _create_doc(client, 'Second')
    with app.app_context():
        nums = [d.doc_number for d in Document.query.all()]
        assert len(nums) == len(set(nums)) == 2
        seq = DocumentSequence.query.filter_by(doc_type='purchase_req').first()
        assert seq.counter == 2


def test_price_stored_as_decimal(client, app):
    login(client, 'admin@test.kz', 'adminpass123')
    _create_doc(client)
    with app.app_context():
        item = DocumentItem.query.first()
        assert item.price == Decimal('125.50')
        assert item.line_total == 1255.0


def test_unassigned_user_cannot_approve(client, app):
    login(client, 'admin@test.kz', 'adminpass123')
    _create_doc(client)
    with app.app_context():
        doc_id = Document.query.first().id
    # dept_head has 'documents' permission but no pending approval assigned
    client.get('/auth/logout')
    login(client, 'head@test.kz', 'headpass123')
    client.post(f'/documents/{doc_id}/approve',
                data={'action': 'approve'}, follow_redirects=True)
    with app.app_context():
        assert Document.query.get(doc_id).status == 'draft'  # unchanged
