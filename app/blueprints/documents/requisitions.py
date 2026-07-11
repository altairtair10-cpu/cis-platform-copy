"""Требования на приобретение материалов."""
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


@documents.route('/new/purchase-requisition', methods=['GET', 'POST'])
@login_required
def new_purchase_req():
    """Old wizard — funnels into the single full form (kept for old links/tests)."""
    if request.method == 'POST':
        return submit_trebovanie_new()
    return redirect(url_for('documents.new_trebovanie_new',
                            from_defect=request.args.get('from_defect')))


@documents.route('/trebovanie/new', methods=['GET'])
@login_required
def new_trebovanie():
    """Old entry point — everything funnels into the single full form."""
    return redirect(url_for('documents.new_trebovanie_new',
                            from_defect=request.args.get('from_defect')))


@documents.route('/trebovanie/submit', methods=['POST'])
@login_required
def submit_trebovanie():
    executor_id = request.form.get('executor_id', type=int) or current_user.id
    action = request.form.get('action', 'draft')
    related_defect_id = request.form.get('related_defect_id', type=int)
    if related_defect_id:
        rel = Document.query.filter_by(id=related_defect_id, doc_type='defect_act').first()
        related_defect_id = rel.id if rel else None
    signatory_id = request.form.get('signatory_id', type=int)

    if action == 'submit' and not signatory_id:
        action = 'draft'
        flash('Документ сохранён как черновик: не выбран Утверждающий. Укажите утверждающего и отправьте документ ещё раз.', 'warning')

    doc = Document(
        doc_type      = 'purchase_req',
        title         = request.form.get('summary', 'Требование на приобретение')[:100],
        department    = request.form.get('department', current_user.department),
        urgency       = request.form.get('urgency', 'standard'),
        purpose       = request.form.get('summary'),
        justification = request.form.get('note'),
        author_id     = current_user.id,
        executor_id   = executor_id,
        related_defect_id = related_defect_id,
        status        = 'pending' if action == 'submit' else 'draft',
    )

    needed_by = request.form.get('needed_by')
    if needed_by:
        try:
            doc.needed_by = datetime.strptime(needed_by, '%Y-%m-%d').date()
        except ValueError:
            pass

    db.session.add(doc)
    db.session.flush()
    doc.generate_number()
    log_action('document_created', 'document', doc.id, details=doc.doc_number)

    _save_form_attachments(doc)

    names = request.form.getlist('item_name[]')
    specs = request.form.getlist('item_spec[]')
    qtys  = request.form.getlist('item_qty[]')
    units = request.form.getlist('item_unit[]')
    costs = request.form.getlist('item_cost[]')

    for i, name in enumerate(names):
        if name.strip():
            db.session.add(DocumentItem(
                document_id = doc.id,
                name        = name.strip(),
                unit        = units[i] if i < len(units) else 'шт',
                quantity    = float(qtys[i]) if i < len(qtys) and qtys[i] else None,
                note        = specs[i] if i < len(specs) else '',
                price       = _to_float(costs[i]) if i < len(costs) else None,
            ))

    db.session.add(DocumentComment(
        document_id = doc.id,
        author_id   = current_user.id,
        text        = f'Требование {"отправлено на согласование" if action == "submit" else "сохранено как черновик"} пользователем {current_user.full_name}.',
        is_system   = True,
    ))

    _build_route(doc, action, signatory_id)

    approvers = User.query.filter(
        User.role.in_(['dept_head', 'director', 'it_admin']),
        User.is_active == True
    ).all()
    for approver in approvers:
        db.session.add(Notification(
            user_id = approver.id,
            title   = f'Новый документ на согласовании: {doc.doc_number}',
            body    = doc.title[:100],
            link    = f'/documents/{doc.id}',
            is_read = False,
        ))

    db.session.commit()
    flash(f'Документ {doc.doc_number} {"отправлен на согласование" if action == "submit" else "сохранён как черновик"}.', 'success')
    return redirect(url_for('documents.view', doc_id=doc.id))


@documents.route('/trebovanie-new/new', methods=['GET'])
@login_required
def new_trebovanie_new():
    import json as _json
    from app.models import RouteTemplate
    now = datetime.now().strftime('%d.%m.%Y %H:%M')
    executors = User.query.filter_by(is_active=True).order_by(User.first_name, User.last_name).all()
    approvers = User.query.filter(User.is_active==True, User.role.in_(['dept_head', 'director', 'it_admin'])).order_by(User.first_name, User.last_name).all()
    open_defects = Document.query.filter_by(doc_type='defect_act', defect_closed=False)\
                                 .order_by(Document.created_at.desc()).limit(100).all()
    from_defect = request.args.get('from_defect', type=int)
    route_templates = RouteTemplate.query.order_by(RouteTemplate.name).all()
    templates_json = _json.dumps(
        [{'id': t.id, 'name': t.name, 'data': _json.loads(t.data)} for t in route_templates],
        ensure_ascii=False)
    return render_template('documents/trebovanie_new.html', now=now, executors=executors,
                           approvers=approvers, open_defects=open_defects,
                           from_defect=from_defect, templates_json=templates_json)


@documents.route('/trebovanie-new/submit', methods=['POST'])
@login_required
def submit_trebovanie_new():
    action = request.form.get('action', 'draft')
    executor_id = request.form.get('executor_id', type=int) or current_user.id
    signatory_id = request.form.get('signatory_id', type=int)

    if action == 'submit' and not signatory_id:
        action = 'draft'
        flash('Документ сохранён как черновик: не выбран Утверждающий. Укажите утверждающего и отправьте документ ещё раз.', 'warning')

    related_defect_id = request.form.get('related_defect_id', type=int) or None
    if related_defect_id:
        rel = Document.query.filter_by(id=related_defect_id, doc_type='defect_act').first()
        related_defect_id = rel.id if rel else None

    doc = Document(
        doc_type      = 'purchase_req',
        related_defect_id = related_defect_id,
        title         = request.form.get('summary', 'Требование на приобретение материалов')[:100],
        purpose       = request.form.get('summary'),
        justification = request.form.get('linked_to'),
        author_id     = current_user.id,
        executor_id   = executor_id,
        status        = 'pending' if action == 'submit' else 'draft',
        current_step  = 0,
    )

    needed_by = request.form.get('needed_by')
    if needed_by:
        doc.needed_by = datetime.strptime(needed_by, '%Y-%m-%d').date()

    db.session.add(doc)
    db.session.flush()
    doc.generate_number()
    log_action('document_created', 'document', doc.id, details=doc.doc_number)

    names = request.form.getlist('item_name[]')
    specs = request.form.getlist('item_spec[]')
    qtys  = request.form.getlist('item_qty[]')
    units = request.form.getlist('item_unit[]')
    dates = request.form.getlist('item_date[]')
    notes = request.form.getlist('item_note[]')
    costs = request.form.getlist('item_cost[]')

    for i, name in enumerate(names):
        if name.strip():
            db.session.add(DocumentItem(
                document_id = doc.id,
                name        = name.strip(),
                unit        = units[i] if i < len(units) else 'шт',
                quantity    = float(qtys[i]) if i < len(qtys) and qtys[i] else None,
                note        = notes[i] if i < len(notes) else '',
                price       = _to_float(costs[i]) if i < len(costs) else None,
            ))

    db.session.add(DocumentComment(
        document_id = doc.id,
        author_id   = current_user.id,
        text        = f'Требование {"отправлено на согласование" if action == "submit" else "сохранено как черновик"} пользователем {current_user.full_name}.',
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


@documents.route('/trebovanie/<int:doc_id>/edit', methods=['GET'])
@login_required
def edit_trebovanie(doc_id):
    doc = Document.query.get_or_404(doc_id)
    if doc.author_id != current_user.id:
        abort(403)
    if doc.doc_type != 'trebovanie' or doc.status != 'returned':
        flash('Этот документ нельзя редактировать.', 'warning')
        return redirect(url_for('documents.view', doc_id=doc_id))
    items = doc.items.all()
    return render_template('documents/trebovanie_edit.html', doc=doc, items=items)


@documents.route('/trebovanie/<int:doc_id>/update', methods=['POST'])
@login_required
def update_trebovanie(doc_id):
    doc = Document.query.get_or_404(doc_id)
    if doc.author_id != current_user.id:
        abort(403)
    if doc.doc_type != 'trebovanie' or doc.status != 'returned':
        flash('Этот документ нельзя редактировать.', 'warning')
        return redirect(url_for('documents.view', doc_id=doc_id))

    doc.title   = request.form.get('summary', doc.title)[:100]
    doc.purpose = request.form.get('summary')
    doc.justification = request.form.get('linked_to')

    needed_by = request.form.get('needed_by')
    if needed_by:
        try:
            doc.needed_by = datetime.strptime(needed_by, '%Y-%m-%d').date()
        except ValueError:
            pass

    for it in doc.items.all():
        db.session.delete(it)
    names = request.form.getlist('item_name[]')
    units = request.form.getlist('item_unit[]')
    qtys  = request.form.getlist('item_qty[]')
    notes = request.form.getlist('item_note[]')
    costs = request.form.getlist('item_cost[]')
    for i, name in enumerate(names):
        if name.strip():
            db.session.add(DocumentItem(
                document_id=doc.id,
                name=name.strip(),
                unit=units[i] if i < len(units) else 'шт',
                quantity=float(qtys[i]) if i < len(qtys) and qtys[i] else None,
                note=notes[i] if i < len(notes) else '',
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
