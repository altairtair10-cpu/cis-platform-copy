"""Внутренние документы (Documentolog-style): форма, полный жизненный цикл
Создание → Согласование → Подпись → Регистрация → На исполнении → Исполнен,
получатели, санитайзер текста, видимость."""
from tests.conftest import login
from app import db
from app.models import Document, DocumentRecipient, Notification, User


def _submit_memo(client, recipient_ids=('3',), signatory='2', action='submit',
                 body='<p>Прошу Вас рассмотреть.</p>', extra=None):
    data = {
        'action': action,
        'doc_type': 'memo',
        'summary': 'О закупке канцтоваров',
        'case_index': '03-05',
        'doc_language': 'ru',
        'needed_by': '2026-08-01',
        'body_html': body,
        'signatory_id': signatory,
        'stage_reviewer[]': ['1'],
        'recipient_ids[]': list(recipient_ids),
    }
    if extra:
        data.update(extra)
    return client.post('/documents/internal/submit', data=data,
                       content_type='multipart/form-data',
                       follow_redirects=True)


def test_internal_form_renders(client):
    login(client, 'admin@test.kz', 'adminpass123')
    r = client.get('/documents/internal/new?doc_type=memo')
    assert r.status_code == 200
    html = r.data.decode()
    assert 'ПРОЕКТ ВНУТРЕННЕГО ДОКУМЕНТА' in html
    assert 'Получатели' in html
    assert 'Подписывающий' in html
    assert 'Индекс дела' in html
    assert 'Текст документа' in html
    assert 'Регистрация' in html          # чеврон этапа
    assert 'Констатирующая часть' in html  # шаблон текста как в Documentolog


def test_memo_number_prefix_and_creation(client, app):
    login(client, 'admin@test.kz', 'adminpass123')
    r = _submit_memo(client)
    assert r.status_code == 200
    with app.app_context():
        doc = Document.query.filter_by(doc_type='memo').first()
        assert doc is not None
        assert doc.doc_number.startswith('СЗ-')
        assert doc.status == 'pending'
        assert doc.case_index == '03-05'
        assert doc.doc_language == 'ru'
        assert doc.recipients.count() == 1
        # маршрут: этап согласующих + подписывающий последним
        steps = sorted(a.step for a in doc.approvals.all())
        assert steps == [0, 1]


def test_full_lifecycle_to_executed(client, app):
    # автор: admin; согласующий: admin (step 0); подписывающий: head (step 1);
    # получатель: mech (id 3)
    login(client, 'admin@test.kz', 'adminpass123')
    _submit_memo(client)
    with app.app_context():
        doc_id = Document.query.filter_by(doc_type='memo').first().id

    # шаг 1: согласующий (admin) согласует
    client.post(f'/documents/{doc_id}/approve',
                data={'action': 'approve'}, follow_redirects=True)
    with app.app_context():
        doc = db.session.get(Document, doc_id)
        assert doc.status == 'pending'
        assert doc.current_step == 1

    # шаг 2: подписывающий (head) подписывает → регистрация + на исполнении
    client.get('/auth/logout')
    login(client, 'head@test.kz', 'headpass123')
    client.post(f'/documents/{doc_id}/approve',
                data={'action': 'approve'}, follow_redirects=True)
    with app.app_context():
        doc = db.session.get(Document, doc_id)
        assert doc.status == 'in_execution'
        assert doc.registered_at is not None
        # получатель уведомлён
        mech = User.query.filter_by(email='mech@test.kz').first()
        n = Notification.query.filter_by(user_id=mech.id).filter(
            Notification.title.contains('на исполнение')).first()
        assert n is not None

    # шаг 3: получатель (mech) видит документ и отмечает исполнение
    client.get('/auth/logout')
    login(client, 'mech@test.kz', 'mechpass123')
    r = client.get(f'/documents/{doc_id}')
    assert r.status_code == 200
    r = client.post(f'/documents/{doc_id}/recipient-done',
                    data={'note': 'Закуплено'}, follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        doc = db.session.get(Document, doc_id)
        assert doc.status == 'executed'
        rec = DocumentRecipient.query.filter_by(document_id=doc_id).first()
        assert rec.status == 'done'
        assert rec.note == 'Закуплено'


def test_submit_without_recipients_saves_draft(client, app):
    login(client, 'admin@test.kz', 'adminpass123')
    _submit_memo(client, recipient_ids=())
    with app.app_context():
        doc = Document.query.filter_by(doc_type='memo').first()
        assert doc.status == 'draft'


def test_submit_without_signatory_saves_draft(client, app):
    login(client, 'admin@test.kz', 'adminpass123')
    _submit_memo(client, signatory='')
    with app.app_context():
        doc = Document.query.filter_by(doc_type='memo').first()
        assert doc.status == 'draft'


def test_body_html_sanitized(client, app):
    login(client, 'admin@test.kz', 'adminpass123')
    _submit_memo(client, body='<p onclick="hack()">Текст</p>'
                              '<script>alert(1)</script><b>жирный</b>')
    with app.app_context():
        doc = Document.query.filter_by(doc_type='memo').first()
        assert '<script' not in doc.body_html
        assert 'onclick' not in doc.body_html
        assert 'alert(1)' not in doc.body_html
        assert '<b>жирный</b>' in doc.body_html
        assert 'Текст' in doc.body_html


def test_non_recipient_cannot_mark_done(client, app):
    login(client, 'admin@test.kz', 'adminpass123')
    _submit_memo(client)
    with app.app_context():
        doc_id = Document.query.filter_by(doc_type='memo').first().id
    # согласование + подпись
    client.post(f'/documents/{doc_id}/approve', data={'action': 'approve'},
                follow_redirects=True)
    client.get('/auth/logout')
    login(client, 'head@test.kz', 'headpass123')
    client.post(f'/documents/{doc_id}/approve', data={'action': 'approve'},
                follow_redirects=True)
    # head — не получатель: отметить исполнение не может
    client.post(f'/documents/{doc_id}/recipient-done', data={},
                follow_redirects=True)
    with app.app_context():
        doc = db.session.get(Document, doc_id)
        assert doc.status == 'in_execution'
        rec = DocumentRecipient.query.filter_by(document_id=doc_id).first()
        assert rec.status == 'pending'


def test_draft_edit_and_submit_builds_route(client, app):
    login(client, 'admin@test.kz', 'adminpass123')
    _submit_memo(client, signatory='', action='submit')  # станет черновиком
    with app.app_context():
        doc = Document.query.filter_by(doc_type='memo').first()
        doc_id = doc.id
        assert doc.status == 'draft'
        assert doc.approvals.count() == 0

    r = client.get(f'/documents/internal/{doc_id}/edit')
    assert r.status_code == 200

    r = client.post(f'/documents/internal/{doc_id}/update', data={
        'action': 'submit',
        'doc_type': 'memo',
        'summary': 'О закупке канцтоваров (ред.)',
        'doc_language': 'ru',
        'body_html': '<p>Обновлено</p>',
        'signatory_id': '2',
        'stage_reviewer[]': ['1'],
        'recipient_ids[]': ['3'],
    }, content_type='multipart/form-data', follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        doc = db.session.get(Document, doc_id)
        assert doc.status == 'pending'
        assert doc.approvals.count() == 2
        assert doc.purpose == 'О закупке канцтоваров (ред.)'
