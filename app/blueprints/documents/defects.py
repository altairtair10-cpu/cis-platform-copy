"""Дефектные акты и их жизненный цикл."""
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


@documents.route('/defect-act/new', methods=['GET', 'POST'])
@login_required
def new_defect_act():
    from app.models import Equipment
    equipment = Equipment.query.order_by(Equipment.unit_id).all()
    now = datetime.now().strftime('%d.%m.%Y %H:%M')
    executors = User.query.filter_by(is_active=True)\
                          .order_by(User.first_name, User.last_name).all()
    return render_template('documents/defect.html', equipment=equipment, now=now,
                           executors=executors)


@documents.route('/defect-act/submit', methods=['POST'])
@login_required
def submit_defect_act():
    action = request.form.get('action', 'draft')

    # Маршрут как у всех документов: утверждающий выбирается в форме.
    # Если не выбран — fallback на начальника отдела/директора (как раньше).
    signatory_id = request.form.get('signatory_id', type=int)
    if not signatory_id:
        fallback = (User.query.filter_by(role='dept_head', is_active=True).first()
                    or User.query.filter_by(role='director', is_active=True).first()
                    or User.query.filter_by(role='it_admin', is_active=True).first())
        signatory_id = fallback.id if fallback else None
    if action == 'submit' and not signatory_id:
        action = 'draft'
        flash('Документ сохранён как черновик: не выбран утверждающий. Укажите маршрут и отправьте ещё раз.', 'warning')

    equipment_id = request.form.get('equipment_id', type=int)
    doc = Document(
        doc_type      = 'defect_act',
        equipment_id  = equipment_id,
        title         = request.form.get('description', 'Дефектный акт')[:100],
        department    = request.form.get('department', current_user.department),
        urgency       = request.form.get('urgency', 'critical'),
        purpose       = request.form.get('description'),
        justification = request.form.get('cause'),
        author_id     = current_user.id,
        status        = 'pending' if action == 'submit' else 'draft',
        current_step  = 0,
    )

    db.session.add(doc)
    db.session.flush()
    doc.generate_number()
    doc.assign_event_code()
    log_action('document_created', 'document', doc.id, details=doc.doc_number)

    names = request.form.getlist('part_name[]')
    specs = request.form.getlist('part_spec[]')
    qtys  = request.form.getlist('part_qty[]')
    units = request.form.getlist('part_unit[]')
    costs = request.form.getlist('part_cost[]')

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

    _build_route(doc, action, signatory_id)

    db.session.add(DocumentComment(
        document_id = doc.id,
        author_id   = current_user.id,
        text        = f'Дефектный акт {"отправлен на согласование" if action == "submit" else "сохранён как черновик"} пользователем {current_user.full_name}.',
        is_system   = True,
    ))

    db.session.commit()

    if action == 'submit':
        _notify_approvers(doc)
        db.session.commit()

    flash(f'Документ {doc.doc_number}'
          + (f' (учётный код {doc.event_code})' if doc.event_code else '')
          + f' {"отправлен на согласование" if action == "submit" else "сохранён как черновик"}.', 'success')
    return redirect(url_for('documents.view', doc_id=doc.id))


@documents.route('/defect-act/<int:doc_id>/edit', methods=['GET'])
@login_required
def edit_defect_act(doc_id):
    doc = Document.query.get_or_404(doc_id)
    if doc.author_id != current_user.id:
        abort(403)
    if doc.doc_type != 'defect_act' or doc.status != 'returned':
        flash('Этот документ нельзя редактировать.', 'warning')
        return redirect(url_for('documents.view', doc_id=doc_id))
    items = doc.items.all()
    return render_template('documents/defect_edit.html', doc=doc, items=items)


@documents.route('/defect-act/<int:doc_id>/update', methods=['POST'])
@login_required
def update_defect_act(doc_id):
    doc = Document.query.get_or_404(doc_id)
    if doc.author_id != current_user.id:
        abort(403)
    if doc.doc_type != 'defect_act' or doc.status != 'returned':
        flash('Этот документ нельзя редактировать.', 'warning')
        return redirect(url_for('documents.view', doc_id=doc_id))

    doc.title         = request.form.get('description', doc.title)[:100]
    doc.purpose       = request.form.get('description')
    doc.justification = request.form.get('cause')
    doc.urgency       = request.form.get('urgency', doc.urgency)

    for it in doc.items.all():
        db.session.delete(it)
    names = request.form.getlist('part_name[]')
    specs = request.form.getlist('part_spec[]')
    qtys  = request.form.getlist('part_qty[]')
    units = request.form.getlist('part_unit[]')
    costs = request.form.getlist('part_cost[]')
    for i, name in enumerate(names):
        if name.strip():
            db.session.add(DocumentItem(
                document_id=doc.id,
                name=name.strip(),
                unit=units[i] if i < len(units) else 'шт',
                quantity=float(qtys[i]) if i < len(qtys) and qtys[i] else None,
                note=specs[i] if i < len(specs) else '',
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


@documents.route('/<int:doc_id>/close-defect', methods=['POST'])
@login_required
def close_defect(doc_id):
    doc = Document.query.get_or_404(doc_id)
    if doc.doc_type != 'defect_act' or doc.defect_closed:
        flash('Этот документ нельзя закрыть.', 'warning')
        return redirect(url_for('documents.view', doc_id=doc_id))
    if not (doc.author_id == current_user.id
            or current_user.can_access('documents')
            or current_user.can_access('equipment')):
        abort(403)
    doc.defect_closed = True
    doc.defect_closed_at = datetime.utcnow()
    db.session.add(DocumentComment(
        document_id=doc.id, author_id=current_user.id,
        text=f'Дефект {doc.event_code or doc.doc_number} закрыт (ремонт выполнен).',
        is_system=True))
    log_action('defect_closed', 'document', doc.id, details=doc.event_code or doc.doc_number)
    db.session.commit()
    flash(f'Дефект {doc.event_code or doc.doc_number} закрыт.', 'success')
    return redirect(url_for('documents.view', doc_id=doc_id))
