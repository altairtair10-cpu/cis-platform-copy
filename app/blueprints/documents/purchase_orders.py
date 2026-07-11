"""РО на услуги и РО на товары."""
from datetime import datetime
from flask import (render_template, redirect, url_for, flash, request, abort,
                   jsonify, send_file)
from flask_login import login_required, current_user
from sqlalchemy import or_
from app import db
from app.models import (Document, DocumentItem, DocumentComment, DocumentApproval,
                        DocumentAttachment, DOC_TYPES, DOC_STATUSES, User,
                        Notification)
from app.decorators import requires_permission
from app.audit import log_action
from app.storage import save_upload, send_attachment, allowed_file, MAX_FILE_SIZE_MB
from . import documents
from .helpers import (_to_float, _unpack_extras, _is_assigned_approver,
                      _can_view_doc, _visible_docs_query, _panel_counts,
                      _build_route, _save_form_attachments, _notify_approvers,
                      _notify_current_approvers, PROCUREMENT_DOC_TYPES)


def _resolve_counterparty():
    """Возвращает (counterparty_id, name) из формы; имя берём из справочника."""
    from app.models import Counterparty
    cp_id = request.form.get('counterparty_id', type=int)
    if cp_id:
        cp = db.session.get(Counterparty, cp_id)
        if cp:
            return cp.id, cp.name
    return None, (request.form.get('counterparty') or '').strip()


@documents.route('/po-services/new', methods=['GET'])
@login_required
def new_po_services():
    from_req = request.args.get('from_req', type=int)
    linked_req = None
    if from_req:
        linked_req = Document.query.filter_by(id=from_req, doc_type='purchase_req').first()
    executors = User.query.filter_by(is_active=True).order_by(User.first_name, User.last_name).all()
    return render_template('documents/po_services.html', executors=executors,
                           linked_req=linked_req)


@documents.route('/po-services/submit', methods=['POST'])
@login_required
def submit_po_services():
    action = request.form.get('action', 'draft')
    cp_id, cp_name = _resolve_counterparty()
    signatory_id = request.form.get('signatory_id', type=int)

    if action == 'submit' and not signatory_id:
        action = 'draft'
        flash('Документ сохранён как черновик: не выбран Утверждающий. Укажите утверждающего и отправьте документ ещё раз.', 'warning')

    extras = {
        'Заказано': request.form.get('ordered_by'),
        'Плательщик НДС': request.form.get('vat_payer'),
        'Валюта': request.form.get('currency'),
        'Дата оплаты': request.form.get('payment_date'),
        'Основание': request.form.get('basis'),
        'Контрагент': cp_name,
        'Условия оплаты': request.form.get('payment_terms'),
        'Условия оказания услуг': request.form.get('service_terms'),
        'Срок оказания услуг': request.form.get('service_date'),
        'Статья бюджета': request.form.get('budget_line'),
    }
    extras_text = '\n'.join(f'{k}: {v}' for k, v in extras.items() if v)

    doc = Document(
        doc_type      = 'po_services',
        related_req_id = (request.form.get('related_req_id', type=int) or None),
        counterparty_id = cp_id,
        title         = request.form.get('summary', 'РО на услуги')[:100],
        department    = request.form.get('department', current_user.department),
        purpose       = request.form.get('summary'),
        justification = extras_text,
        author_id     = current_user.id,
        status        = 'pending' if action == 'submit' else 'draft',
        current_step  = 0,
    )

    service_date = request.form.get('service_date')
    if service_date:
        try:
            doc.needed_by = datetime.strptime(service_date, '%Y-%m-%d').date()
        except ValueError:
            pass

    db.session.add(doc)
    db.session.flush()
    doc.generate_number()
    log_action('document_created', 'document', doc.id, details=doc.doc_number)

    names = request.form.getlist('item_name[]')
    units = request.form.getlist('item_unit[]')
    qtys  = request.form.getlist('item_qty[]')
    costs = request.form.getlist('item_cost[]')

    for i, name in enumerate(names):
        if name.strip():
            db.session.add(DocumentItem(
                document_id = doc.id,
                name        = name.strip(),
                unit        = units[i] if i < len(units) else '',
                quantity    = float(qtys[i]) if i < len(qtys) and qtys[i] else None,
                note        = '',
                price       = _to_float(costs[i]) if i < len(costs) else None,
            ))

    db.session.add(DocumentComment(
        document_id = doc.id,
        author_id   = current_user.id,
        text        = f'РО на услуги {"отправлен на согласование" if action == "submit" else "сохранён как черновик"} пользователем {current_user.full_name}.',
        is_system   = True,
    ))

    _build_route(doc, action, signatory_id)
    _save_form_attachments(doc)

    req_id = request.form.get('related_req_id', type=int)
    if req_id:
        req = Document.query.filter_by(id=req_id, doc_type='purchase_req').first()
        if req and req.status in ('approved', 'in_execution'):
            req.status = 'in_execution'
            db.session.add(DocumentComment(
                document_id=req.id, author_id=current_user.id,
                text=f'Создан ПО по требованию (см. связанные документы).',
                is_system=True))
    db.session.commit()

    if action == 'submit':
        _notify_approvers(doc)

    db.session.commit()
    flash(f'Документ {doc.doc_number} {"отправлен на согласование" if action == "submit" else "сохранён как черновик"}.', 'success')
    return redirect(url_for('documents.view', doc_id=doc.id))


@documents.route('/po-services/<int:doc_id>/edit', methods=['GET'])
@login_required
def edit_po_services(doc_id):
    doc = Document.query.get_or_404(doc_id)
    if doc.author_id != current_user.id:
        abort(403)
    if doc.doc_type != 'po_services' or doc.status != 'returned':
        flash('Этот документ нельзя редактировать.', 'warning')
        return redirect(url_for('documents.view', doc_id=doc_id))
    extras = _unpack_extras(doc.justification)
    items = doc.items.all()
    return render_template('documents/po_services_edit.html', doc=doc, extras=extras, items=items)


@documents.route('/po-services/<int:doc_id>/update', methods=['POST'])
@login_required
def update_po_services(doc_id):
    doc = Document.query.get_or_404(doc_id)
    if doc.author_id != current_user.id:
        abort(403)
    if doc.doc_type != 'po_services' or doc.status != 'returned':
        flash('Этот документ нельзя редактировать.', 'warning')
        return redirect(url_for('documents.view', doc_id=doc_id))

    doc.title      = request.form.get('summary', doc.title)[:100]
    doc.purpose    = request.form.get('summary')
    doc.department = request.form.get('department', doc.department)

    extras = {
        'Заказано': request.form.get('ordered_by'),
        'Плательщик НДС': request.form.get('vat_payer'),
        'Валюта': request.form.get('currency'),
        'Дата оплаты': request.form.get('payment_date'),
        'Основание': request.form.get('basis'),
        'Контрагент': cp_name,
        'Условия оплаты': request.form.get('payment_terms'),
        'Условия оказания услуг': request.form.get('service_terms'),
        'Срок оказания услуг': request.form.get('service_date'),
        'Статья бюджета': request.form.get('budget_line'),
    }
    doc.justification = '\n'.join(f'{k}: {v}' for k, v in extras.items() if v)

    service_date = request.form.get('service_date')
    if service_date:
        try:
            doc.needed_by = datetime.strptime(service_date, '%Y-%m-%d').date()
        except ValueError:
            pass

    for it in doc.items.all():
        db.session.delete(it)
    names = request.form.getlist('item_name[]')
    units = request.form.getlist('item_unit[]')
    qtys  = request.form.getlist('item_qty[]')
    costs = request.form.getlist('item_cost[]')
    for i, name in enumerate(names):
        if name.strip():
            db.session.add(DocumentItem(
                document_id=doc.id,
                name=name.strip(),
                unit=units[i] if i < len(units) else '',
                quantity=float(qtys[i]) if i < len(qtys) and qtys[i] else None,
                note='',
                price=_to_float(costs[i]) if i < len(costs) else None,
            ))

    _save_form_attachments(doc)

    action = request.form.get('action', 'save')
    if action == 'submit':
        doc.status = 'pending'
        db.session.add(DocumentComment(
            document_id=doc.id, author_id=current_user.id,
            text=f'Документ отредактирован и повторно отправлен на согласование пользователем {current_user.full_name}.',
            is_system=True,
        ))
        _notify_current_approvers(doc, f'Документ повторно на согласовании: {doc.doc_number}')
        msg = 'Документ отредактирован и отправлен на согласование.'
    else:
        db.session.add(DocumentComment(
            document_id=doc.id, author_id=current_user.id,
            text=f'Документ обновлён пользователем {current_user.full_name} (черновик доработки).',
            is_system=True,
        ))
        msg = 'Изменения сохранены. Документ всё ещё на доработке.'

    db.session.commit()
    flash(msg, 'success')
    return redirect(url_for('documents.view', doc_id=doc.id))


@documents.route('/po-trebovanie/new', methods=['GET'])
@login_required
def new_po_trebovanie():
    executors = User.query.filter_by(is_active=True).order_by(User.first_name, User.last_name).all()
    requisitions = Document.query.filter(
        Document.doc_type == 'purchase_req',
        Document.status != 'draft')\
        .order_by(Document.created_at.desc()).limit(200).all()
    return render_template('documents/po_trebovanie.html', executors=executors,
                           requisitions=requisitions)


@documents.route('/po-trebovanie/submit', methods=['POST'])
@login_required
def submit_po_trebovanie():
    action = request.form.get('action', 'draft')
    cp_id, cp_name = _resolve_counterparty()
    related_req_id = request.form.get('related_req_id', type=int) or None
    related_req = None
    if related_req_id:
        related_req = Document.query.filter_by(id=related_req_id,
                                               doc_type='purchase_req').first()
        related_req_id = related_req.id if related_req else None
    signatory_id = request.form.get('signatory_id', type=int)

    if action == 'submit' and not signatory_id:
        action = 'draft'
        flash('Документ сохранён как черновик: не выбран Утверждающий. Укажите утверждающего и отправьте документ ещё раз.', 'warning')

    extras = {
        'Основание': request.form.get('basis'),
        'Группа материалов': (request.form.getlist('group_name[]') or [''])[0] or None,
        'Требование на приобретение материалов':
            (f'{related_req.doc_number} — {related_req.title[:60]}' if related_req else None),
        'Контрагент': cp_name,
        'Плательщик НДС': request.form.get('vat_payer'),
        'Заказано': request.form.get('ordered_by'),
        'Валюта': request.form.get('currency'),
        'Дата оплаты': request.form.get('payment_date'),
        'Условия оплаты': request.form.get('payment_terms'),
        'Условия оказания услуг': request.form.get('service_terms'),
        'Срок оказания услуг': request.form.get('service_date'),
        'Статья бюджета': request.form.get('budget_line'),
    }
    extras_text = '\n'.join(f'{k}: {v}' for k, v in extras.items() if v)

    doc = Document(
        doc_type      = 'po_trebovanie',
        related_req_id = related_req_id,
        counterparty_id = cp_id,
        title         = request.form.get('summary', 'РО на товары')[:100],
        department    = request.form.get('department', current_user.department),
        purpose       = request.form.get('summary'),
        justification = extras_text,
        author_id     = current_user.id,
        status        = 'pending' if action == 'submit' else 'draft',
        current_step  = 0,
    )

    payment_date = request.form.get('payment_date')
    if payment_date:
        try:
            doc.needed_by = datetime.strptime(payment_date, '%Y-%m-%d').date()
        except ValueError:
            pass

    db.session.add(doc)
    db.session.flush()
    doc.generate_number()
    log_action('document_created', 'document', doc.id, details=doc.doc_number)

    names = request.form.getlist('item_name[]')
    units = request.form.getlist('item_unit[]')
    qtys  = request.form.getlist('item_qty[]')
    costs = request.form.getlist('item_cost[]')
    codes = request.form.getlist('item_code[]')

    for i, name in enumerate(names):
        if name.strip():
            db.session.add(DocumentItem(
                document_id = doc.id,
                name        = name.strip(),
                unit        = units[i] if i < len(units) else '',
                quantity    = float(qtys[i]) if i < len(qtys) and qtys[i] else None,
                note        = codes[i] if i < len(codes) else '',
                price       = _to_float(costs[i]) if i < len(costs) else None,
            ))

    db.session.add(DocumentComment(
        document_id = doc.id,
        author_id   = current_user.id,
        text        = f'РО на товары {"отправлена на согласование" if action == "submit" else "сохранена как черновик"} пользователем {current_user.full_name}.',
        is_system   = True,
    ))

    _build_route(doc, action, signatory_id)
    _save_form_attachments(doc)

    db.session.commit()

    if action == 'submit':
        _notify_approvers(doc)

    db.session.commit()
    flash(f'Документ {doc.doc_number} {"отправлен на согласование" if action == "submit" else "сохранён как черновик"}.', 'success')
    return redirect(url_for('documents.view', doc_id=doc.id))


@documents.route('/po-trebovanie/<int:doc_id>/edit', methods=['GET'])
@login_required
def edit_po_trebovanie(doc_id):
    doc = Document.query.get_or_404(doc_id)
    if doc.author_id != current_user.id:
        abort(403)
    if doc.doc_type != 'po_trebovanie' or doc.status != 'returned':
        flash('Этот документ нельзя редактировать.', 'warning')
        return redirect(url_for('documents.view', doc_id=doc_id))
    extras = _unpack_extras(doc.justification)
    items = doc.items.all()
    return render_template('documents/po_trebovanie_edit.html', doc=doc, extras=extras, items=items)


@documents.route('/po-trebovanie/<int:doc_id>/update', methods=['POST'])
@login_required
def update_po_trebovanie(doc_id):
    doc = Document.query.get_or_404(doc_id)
    if doc.author_id != current_user.id:
        abort(403)
    if doc.doc_type != 'po_trebovanie' or doc.status != 'returned':
        flash('Этот документ нельзя редактировать.', 'warning')
        return redirect(url_for('documents.view', doc_id=doc_id))

    doc.title      = request.form.get('summary', doc.title)[:100]
    doc.purpose    = request.form.get('summary')
    doc.department = request.form.get('department', doc.department)

    extras = {
        'Основание': request.form.get('basis'),
        'Группа материалов': (request.form.getlist('group_name[]') or [''])[0] or None,
        'Требование на приобретение материалов':
            (f'{related_req.doc_number} — {related_req.title[:60]}' if related_req else None),
        'Контрагент': cp_name,
        'Плательщик НДС': request.form.get('vat_payer'),
        'Заказано': request.form.get('ordered_by'),
        'Валюта': request.form.get('currency'),
        'Дата оплаты': request.form.get('payment_date'),
        'Условия оплаты': request.form.get('payment_terms'),
        'Условия оказания услуг': request.form.get('service_terms'),
        'Срок оказания услуг': request.form.get('service_date'),
        'Статья бюджета': request.form.get('budget_line'),
    }
    doc.justification = '\n'.join(f'{k}: {v}' for k, v in extras.items() if v)

    payment_date = request.form.get('payment_date')
    if payment_date:
        try:
            doc.needed_by = datetime.strptime(payment_date, '%Y-%m-%d').date()
        except ValueError:
            pass

    for it in doc.items.all():
        db.session.delete(it)
    names = request.form.getlist('item_name[]')
    units = request.form.getlist('item_unit[]')
    qtys  = request.form.getlist('item_qty[]')
    costs = request.form.getlist('item_cost[]')
    codes = request.form.getlist('item_code[]')
    for i, name in enumerate(names):
        if name.strip():
            db.session.add(DocumentItem(
                document_id=doc.id,
                name=name.strip(),
                unit=units[i] if i < len(units) else '',
                quantity=float(qtys[i]) if i < len(qtys) and qtys[i] else None,
                note=codes[i] if i < len(codes) else '',
                price=_to_float(costs[i]) if i < len(costs) else None,
            ))

    _save_form_attachments(doc)

    action = request.form.get('action', 'save')
    if action == 'submit':
        doc.status = 'pending'
        db.session.add(DocumentComment(
            document_id=doc.id, author_id=current_user.id,
            text=f'Документ отредактирован и повторно отправлен на согласование пользователем {current_user.full_name}.',
            is_system=True,
        ))
        _notify_current_approvers(doc, f'Документ повторно на согласовании: {doc.doc_number}')
        msg = 'Документ отредактирован и отправлен на согласование.'
    else:
        db.session.add(DocumentComment(
            document_id=doc.id, author_id=current_user.id,
            text=f'Документ обновлён пользователем {current_user.full_name} (черновик доработки).',
            is_system=True,
        ))
        msg = 'Изменения сохранены. Документ всё ещё на доработке.'

    db.session.commit()
    flash(msg, 'success')
    return redirect(url_for('documents.view', doc_id=doc.id))
