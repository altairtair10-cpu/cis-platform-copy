from conftest import login
from app import db
from app.models import User, AuditLog


def test_login_success(client):
    resp = login(client, 'admin@test.kz', 'adminpass123')
    assert resp.status_code == 200
    # audit row written
    with client.application.app_context():
        assert AuditLog.query.filter_by(action='login').count() == 1


def test_login_wrong_password(client):
    resp = login(client, 'admin@test.kz', 'wrong')
    assert 'Invalid email or password' in resp.get_data(as_text=True)
    with client.application.app_context():
        assert AuditLog.query.filter_by(action='login_failed').count() == 1


def test_inactive_user_cannot_login(client):
    resp = login(client, 'gone@test.kz', 'gonepass123')
    assert 'Invalid email or password' in resp.get_data(as_text=True)


def test_open_redirect_blocked(client):
    resp = client.post('/auth/login?next=https://evil.example.com',
                       data={'email': 'admin@test.kz', 'password': 'adminpass123'})
    assert resp.status_code == 302
    assert 'evil.example.com' not in resp.headers['Location']


def test_must_change_password_redirects(client, app):
    with app.app_context():
        u = User.query.filter_by(email='mech@test.kz').first()
        u.must_change_password = True
        db.session.commit()
    login(client, 'mech@test.kz', 'mechpass123')
    resp = client.get('/dashboard')
    assert resp.status_code == 302
    assert '/auth/settings' in resp.headers['Location']


def test_password_change_clears_flag(client, app):
    with app.app_context():
        u = User.query.filter_by(email='mech@test.kz').first()
        u.must_change_password = True
        db.session.commit()
    login(client, 'mech@test.kz', 'mechpass123')
    client.post('/auth/settings/password', data={
        'current_password': 'mechpass123',
        'new_password': 'newsecurepass1',
        'confirm_password': 'newsecurepass1',
    })
    with app.app_context():
        u = User.query.filter_by(email='mech@test.kz').first()
        assert u.must_change_password is False
        assert u.check_password('newsecurepass1')
