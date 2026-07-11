from conftest import login
from app import db
from app.models import User, AuditLog


def _mech_id(app):
    with app.app_context():
        return User.query.filter_by(email='mech@test.kz').first().id


def test_admin_can_view_as_and_return(client, app):
    mech_id = _mech_id(app)
    login(client, 'admin@test.kz', 'adminpass123')
    r = client.post(f'/auth/users/{mech_id}/impersonate', follow_redirects=True)
    body = r.get_data(as_text=True)
    assert 'Режим просмотра' in body
    # видим сайт с правами механика: админ-панель недоступна
    assert client.get('/admin/').status_code == 403
    # возвращаемся
    client.post('/auth/impersonate/stop')
    assert client.get('/admin/').status_code == 200
    with app.app_context():
        assert AuditLog.query.filter_by(action='impersonate_start').count() == 1
        assert AuditLog.query.filter_by(action='impersonate_stop').count() == 1


def test_non_admin_cannot_impersonate(client, app):
    mech_id = _mech_id(app)
    login(client, 'head@test.kz', 'headpass123')
    client.post(f'/auth/users/{mech_id}/impersonate', follow_redirects=True)
    body = client.get('/dashboard').get_data(as_text=True)
    assert 'Режим просмотра' not in body


def test_no_nested_impersonation(client, app):
    mech_id = _mech_id(app)
    with app.app_context():
        head_id = User.query.filter_by(email='head@test.kz').first().id
    login(client, 'admin@test.kz', 'adminpass123')
    client.post(f'/auth/users/{mech_id}/impersonate')
    # попытка вложенного «войти как» из-под механика
    r = client.post(f'/auth/users/{head_id}/impersonate', follow_redirects=True)
    assert 'Доступ запрещён' in r.get_data(as_text=True)


def test_inactive_target_blocked(client, app):
    with app.app_context():
        gone_id = User.query.filter_by(email='gone@test.kz').first().id
    login(client, 'admin@test.kz', 'adminpass123')
    r = client.post(f'/auth/users/{gone_id}/impersonate', follow_redirects=True)
    assert 'деактивирован' in r.get_data(as_text=True)
