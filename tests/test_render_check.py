"""Render check for the Documentolog-style document form refresh."""
import io
from tests.conftest import login


def test_dlog_forms_render_and_flow(client):
    login(client, 'admin@test.kz', 'adminpass123')

    # Old entry point now funnels into the unified form
    r = client.get('/documents/trebovanie/new', follow_redirects=True)
    assert r.status_code == 200
    html = r.data.decode()
    assert 'signatory_id' in html
    assert 'Согласующие' in html
    assert 'attachments' in html

    r = client.get('/documents/po-services/new')
    assert r.status_code == 200
    html = r.data.decode()
    assert 'Маршрут документа' in html
    assert 'Прочие условия' in html
    assert 'Вложения' in html

    # Submit a trebovanie with route + attachment; check the view page
    r = client.post('/documents/trebovanie-new/submit', data={
        'action': 'submit',
        'summary': 'Труба проф. 40х40х3,0',
        'urgency': 'standard',
        'department': 'mechanic',
        'needed_by': '2026-08-01',
        'signatory_id': '2',
        'stage_type[]': ['parallel'],
        'stage_reviewer[]': ['1', '2'],
        'item_name[]': ['Труба проф.40х40х3,0 L=12,0'],
        'item_spec[]': [''],
        'item_qty[]': ['122'],
        'item_unit[]': ['кг'],
        'item_cost[]': ['50184'],
        'attachments': (io.BytesIO(b'%PDF-1.4 test'), 'schet.pdf'),
    }, content_type='multipart/form-data', follow_redirects=True)
    assert r.status_code == 200
    html = r.data.decode()
    assert 'Результаты согласования' in html
    assert 'Подписывающий:' in html
    assert 'schet.pdf' in html

    # Submit a PO for services too
    r = client.post('/documents/po-services/submit', data={
        'action': 'submit',
        'summary': 'Услуги доставки',
        'basis': 'Проект Хим Скид (ГРП)',
        'counterparty': 'ТОО "УралМеталлинвест"',
        'ordered_by': 'Жулмаганбетов Н.Б.',
        'department': 'mechanic',
        'currency': 'KZT',
        'payment_date': '2026-08-01',
        'payment_terms': '100% предоплата',
        'service_terms': 'База Атырау',
        'service_date': '2026-08-15',
        'budget_line': 'ОРЕХ-12',
        'signatory_id': '2',
        'item_name[]': ['Доставка'],
        'item_unit[]': ['услуга'],
        'item_qty[]': ['1'],
        'item_cost[]': ['5000'],
    }, content_type='multipart/form-data', follow_redirects=True)
    assert r.status_code == 200
    assert 'Результаты согласования' in r.data.decode()
