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


def test_admin_cannot_demote_self(client, app):
    with app.app_context():
        admin_id = User.query.filter_by(email='admin@test.kz').first().id
    login(client, 'admin@test.kz', 'adminpass123')
    r = client.post(f'/auth/users/{admin_id}/edit', data={
        'full_name': 'Admin Test', 'email': 'admin@test.kz', 'role': 'mechanic',
        'department': 'it', 'language': 'ru', 'is_active': 'y',
    }, follow_redirects=True)
    assert 'с самого себя' in r.get_data(as_text=True)
    with app.app_context():
        assert db.session.get(User, admin_id).role == 'it_admin'


def test_cannot_remove_last_admin_via_other_admin(client, app):
    with app.app_context():
        admin2 = User(first_name='Second', last_name='Admin', email='admin2@test.kz',
                      role='it_admin', is_active=True)
        admin2.set_password('adminpass456')
        db.session.add(admin2); db.session.commit()
        a2_id = admin2.id
    login(client, 'admin@test.kz', 'adminpass123')
    # понизить второго админа можно — первый остаётся
    client.post(f'/auth/users/{a2_id}/edit', data={
        'full_name': 'Second Admin', 'email': 'admin2@test.kz', 'role': 'field',
        'department': 'it', 'language': 'ru', 'is_active': 'y',
    })
    with app.app_context():
        assert db.session.get(User, a2_id).role == 'field'
