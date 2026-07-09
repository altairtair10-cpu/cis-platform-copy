from conftest import login


def test_hr_requires_permission(client):
    login(client, 'mech@test.kz', 'mechpass123')
    resp = client.get('/hr/')
    assert resp.status_code == 403


def test_user_management_admin_only(client):
    login(client, 'mech@test.kz', 'mechpass123')
    resp = client.get('/auth/users')
    assert resp.status_code == 302  # redirected away


def test_admin_can_open_user_management(client):
    login(client, 'admin@test.kz', 'adminpass123')
    resp = client.get('/auth/users')
    assert resp.status_code == 200


def test_anonymous_redirected_to_login(client):
    resp = client.get('/dashboard')
    assert resp.status_code == 302
    assert '/auth/login' in resp.headers['Location']
