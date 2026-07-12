from conftest import login
from app import db
from app.models import Document, SavedView, User


def _submit(client, sig_id, summary='Входящий тест'):
    return client.post('/documents/trebovanie-new/submit', data={
        'summary': summary, 'action': 'submit', 'signatory_id': str(sig_id),
        'item_name[]': ['x'], 'item_spec[]': [''], 'item_qty[]': ['1'],
        'item_unit[]': ['шт'], 'item_date[]': [''], 'item_note[]': [''],
        'item_cost[]': ['1'],
    })


def test_inbox_shows_docs_awaiting_me(client, app):
    with app.app_context():
        head_id = User.query.filter_by(email='head@test.kz').first().id
    login(client, 'mech@test.kz', 'mechpass123')
    _submit(client, head_id)
    client.get('/auth/logout')
    # у подписывающего документ во «входящих»
    login(client, 'head@test.kz', 'headpass123')
    body = client.get('/documents/?mine=inbox').get_data(as_text=True)
    assert body.count('data-doc-row') == 1
    # после решения — уходит из входящих, появляется в «решённых»
    with app.app_context():
        doc_id = Document.query.first().id
    client.post(f'/documents/{doc_id}/approve', data={'action': 'approve'})
    body = client.get('/documents/?mine=inbox').get_data(as_text=True)
    assert body.count('data-doc-row') == 0
    body = client.get('/documents/?mine=decided').get_data(as_text=True)
    assert body.count('data-doc-row') == 1


def test_created_by_me_filter(client, app):
    with app.app_context():
        head_id = User.query.filter_by(email='head@test.kz').first().id
    login(client, 'mech@test.kz', 'mechpass123')
    _submit(client, head_id, 'Моё требование')
    body = client.get('/documents/?mine=created').get_data(as_text=True)
    assert body.count('data-doc-row') == 1 and 'Моё требование' in body
    client.get('/auth/logout')
    login(client, 'head@test.kz', 'headpass123')
    body = client.get('/documents/?mine=created').get_data(as_text=True)
    assert body.count('data-doc-row') == 0


def test_inbox_counter_in_panel(client, app):
    with app.app_context():
        head_id = User.query.filter_by(email='head@test.kz').first().id
    login(client, 'mech@test.kz', 'mechpass123')
    _submit(client, head_id)
    client.get('/auth/logout')
    login(client, 'head@test.kz', 'headpass123')
    body = client.get('/documents/').get_data(as_text=True)
    assert 'Ждут моего решения' in body


def test_saved_view_lifecycle(client, app):
    login(client, 'mech@test.kz', 'mechpass123')
    client.post('/documents/views/save',
                data={'name': 'Мои ПО', 'params': 'doc_type=po_services&mine=created'})
    body = client.get('/documents/').get_data(as_text=True)
    assert 'Мои ПО' in body and 'doc_type=po_services' in body
    with app.app_context():
        view = SavedView.query.filter_by(name='Мои ПО').first()
        assert view is not None
        vid, owner_id = view.id, view.user_id
    # чужой не может удалить
    client.get('/auth/logout')
    login(client, 'head@test.kz', 'headpass123')
    assert client.post(f'/documents/views/{vid}/delete').status_code == 403
    body = client.get('/documents/').get_data(as_text=True)
    assert 'doc_type=po_services&mine=created' not in body   # и не видит чужой вид
    # владелец удаляет
    client.get('/auth/logout')
    login(client, 'mech@test.kz', 'mechpass123')
    client.post(f'/documents/views/{vid}/delete')
    with app.app_context():
        assert db.session.get(SavedView, vid) is None


def test_sidebar_has_my_documents_tab(client):
    login(client, 'mech@test.kz', 'mechpass123')
    body = client.get('/dashboard').get_data(as_text=True)
    assert 'mine=inbox' in body and 'Мои документы' in body
