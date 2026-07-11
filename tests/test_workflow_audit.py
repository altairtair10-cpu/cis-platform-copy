"""Functional audit: routing order, stages, signature-last, all doc types."""
from conftest import login
from app import db
from app.models import Document, DocumentApproval, User, Notification


def _mk_user(app, email, role='dept_head'):
    with app.app_context():
        u = User(first_name=email.split('@')[0].title(), last_name='T',
                 email=email, role=role, is_active=True)
        u.set_password('password123')
        db.session.add(u); db.session.commit()
        return u.id


def _submit_staged_req(client, sig_id, stage1_ids, stage2_ids=None):
    """New form format: per-stage reviewers + signatory."""
    data = {
        'summary': 'Маршрутный тест', 'action': 'submit',
        'signatory_id': str(sig_id),
        'stage_no[]': ['1'] + (['2'] if stage2_ids else []),
        'stage_type[]': ['parallel'] + (['parallel'] if stage2_ids else []),
        'item_name[]': ['Товар'], 'item_spec[]': [''], 'item_qty[]': ['1'],
        'item_unit[]': ['шт'], 'item_date[]': [''], 'item_note[]': [''],
        'item_cost[]': ['100'],
    }
    for rid in stage1_ids:
        data.setdefault('stage_reviewer_1[]', []).append(str(rid))
    for rid in (stage2_ids or []):
        data.setdefault('stage_reviewer_2[]', []).append(str(rid))
    return client.post('/documents/trebovanie-new/submit', data=data,
                       follow_redirects=True)


def _approve(client, doc_id, action='approve', comment=''):
    return client.post(f'/documents/{doc_id}/approve',
                       data={'action': action, 'comment': comment},
                       follow_redirects=True)


def test_signature_comes_last(client, app):
    a_id = _mk_user(app, 'rev.a@test.kz')
    with app.app_context():
        sig_id = User.query.filter_by(email='head@test.kz').first().id
    login(client, 'mech@test.kz', 'mechpass123')
    _submit_staged_req(client, sig_id, [a_id])
    with app.app_context():
        doc = Document.query.filter_by(title='Маршрутный тест').first()
        steps = {(ap.approver_id): ap.step for ap in doc.approvals}
        assert steps[a_id] == 0          # согласующий первым
        assert steps[sig_id] == 1        # подписывающий последним
        assert doc.current_step == 0


def test_stage_order_enforced_and_chain_completes(client, app):
    a_id = _mk_user(app, 'rev.a2@test.kz')
    b_id = _mk_user(app, 'rev.b2@test.kz')
    with app.app_context():
        sig_id = User.query.filter_by(email='head@test.kz').first().id
    login(client, 'mech@test.kz', 'mechpass123')
    _submit_staged_req(client, sig_id, [a_id], [b_id])
    with app.app_context():
        doc_id = Document.query.filter_by(title='Маршрутный тест').first().id
    client.get('/auth/logout')

    # B (этап 2) не может согласовать раньше A (этап 1)
    login(client, 'rev.b2@test.kz', 'password123')
    _approve(client, doc_id)
    with app.app_context():
        doc = db.session.get(Document, doc_id)
        assert doc.status == 'pending' and doc.current_step == 0
    client.get('/auth/logout')

    # Подписывающий тоже не может подписать раньше согласующих
    login(client, 'head@test.kz', 'headpass123')
    _approve(client, doc_id)
    with app.app_context():
        assert db.session.get(Document, doc_id).current_step == 0
    client.get('/auth/logout')

    # A согласует -> этап 2, B получает уведомление
    login(client, 'rev.a2@test.kz', 'password123')
    _approve(client, doc_id)
    with app.app_context():
        assert db.session.get(Document, doc_id).current_step == 1
        assert Notification.query.filter_by(user_id=b_id).filter(
            Notification.title.like('%на согласование%')).count() >= 1
    client.get('/auth/logout')

    # B согласует -> подпись; подписывающий утверждает -> approved
    login(client, 'rev.b2@test.kz', 'password123')
    _approve(client, doc_id)
    client.get('/auth/logout')
    login(client, 'head@test.kz', 'headpass123')
    _approve(client, doc_id)
    with app.app_context():
        assert db.session.get(Document, doc_id).status == 'approved'


def test_parallel_stage_requires_everyone(client, app):
    a_id = _mk_user(app, 'rev.a3@test.kz')
    b_id = _mk_user(app, 'rev.b3@test.kz')
    with app.app_context():
        sig_id = User.query.filter_by(email='head@test.kz').first().id
    login(client, 'mech@test.kz', 'mechpass123')
    _submit_staged_req(client, sig_id, [a_id, b_id])
    with app.app_context():
        doc_id = Document.query.filter_by(title='Маршрутный тест').first().id
    client.get('/auth/logout')
    login(client, 'rev.a3@test.kz', 'password123')
    _approve(client, doc_id)
    with app.app_context():
        assert db.session.get(Document, doc_id).current_step == 0  # ждём B
    client.get('/auth/logout')
    login(client, 'rev.b3@test.kz', 'password123')
    _approve(client, doc_id)
    with app.app_context():
        assert db.session.get(Document, doc_id).current_step == 1  # подпись


def test_double_approve_is_noop(client, app):
    a_id = _mk_user(app, 'rev.a4@test.kz')
    with app.app_context():
        sig_id = User.query.filter_by(email='head@test.kz').first().id
    login(client, 'mech@test.kz', 'mechpass123')
    _submit_staged_req(client, sig_id, [a_id])
    with app.app_context():
        doc_id = Document.query.filter_by(title='Маршрутный тест').first().id
    client.get('/auth/logout')
    login(client, 'rev.a4@test.kz', 'password123')
    _approve(client, doc_id)
    _approve(client, doc_id)   # повторное — не должно ничего сломать
    with app.app_context():
        doc = db.session.get(Document, doc_id)
        assert doc.current_step == 1 and doc.status == 'pending'
        approved = DocumentApproval.query.filter_by(document_id=doc_id,
                                                    status='approved').count()
        assert approved == 1


def test_reject_at_signature_stage(client, app):
    a_id = _mk_user(app, 'rev.a5@test.kz')
    with app.app_context():
        sig_id = User.query.filter_by(email='head@test.kz').first().id
    login(client, 'mech@test.kz', 'mechpass123')
    _submit_staged_req(client, sig_id, [a_id])
    with app.app_context():
        doc_id = Document.query.filter_by(title='Маршрутный тест').first().id
    client.get('/auth/logout')
    login(client, 'rev.a5@test.kz', 'password123')
    _approve(client, doc_id)
    client.get('/auth/logout')
    login(client, 'head@test.kz', 'headpass123')
    _approve(client, doc_id, action='reject', comment='нет бюджета')
    with app.app_context():
        assert db.session.get(Document, doc_id).status == 'rejected'
    # согласовать отклонённый нельзя
    _approve(client, doc_id)
    with app.app_context():
        assert db.session.get(Document, doc_id).status == 'rejected'


def test_return_and_resubmit_loop(client, app):
    a_id = _mk_user(app, 'rev.a6@test.kz')
    with app.app_context():
        sig_id = User.query.filter_by(email='head@test.kz').first().id
    login(client, 'mech@test.kz', 'mechpass123')
    _submit_staged_req(client, sig_id, [a_id])
    with app.app_context():
        doc_id = Document.query.filter_by(title='Маршрутный тест').first().id
    client.get('/auth/logout')
    login(client, 'rev.a6@test.kz', 'password123')
    _approve(client, doc_id, action='return', comment='уточните количество')
    with app.app_context():
        assert db.session.get(Document, doc_id).status == 'returned'
    client.get('/auth/logout')
    login(client, 'mech@test.kz', 'mechpass123')
    client.post(f'/documents/{doc_id}/resubmit', follow_redirects=True)
    with app.app_context():
        assert db.session.get(Document, doc_id).status == 'pending'


def test_draft_cannot_be_approved(client, app):
    login(client, 'mech@test.kz', 'mechpass123')
    client.post('/documents/trebovanie-new/submit', data={
        'summary': 'Черновик', 'action': 'draft',
        'item_name[]': ['Товар'], 'item_spec[]': [''], 'item_qty[]': ['1'],
        'item_unit[]': ['шт'], 'item_date[]': [''], 'item_note[]': [''],
        'item_cost[]': ['1'],
    })
    with app.app_context():
        doc_id = Document.query.filter_by(title='Черновик').first().id
    client.get('/auth/logout')
    login(client, 'admin@test.kz', 'adminpass123')
    _approve(client, doc_id)
    with app.app_context():
        assert db.session.get(Document, doc_id).status == 'draft'


def test_po_services_and_po_trebovanie_chains(client, app):
    with app.app_context():
        sig_id = User.query.filter_by(email='head@test.kz').first().id
    login(client, 'mech@test.kz', 'mechpass123')
    client.post('/documents/po-services/submit', data={
        'summary': 'Услуги крана', 'action': 'submit', 'signatory_id': str(sig_id),
        'item_name[]': ['Кран'], 'item_qty[]': ['1'], 'item_unit[]': ['усл'],
        'item_cost[]': ['5000'], 'item_note[]': [''],
    }, content_type='multipart/form-data')
    client.post('/documents/po-trebovanie/submit', data={
        'summary': 'Товары со склада', 'action': 'submit', 'signatory_id': str(sig_id),
        'item_name[]': ['Фильтр'], 'item_qty[]': ['4'], 'item_unit[]': ['шт'],
        'item_cost[]': ['200'], 'item_code[]': ['FF105'],
    }, content_type='multipart/form-data')
    client.get('/auth/logout')
    login(client, 'head@test.kz', 'headpass123')
    with app.app_context():
        po_s = Document.query.filter_by(doc_type='po_services').first()
        po_t = Document.query.filter_by(doc_type='po_trebovanie').first()
        assert po_s.status == 'pending' and po_t.status == 'pending'
        ids = (po_s.id, po_t.id)
    for did in ids:
        _approve(client, did)
    with app.app_context():
        # оба вида ПО после подписи уходят на оплату
        assert db.session.get(Document, ids[0]).status == 'awaiting_payment'
        assert db.session.get(Document, ids[1]).status == 'awaiting_payment'
