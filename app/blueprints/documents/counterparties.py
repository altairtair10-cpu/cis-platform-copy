"""Справочник контрагентов: JSON для модального окна выбора + добавление."""
from flask import jsonify, request
from flask_login import login_required, current_user
from app import db
from app.models import Counterparty
from app.audit import log_action
from . import documents


@documents.route('/counterparties.json')
@login_required
def counterparties_json():
    rows = Counterparty.query.filter_by(is_active=True)\
                             .order_by(Counterparty.name).all()
    return jsonify([{
        'id': c.id, 'name': c.name, 'bin': c.bin or '', 'phone': c.phone or '',
        'address': c.address or '', 'contact_person': c.contact_person or '',
        'materials': c.materials or '', 'currency': c.currency or 'KZT',
    } for c in rows])


@documents.route('/counterparties/add', methods=['POST'])
@login_required
def counterparty_add():
    data = request.get_json(silent=True) or request.form
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'Название контрагента обязательно'}), 400
    existing = Counterparty.query.filter_by(name=name).first()
    if existing:
        if not existing.is_active:
            existing.is_active = True
            db.session.commit()
        return jsonify({'ok': True, 'id': existing.id, 'name': existing.name,
                        'existed': True})
    c = Counterparty(
        name=name[:256],
        bin=(data.get('bin') or '').strip()[:32] or None,
        address=(data.get('address') or '').strip()[:256] or None,
        phone=(data.get('phone') or '').strip()[:64] or None,
        email=(data.get('email') or '').strip()[:128] or None,
        contact_person=(data.get('contact_person') or '').strip()[:128] or None,
        materials=(data.get('materials') or '').strip()[:256] or None,
        currency=(data.get('currency') or 'KZT').strip()[:8],
        created_by=current_user.id,
    )
    db.session.add(c)
    db.session.flush()
    log_action('counterparty_added', 'counterparty', c.id, details=c.name)
    db.session.commit()
    return jsonify({'ok': True, 'id': c.id, 'name': c.name})
