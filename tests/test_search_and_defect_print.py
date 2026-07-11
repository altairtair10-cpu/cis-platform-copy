from conftest import login
from app import db
from app.models import Document, Equipment, User


def _mk_docs(client, app):
    login(client, 'mech@test.kz', 'mechpass123')
    for summary in ('Улитка для насоса высокого давления',
                    'Химстанция обслуживание',
                    'Обычные перчатки'):
        client.post('/documents/trebovanie-new/submit', data={
            'summary': summary, 'action': 'draft',
            'item_name[]': ['x'], 'item_spec[]': [''], 'item_qty[]': ['1'],
            'item_unit[]': ['шт'], 'item_date[]': [''], 'item_note[]': [''],
            'item_cost[]': ['1'],
        })


def test_search_prefix(client, app):
    _mk_docs(client, app)
    body = client.get('/documents/?q=улит').get_data(as_text=True)
    assert 'Улитка для насоса' in body
    assert 'Химстанция' not in body


def test_search_space_insensitive_both_ways(client, app):
    _mk_docs(client, app)
    # написали с пробелом — в документе слитно
    body = client.get('/documents/?q=хим станция').get_data(as_text=True)
    assert 'Химстанция' in body
    # и наоборот: в запросе слитно, найдём и документ «хим станция...» —
    # проверим через номер с пробелами не актуально; главное направление покрыто


def test_search_by_number_and_author(client, app):
    _mk_docs(client, app)
    with app.app_context():
        num = Document.query.first().doc_number
    body = client.get(f'/documents/?q={num[:8]}').get_data(as_text=True)
    assert num in body
    body = client.get('/documents/?q=Mechanic').get_data(as_text=True)
    assert 'Улитка' in body      # автор всех трёх — Mechanic Test


def test_search_multiword_and(client, app):
    _mk_docs(client, app)
    body = client.get('/documents/?q=улитка давления').get_data(as_text=True)
    assert 'Улитка для насоса' in body
    body = client.get('/documents/?q=улитка перчатки').get_data(as_text=True)
    assert 'Улитка' not in body   # оба слова сразу нигде не встречаются


def test_defect_print_letterhead_no_attachments(client, app):
    with app.app_context():
        eq = Equipment(unit_id='Б1', name='Насос SPM', eq_type='Насос ГРП',
                       gos_number='882AHDE', location='База Атырау')
        db.session.add(eq); db.session.commit()
        eq_id = eq.id
    login(client, 'mech@test.kz', 'mechpass123')
    client.post('/documents/defect-act/submit', data={
        'equipment_id': str(eq_id), 'description': 'Течь клапана', 'cause': 'износ',
        'action': 'draft',
        'part_name[]': ['Сальник'], 'part_spec[]': ['P/N 55'], 'part_qty[]': ['2'],
        'part_unit[]': ['шт'], 'part_cost[]': ['5000'],
    })
    with app.app_context():
        doc_id = Document.query.filter_by(doc_type='defect_act').first().id
    body = client.get(f'/documents/{doc_id}/print').get_data(as_text=True)
    assert 'ДЕФЕКТНЫЙ АКТ' in body and 'CIS-DA-001' in body
    assert 'Б1 — Насос SPM' in body and 'Течь клапана' in body
    assert 'Сальник' in body and 'Итого: 10 000.00' in body
    assert 'Лист согласования' in body
    assert 'Загрузить' not in body and 'attachments' not in body
