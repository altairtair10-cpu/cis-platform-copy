from conftest import login
from app import db
from app.models import User, AuditLog


def test_hidden_when_unconfigured(client):
    body = client.get('/auth/login').get_data(as_text=True)
    assert 'ms/login' not in body
    assert client.get('/auth/ms/login').status_code == 404


def _enable(monkeypatch):
    monkeypatch.setenv('AZURE_CLIENT_ID', 'cid')
    monkeypatch.setenv('AZURE_CLIENT_SECRET', 'secret')
    monkeypatch.setenv('AZURE_TENANT_ID', 'tid')


def test_button_shown_when_configured(client, monkeypatch):
    _enable(monkeypatch)
    body = client.get('/auth/login').get_data(as_text=True)
    assert 'ms/login' in body


def test_login_redirects_to_microsoft(client, monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setattr('app.services.ms_auth.build_auth_url',
                        lambda uri, state: f'https://login.microsoftonline.com/x?state={state}')
    r = client.get('/auth/ms/login')
    assert r.status_code == 302
    assert 'login.microsoftonline.com' in r.headers['Location']


def _callback(client, monkeypatch, claims, state='s1'):
    _enable(monkeypatch)
    monkeypatch.setattr('app.services.ms_auth.acquire_token',
                        lambda code, uri: {'id_token_claims': claims})
    with client.session_transaction() as sess:
        sess['ms_auth_state'] = state
    return client.get(f'/auth/ms/callback?code=abc&state={state}',
                      follow_redirects=True)


def test_callback_logs_in_existing_user(client, app, monkeypatch):
    r = _callback(client, monkeypatch,
                  {'preferred_username': 'MECH@test.kz', 'name': 'Mech Test'})
    assert r.status_code == 200
    with app.app_context():
        assert AuditLog.query.filter_by(action='login_microsoft').count() == 1


def test_callback_provisions_new_user(client, app, monkeypatch):
    _callback(client, monkeypatch,
              {'preferred_username': 'new.person@cis.kz', 'name': 'Новый Сотрудник'})
    with app.app_context():
        u = User.query.filter_by(email='new.person@cis.kz').first()
        assert u is not None and u.is_active and u.role == 'field'
        assert u.first_name == 'Новый'


def test_callback_rejects_bad_state(client, app, monkeypatch):
    r = _callback(client, monkeypatch,
                  {'preferred_username': 'mech@test.kz'}, state='forged')
    # state в сессии s1... подделанный не совпадает
    with client.session_transaction() as sess:
        sess['ms_auth_state'] = 'real'
    _enable(monkeypatch)
    r = client.get('/auth/ms/callback?code=abc&state=fake', follow_redirects=True)
    body = r.get_data(as_text=True)
    assert 'Не удалось проверить' in body


def test_inactive_user_blocked(client, app, monkeypatch):
    with app.app_context():
        u = User.query.filter_by(email='gone@test.kz').first()
        assert u.is_active is False
    r = _callback(client, monkeypatch, {'preferred_username': 'gone@test.kz'})
    assert 'деактивирована' in r.get_data(as_text=True)
