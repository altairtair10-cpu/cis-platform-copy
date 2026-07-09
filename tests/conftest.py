import pytest
from app import create_app, db
from app.models import User


@pytest.fixture
def app():
    app = create_app('testing')
    with app.app_context():
        db.create_all()

        def make(email, role, dept, pwd):
            u = User(first_name=role.title(), last_name='Test', email=email,
                     role=role, department=dept, language='ru', is_active=True)
            u.set_password(pwd)
            db.session.add(u)
            return u

        make('admin@test.kz', 'it_admin', 'it', 'adminpass123')
        make('head@test.kz', 'dept_head', 'it', 'headpass123')
        make('mech@test.kz', 'mechanic', 'mechanic', 'mechpass123')
        inactive = make('gone@test.kz', 'field', 'field', 'gonepass123')
        inactive.is_active = False
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def login(client, email, password):
    return client.post('/auth/login',
                       data={'email': email, 'password': password},
                       follow_redirects=True)
