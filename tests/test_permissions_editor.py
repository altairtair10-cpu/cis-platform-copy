from conftest import login
from app import db
from app.models import RolePermission


def test_defaults_apply_without_db_rows(client):
    login(client, 'mech@test.kz', 'mechpass123')
    assert client.get('/equipment/').status_code == 200


def test_matrix_page_admin_only(client):
    login(client, 'mech@test.kz', 'mechpass123')
    assert client.get('/admin/permissions').status_code == 403
    client.get('/auth/logout')
    login(client, 'admin@test.kz', 'adminpass123')
    assert client.get('/admin/permissions').status_code == 200


def test_grant_module_via_matrix(client, app):
    login(client, 'admin@test.kz', 'adminpass123')
    # give field workers equipment access, keep their defaults minimal
    client.post('/admin/permissions', data={
        'perm_field': ['dashboard_limited', 'documents_own', 'pto_own', 'equipment'],
    })
    from app.models import User
    with app.app_context():
        u = User(first_name='F', last_name='W', email='fw2@test.kz',
                 role='field', is_active=True)
        u.set_password('fieldpass123')
        db.session.add(u); db.session.commit()
    client.get('/auth/logout')
    login(client, 'fw2@test.kz', 'fieldpass123')
    assert client.get('/equipment/dashboard').status_code == 200


def test_revoke_all_means_none_not_defaults(client, app):
    login(client, 'admin@test.kz', 'adminpass123')
    client.post('/admin/permissions', data={})   # every editable role: nothing
    with app.app_context():
        assert RolePermission.query.filter_by(role='mechanic', module='__none__').count() == 1
    client.get('/auth/logout')
    login(client, 'mech@test.kz', 'mechpass123')
    assert client.get('/equipment/').status_code == 403


def test_it_admin_unaffected_by_matrix(client):
    login(client, 'admin@test.kz', 'adminpass123')
    client.post('/admin/permissions', data={})
    assert client.get('/equipment/').status_code == 200
