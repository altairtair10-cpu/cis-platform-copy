"""Статьи бюджета: справочник, привязка к РО, предупреждение о лимите."""
from app import db
from app.models import BudgetLine, Document, User
from tests.conftest import login


def _add_line(app, name, limit=None):
    with app.app_context():
        bl = BudgetLine(name=name, yearly_limit=limit, is_active=True)
        db.session.add(bl)
        db.session.commit()
        return bl.id


def _submit_po(client, app, budget_line, cost='100000'):
    with app.app_context():
        sig_id = User.query.filter_by(email='head@test.kz').first().id
    return client.post('/documents/po-services/submit', data={
        'summary': 'Услуги крана', 'action': 'submit', 'signatory_id': str(sig_id),
        'vat_payer': 'yes', 'budget_line': budget_line,
        'item_name[]': ['Кран'], 'item_qty[]': ['1'], 'item_unit[]': ['усл'],
        'item_cost[]': [cost], 'item_note[]': [''],
    }, content_type='multipart/form-data', follow_redirects=True)


def test_admin_adds_budget_line_and_sets_limit(client, app):
    login(client, 'admin@test.kz', 'adminpass123')
    client.post('/admin/reference-data/budget-lines/add',
                data={'name': 'Запчасти спецтехники'})
    with app.app_context():
        bl = BudgetLine.query.filter_by(name='Запчасти спецтехники').first()
        assert bl is not None
        bl_id = bl.id
    client.post(f'/admin/reference-data/budget-lines/{bl_id}/limit',
                data={'yearly_limit': '1 500 000,50'})
    with app.app_context():
        bl = db.session.get(BudgetLine, bl_id)
        assert float(bl.yearly_limit) == 1500000.50


def test_budget_limit_rejects_garbage(client, app):
    bl_id = _add_line(app, 'ГСМ')
    login(client, 'admin@test.kz', 'adminpass123')
    client.post(f'/admin/reference-data/budget-lines/{bl_id}/limit',
                data={'yearly_limit': 'abc'})
    with app.app_context():
        assert db.session.get(BudgetLine, bl_id).yearly_limit is None


def test_po_links_to_budget_line_by_name(client, app):
    bl_id = _add_line(app, 'Услуги подрядчиков', limit=None)
    login(client, 'mech@test.kz', 'mechpass123')
    _submit_po(client, app, 'Услуги подрядчиков')
    with app.app_context():
        doc = Document.query.filter_by(doc_type='po_services').first()
        assert doc.budget_line_id == bl_id


def test_po_free_text_budget_line_keeps_working(client, app):
    login(client, 'mech@test.kz', 'mechpass123')
    _submit_po(client, app, 'Прочее (не из справочника)')
    with app.app_context():
        doc = Document.query.filter_by(doc_type='po_services').first()
        assert doc is not None
        assert doc.budget_line_id is None
        assert 'Прочее (не из справочника)' in (doc.justification or '')


def test_warning_when_yearly_limit_exceeded(client, app):
    _add_line(app, 'Ремонт базы', limit=150000)
    login(client, 'mech@test.kz', 'mechpass123')
    # первый РО — 100 000, в пределах лимита
    resp = _submit_po(client, app, 'Ремонт базы', cost='100000')
    assert 'превышен годовой лимит' not in resp.get_data(as_text=True)
    # второй РО — ещё 100 000, суммарно 200 000 > 150 000
    resp = _submit_po(client, app, 'Ремонт базы', cost='100000')
    assert 'превышен годовой лимит' in resp.get_data(as_text=True)


def test_no_warning_without_limit(client, app):
    _add_line(app, 'Канцелярия', limit=None)
    login(client, 'mech@test.kz', 'mechpass123')
    resp = _submit_po(client, app, 'Канцелярия', cost='99999999')
    assert 'превышен годовой лимит' not in resp.get_data(as_text=True)


def test_drafts_do_not_count_against_budget(client, app):
    _add_line(app, 'Спецодежда', limit=150000)
    login(client, 'mech@test.kz', 'mechpass123')
    with app.app_context():
        sig_id = User.query.filter_by(email='head@test.kz').first().id
    # черновик на 100 000 — не должен учитываться в потраченном
    client.post('/documents/po-services/submit', data={
        'summary': 'Черновик', 'action': 'draft', 'signatory_id': str(sig_id),
        'vat_payer': 'yes', 'budget_line': 'Спецодежда',
        'item_name[]': ['Куртки'], 'item_qty[]': ['1'], 'item_unit[]': ['шт'],
        'item_cost[]': ['100000'], 'item_note[]': [''],
    }, content_type='multipart/form-data')
    resp = _submit_po(client, app, 'Спецодежда', cost='100000')
    assert 'превышен годовой лимит' not in resp.get_data(as_text=True)


def test_over_limit_banner_shown_on_document_page(client, app):
    _add_line(app, 'Аренда техники', limit=150000)
    login(client, 'mech@test.kz', 'mechpass123')
    _submit_po(client, app, 'Аренда техники', cost='200000')
    with app.app_context():
        doc_id = Document.query.filter_by(doc_type='po_services').first().id
    resp = client.get(f'/documents/{doc_id}')
    html = resp.get_data(as_text=True)
    assert 'Превышен годовой лимит' in html
    assert 'Аренда техники' in html


def test_no_banner_within_limit(client, app):
    _add_line(app, 'Связь', limit=500000)
    login(client, 'mech@test.kz', 'mechpass123')
    _submit_po(client, app, 'Связь', cost='100000')
    with app.app_context():
        doc_id = Document.query.filter_by(doc_type='po_services').first().id
    resp = client.get(f'/documents/{doc_id}')
    assert 'Превышен годовой лимит' not in resp.get_data(as_text=True)


def test_approver_sees_over_limit_banner(client, app):
    _add_line(app, 'Инструмент', limit=50000)
    login(client, 'mech@test.kz', 'mechpass123')
    _submit_po(client, app, 'Инструмент', cost='90000')
    with app.app_context():
        doc_id = Document.query.filter_by(doc_type='po_services').first().id
    client.get('/auth/logout')
    login(client, 'head@test.kz', 'headpass123')
    resp = client.get(f'/documents/{doc_id}')
    assert 'Превышен годовой лимит' in resp.get_data(as_text=True)
