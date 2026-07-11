from conftest import login
from app import db
from app.models import AuditLog, User


def test_security_headers_present(client):
    r = client.get('/auth/login')
    assert r.headers.get('X-Content-Type-Options') == 'nosniff'
    assert r.headers.get('X-Frame-Options') == 'SAMEORIGIN'
    assert r.headers.get('Referrer-Policy') == 'strict-origin-when-cross-origin'


def test_audit_page_admin_only(client):
    login(client, 'mech@test.kz', 'mechpass123')
    assert client.get('/admin/audit').status_code == 403


def test_audit_page_lists_and_filters(client, app):
    login(client, 'admin@test.kz', 'adminpass123')   # пишет action='login'
    r = client.get('/admin/audit')
    assert r.status_code == 200
    assert 'login' in r.get_data(as_text=True)
    # фильтр по действию
    r = client.get('/admin/audit?action=login')
    assert 'login' in r.get_data(as_text=True)
    r = client.get('/admin/audit?action=nonexistent_action_xyz')
    assert 'nonexistent' not in r.get_data(as_text=True).replace('nonexistent_action_xyz', '', 1)


def test_scheduler_not_started_in_testing(app):
    assert 'scheduler' not in app.extensions


def test_run_locked_executes_on_sqlite(app):
    from app.scheduler import _run_locked
    hits = []
    _run_locked(app, 999, lambda: hits.append(1))
    assert hits == [1]


def test_inventory_cache_ttl(monkeypatch):
    from app.blueprints import inventory as inv
    inv._CACHE.clear()
    calls = []
    def loader():
        calls.append(1)
        return ['data']
    assert inv._cached('k', loader) == ['data']
    assert inv._cached('k', loader) == ['data']
    assert len(calls) == 1          # второй раз — из кэша
    inv._CACHE['k'] = (0, ['stale'])   # протух
    assert inv._cached('k', loader) == ['data']
    assert len(calls) == 2
