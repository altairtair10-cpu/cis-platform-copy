from conftest import login
from app.models import AppSetting


def test_dashboard_page_requires_equipment_permission(client, app):
    # field role has no 'equipment' permission
    from app import db
    from app.models import User
    with app.app_context():
        u = User(first_name='Field', last_name='Worker', email='fw@test.kz',
                 role='field', is_active=True)
        u.set_password('fieldpass123')
        db.session.add(u); db.session.commit()
    login(client, 'fw@test.kz', 'fieldpass123')
    assert client.get('/equipment/dashboard').status_code == 403


def test_dashboard_shows_setup_notice_when_unconfigured(client):
    login(client, 'mech@test.kz', 'mechpass123')
    resp = client.get('/equipment/dashboard')
    assert resp.status_code == 200
    assert 'iframe' not in resp.get_data(as_text=True)


def test_admin_sets_url_and_iframe_appears(client, app):
    login(client, 'admin@test.kz', 'adminpass123')
    client.post('/admin/integrations',
                data={'equipment_dashboard_url': 'https://dash.example.com'})
    with app.app_context():
        assert AppSetting.get('equipment_dashboard_url') == 'https://dash.example.com'
    resp = client.get('/equipment/dashboard')
    assert 'https://dash.example.com' in resp.get_data(as_text=True)
    assert '<iframe' in resp.get_data(as_text=True)


def test_invalid_url_rejected(client, app):
    login(client, 'admin@test.kz', 'adminpass123')
    client.post('/admin/integrations',
                data={'equipment_dashboard_url': 'javascript:alert(1)'})
    with app.app_context():
        assert AppSetting.get('equipment_dashboard_url') is None
