from conftest import login
from app import db
from app.models import User


def _set_lang(app, email, lang):
    with app.app_context():
        u = User.query.filter_by(email=email).first()
        u.language = lang
        db.session.commit()


def test_russian_default(client, app):
    _set_lang(app, 'mech@test.kz', 'ru')
    login(client, 'mech@test.kz', 'mechpass123')
    body = client.get('/equipment/').get_data(as_text=True)
    assert 'Оборудование' in body


def test_english_translation(client, app):
    _set_lang(app, 'mech@test.kz', 'en')
    login(client, 'mech@test.kz', 'mechpass123')
    body = client.get('/equipment/').get_data(as_text=True)
    assert 'Equipment' in body


def test_kazakh_translation(client, app):
    _set_lang(app, 'mech@test.kz', 'kz')
    login(client, 'mech@test.kz', 'mechpass123')
    body = client.get('/equipment/').get_data(as_text=True)
    assert 'Жабдықтар' in body


def test_anonymous_pages_render(client):
    assert client.get('/auth/login').status_code == 200
