from conftest import login
from app import db
from app.models import Location, AppSetting, DocNumberSetting, Document, AuditLog


def test_admin_hub_requires_it_admin(client):
    login(client, 'mech@test.kz', 'mechpass123')
    assert client.get('/admin/').status_code == 403


def test_admin_hub_opens_for_admin(client):
    login(client, 'admin@test.kz', 'adminpass123')
    assert client.get('/admin/').status_code == 200


def test_add_and_rename_location(client, app):
    login(client, 'admin@test.kz', 'adminpass123')
    client.post('/admin/reference-data/locations/add', data={'name': 'Base Atyrau'})
    with app.app_context():
        loc = Location.query.filter_by(name='Base Atyrau').first()
        assert loc is not None and loc.is_active
        loc_id = loc.id
    client.post(f'/admin/reference-data/locations/{loc_id}/rename',
                data={'name': 'Base Atyrau (Main)'})
    with app.app_context():
        assert Location.query.get(loc_id).name == 'Base Atyrau (Main)'
        assert AuditLog.query.filter_by(action='ref_locations_renamed').count() == 1


def test_duplicate_location_rejected(client, app):
    login(client, 'admin@test.kz', 'adminpass123')
    client.post('/admin/reference-data/locations/add', data={'name': 'Field A'})
    client.post('/admin/reference-data/locations/add', data={'name': 'Field A'})
    with app.app_context():
        assert Location.query.filter_by(name='Field A').count() == 1


def test_toggle_location(client, app):
    login(client, 'admin@test.kz', 'adminpass123')
    client.post('/admin/reference-data/locations/add', data={'name': 'Field B'})
    with app.app_context():
        loc_id = Location.query.filter_by(name='Field B').first().id
    client.post(f'/admin/reference-data/locations/{loc_id}/toggle')
    with app.app_context():
        assert Location.query.get(loc_id).is_active is False


def test_branding_company_name(client, app):
    login(client, 'admin@test.kz', 'adminpass123')
    client.post('/admin/branding', data={'company_name': 'Caspian Integrated Services'})
    with app.app_context():
        assert AppSetting.get('company_name') == 'Caspian Integrated Services'


def test_custom_prefix_used_in_numbering(client, app):
    login(client, 'admin@test.kz', 'adminpass123')
    client.post('/admin/numbering', data={'prefix_purchase_req': 'ЗАК'})
    client.post('/documents/new/purchase-requisition', data={
        'purpose': 'Prefix test', 'department': 'it', 'urgency': 'standard',
        'item_name[]': ['Thing'], 'item_unit[]': ['pc'], 'item_qty[]': ['1'],
        'item_note[]': [''], 'item_cost[]': ['10'], 'action': 'draft',
    })
    with app.app_context():
        doc = Document.query.first()
        assert doc.doc_number.startswith('ЗАК-')


def test_non_admin_cannot_change_reference_data(client, app):
    login(client, 'head@test.kz', 'headpass123')
    client.post('/admin/reference-data/locations/add', data={'name': 'Hacked'})
    with app.app_context():
        assert Location.query.filter_by(name='Hacked').first() is None
