from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from app import db
from app.models import Document, DocumentItem, DocumentComment, DocumentApproval, DOC_TYPES, DOC_STATUSES, User, Notification
from app.decorators import requires_permission
from datetime import datetime

documents = Blueprint('documents', __name__, url_prefix='/documents',
                      template_folder='../../app/templates/documents')


def _to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _panel_docs():
    if current_user.can_access('documents_own'):
        return Document.query.filter_by(author_id=current_user.id)\
                             .order_by(Document.created_at.desc()).all()
    return Document.query.order_by(Document.created_at.desc()).all()


def _build_route(doc, action, signatory_id):
    """Create DocumentApproval records + notify. Shared by all forms."""
    if action != 'submit' or not signatory_id:
        return
    db.session.add(DocumentApproval(document_id=doc.id, approver_id=signatory_id, step=0, status='pending'))
    stage_types = request.form.getlist('stage_type[]')
    all_reviewers = request.form.getlist('stage_reviewer[]')
    reviewer_ids_by_stage = {}
    stage_idx = 0
    for i, rid_str in enumerate(all_reviewers):
        try:
            rid = int(rid_str)
            reviewer_ids_by_stage.setdefault(stage_idx, []).append(rid)
            if stage_idx < len(stage_types) and stage_types[stage_idx] == 'sequential':
                stage_idx += 1
        except (ValueError, TypeError):
            pass
    step = 1
    for stg in sorted(reviewer_ids_by_stage.keys()):
        for rid in reviewer_ids_by_stage[stg]:
            db.session.add(DocumentApproval(document_id=doc.id, approver_id=rid, step=step, status='pending'))
        step += 1


def _notify_approvers(doc):
    all_approvals = DocumentApproval.query.filter_by(document_id=doc.id).all()
    notified = set()
    for appr in all_approvals:
        if appr.approver_id not in notified:
            db.session.add(Notification(
                user_id=appr.approver_id,
                title=f'Документ на согласование: {doc.doc_number}',
                body=doc.title[:100],
                link=f'/documents/{doc.id}',
                is_read=False,
            ))
            notified.add(appr.approver_id)


def _notify_current_approvers(doc, title):
    """Notify whoever is pending at the document's current step."""
    pend = DocumentApproval.query.filter_by(
        document_id=doc.id, step=doc.current_step, status='pending').all()
    for appr in pend:
        db.session.add(Notification(
            user_id=appr.approver_id,
            title=title,
            body=doc.title[:100],
            link=f'/documents/{doc.id}',
            is_read=False,
        ))


@documents.route('/')
@login_required
def index():
    status = request.args.get('status')
    docs = _panel_docs()
    panel_docs = docs
    if status:
        docs = [d for d in docs if d.status == status]
    return render_template('documents/index.html', docs=docs, panel_docs=panel_docs,
                           doc_types=DOC_TYPES, statuses=DOC_STATUSES)


@documents.route('/new')
@login_required
def new():
    return render_template('documents/new.html', doc_types=DOC_TYPES)


@documents.route('/new/purchase-requisition', methods=['GET', 'POST'])
@login_required
def new_purchase_req():
    if request.method == 'POST':
        doc = Document(
            doc_type      = 'purchase_req',
            title         = request.form.get('purpose', 'Purchase Requisition'),
            department    = request.form.get('department'),
            urgency       = request.form.get('urgency', 'standard'),
            purpose       = request.form.get('purpose'),
            justification = request.form.get('justification'),
            author_id     = current_user.id,
            status        = 'draft',
        )
        needed_by = request.form.get('needed_by')
        if needed_by:
            doc.needed_by = datetime.strptime(needed_by, '%Y-%m-%d').date()

        db.session.add(doc)
        db.session.flush()
        doc.generate_number()

        names = request.form.getlist('item_name[]')
        units = request.form.getlist('item_unit[]')
        qtys  = request.form.getlist('item_qty[]')
        notes = request.form.getlist('item_note[]')
        costs = request.form.getlist('item_cost[]')
        for i, name in enumerate(names):
            if name.strip():
                db.session.add(DocumentItem(
                    document_id = doc.id,
                    name        = name.strip(),
                    unit        = units[i] if i < len(units) else '',
                    quantity    = float(qtys[i]) if i < len(qtys) and qtys[i] else None,
                    note        = notes[i] if i < len(notes) else '',
                    price       = _to_float(costs[i]) if i < len(costs) else None,
                ))

        action = request.form.get('action', 'draft')
        if action == 'submit':
            doc.status = 'pending'
            db.session.add(DocumentComment(
                document_id = doc.id,
                author_id   = current_user.id,
                text        = f'Document submitted for approval by {current_user.full_name}.',
                is_system   = True,
            ))

        db.session.commit()
        flash(f'Document {doc.doc_number} {"submitted" if action=="submit" else "saved as draft"}.', 'success')
        return redirect(url_for('documents.view', doc_id=doc.id))

    return render_template('documents/purchase_req.html')


@documents.route('/<int:doc_id>')
@login_required
def view(doc_id):
    doc = Document.query.get_or_404(doc_id)
    if not current_user.can_access('documents') and doc.author_id != current_user.id:
        abort(403)
    items     = doc.items.all()
    comments  = doc.comments.order_by('created_at').all()
    approvals = doc.approvals.order_by(DocumentApproval.step).all()
    panel_docs = _panel_docs()
    return render_template('documents/view.html', doc=doc, items=items,
                           comments=comments, approvals=approvals, panel_docs=panel_docs)


@documents.route('/<int:doc_id>/approve', methods=['POST'])
@login_required
def approve(doc_id):
    doc = Document.query.get_or_404(doc_id)
    action = request.form.get('action')
    comment_text = request.form.get('comment', '').strip()

    if action in ['approve', 'reject', 'return']:
        if not current_user.can_access('documents'):
            abort(403)

        approval = DocumentApproval.query.filter_by(
            document_id=doc_id,
            approver_id=current_user.id,
            step=doc.current_step,
            status='pending'
        ).first()

        # Admin override: IT Admin can act on any document at the current step,
        # even if they are not the specifically assigned approver.
        if not approval and current_user.role == 'it_admin':
            approval = DocumentApproval.query.filter_by(
                document_id=doc_id,
                step=doc.current_step,
                status='pending'
            ).first()

        if not approval:
            flash('Вы не можете выполнить это действие для данного документа.', 'warning')
            return redirect(url_for('documents.view', doc_id=doc_id))

        # ── RETURN FOR REVISION ──────────────────────────────────────────────
        if action == 'return':
            if not comment_text:
                flash('Укажите причину возврата документа.', 'warning')
                return redirect(url_for('documents.view', doc_id=doc_id))
            doc.status = 'returned'   # approval stays 'pending' — supervisor reviews again after resubmit
            db.session.add(DocumentComment(
                document_id=doc.id,
                author_id=current_user.id,
                text=f'Документ возвращён на доработку: {comment_text}',
                is_system=False,
            ))
            db.session.add(Notification(
                user_id=doc.author_id,
                title=f'Документ {doc.doc_number}: возвращён на доработку',
                body=comment_text[:100],
                link=f'/documents/{doc.id}',
                is_read=False,
            ))
            db.session.commit()
            flash('Документ возвращён автору на доработку.', 'success')
            return redirect(url_for('documents.view', doc_id=doc_id))

        # ── APPROVE / REJECT ─────────────────────────────────────────────────
        approval.status = 'approved' if action == 'approve' else 'rejected'
        approval.decided_at = datetime.utcnow()
        if comment_text:
            approval.comment = comment_text

        if action == 'reject':
            doc.status = 'rejected'
            doc.current_step = -1
        else:
            pending_at_step = DocumentApproval.query.filter_by(
                document_id=doc_id,
                step=doc.current_step,
                status='pending'
            ).count()

            if pending_at_step == 1:
                next_step_approvals = DocumentApproval.query.filter_by(
                    document_id=doc_id,
                    step=doc.current_step + 1
                ).count()

                if next_step_approvals > 0:
                    doc.current_step += 1
                else:
                    doc.status = 'approved'

        text = comment_text or f'Документ {"согласован" if action == "approve" else "отклонён"} пользователем {current_user.full_name}.'
        db.session.add(DocumentComment(
            document_id=doc.id,
            author_id=current_user.id,
            text=text,
            is_system=False,
        ))

        db.session.add(Notification(
            user_id=doc.author_id,
            title=f'Документ {doc.doc_number}: {"согласован" if action == "approve" else "отклонён"}',
            body=doc.title[:100],
            link=f'/documents/{doc.id}',
            is_read=False,
        ))

        db.session.commit()
        flash(f'Документ {"согласован" if action == "approve" else "отклонён"}.', 'success')

    elif action == 'comment' and comment_text:
        if doc.author_id != current_user.id and not current_user.can_access('documents'):
            abort(403)
        db.session.add(DocumentComment(
            document_id=doc.id,
            author_id=current_user.id,
            text=comment_text,
            is_system=False,
        ))
        db.session.commit()

    return redirect(url_for('documents.view', doc_id=doc_id))


@documents.route('/<int:doc_id>/resubmit', methods=['POST'])
@login_required
def resubmit(doc_id):
    """Author re-sends a returned document back to the supervisor."""
    doc = Document.query.get_or_404(doc_id)
    if doc.author_id != current_user.id:
        abort(403)
    if doc.status != 'returned':
        flash('Этот документ нельзя повторно отправить.', 'warning')
        return redirect(url_for('documents.view', doc_id=doc_id))
    doc.status = 'pending'
    db.session.add(DocumentComment(
        document_id=doc.id,
        author_id=current_user.id,
        text=f'Документ повторно отправлен на согласование пользователем {current_user.full_name}.',
        is_system=True,
    ))
    _notify_current_approvers(doc, f'Документ повторно на согласовании: {doc.doc_number}')
    db.session.commit()
    flash('Документ повторно отправлен на согласование.', 'success')
    return redirect(url_for('documents.view', doc_id=doc_id))


@documents.route('/defect-act/new', methods=['GET', 'POST'])
@login_required
def new_defect_act():
    from app.models import Equipment
    equipment = Equipment.query.order_by(Equipment.unit_id).all()
    now = datetime.now().strftime('%d.%m.%Y %H:%M')
    return render_template('documents/defect.html', equipment=equipment, now=now)


@documents.route('/defect-act/submit', methods=['POST'])
@login_required
def submit_defect_act():
    action = request.form.get('action', 'draft')

    doc = Document(
        doc_type      = 'defect_act',
        title         = request.form.get('description', 'Дефектный акт')[:100],
        department    = request.form.get('department', current_user.department),
        urgency       = request.form.get('urgency', 'critical'),
        purpose       = request.form.get('description'),
        justification = request.form.get('cause'),
        author_id     = current_user.id,
        status        = 'pending' if action == 'submit' else 'draft',
    )

    db.session.add(doc)
    db.session.flush()
    doc.generate_number()

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

    db.session.add(DocumentComment(
        document_id = doc.id,
        author_id   = current_user.id,
        text        = f'Дефектный акт {"отправлен на согласование" if action == "submit" else "сохранён как черновик"} пользователем {current_user.full_name}.',
        is_system   = True,
    ))

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


@documents.route('/trebovanie/new', methods=['GET', 'POST'])
@login_required
def new_trebovanie():
    now = datetime.now().strftime('%d.%m.%Y %H:%M')
    linked_defect = request.args.get('from_defect', None)
    executors = User.query.filter_by(is_active=True).order_by(User.first_name, User.last_name).all()
    approvers = User.query.filter(User.is_active==True, User.role.in_(['dept_head', 'director', 'it_admin'])).order_by(User.first_name, User.last_name).all()
    return render_template('documents/trebovanie.html', now=now, linked_defect=linked_defect, executors=executors, approvers=approvers)


@documents.route('/trebovanie/submit', methods=['POST'])
@login_required
def submit_trebovanie():
    executor_id = request.form.get('executor_id', type=int) or current_user.id
    action = request.form.get('action', 'draft')

    doc = Document(
        doc_type      = 'purchase_req',
        title         = request.form.get('summary', 'Требование на приобретение')[:100],
        department    = request.form.get('department', current_user.department),
        urgency       = request.form.get('urgency', 'standard'),
        purpose       = request.form.get('summary'),
        justification = request.form.get('note'),
        author_id     = current_user.id,
        executor_id   = executor_id,
        status        = 'pending' if action == 'submit' else 'draft',
    )

    db.session.add(doc)
    db.session.flush()
    doc.generate_number()

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
    now = datetime.now().strftime('%d.%m.%Y %H:%M')
    executors = User.query.filter_by(is_active=True).order_by(User.first_name, User.last_name).all()
    approvers = User.query.filter(User.is_active==True, User.role.in_(['dept_head', 'director', 'it_admin'])).order_by(User.first_name, User.last_name).all()
    return render_template('documents/trebovanie_new.html', now=now, executors=executors, approvers=approvers)


@documents.route('/trebovanie-new/submit', methods=['POST'])
@login_required
def submit_trebovanie_new():
    action = request.form.get('action', 'draft')
    executor_id = request.form.get('executor_id', type=int) or current_user.id
    signatory_id = request.form.get('signatory_id', type=int)

    doc = Document(
        doc_type      = 'trebovanie',
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

    db.session.commit()

    if action == 'submit':
        _notify_approvers(doc)

    db.session.commit()
    flash(f'Документ {doc.doc_number} {"отправлен на согласование" if action == "submit" else "сохранён как черновик"}.', 'success')
    return redirect(url_for('documents.view', doc_id=doc.id))


@documents.route('/po-services/new', methods=['GET'])
@login_required
def new_po_services():
    executors = User.query.filter_by(is_active=True).order_by(User.first_name, User.last_name).all()
    return render_template('documents/po_services.html', executors=executors)


@documents.route('/po-services/submit', methods=['POST'])
@login_required
def submit_po_services():
    action = request.form.get('action', 'draft')
    signatory_id = request.form.get('signatory_id', type=int)

    # Pack the extra service-PO fields into justification as readable text
    extras = {
        'Заказано': request.form.get('ordered_by'),
        'Плательщик НДС': request.form.get('vat_payer'),
        'Валюта': request.form.get('currency'),
        'Дата оплаты': request.form.get('payment_date'),
        'Основание': request.form.get('basis'),
        'Контрагент': request.form.get('counterparty'),
        'Условия оплаты': request.form.get('payment_terms'),
        'Условия оказания услуг': request.form.get('service_terms'),
        'Срок оказания услуг': request.form.get('service_date'),
        'Статья бюджета': request.form.get('budget_line'),
    }
    extras_text = '\n'.join(f'{k}: {v}' for k, v in extras.items() if v)

    doc = Document(
        doc_type      = 'po_services',
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

    db.session.commit()

    if action == 'submit':
        _notify_approvers(doc)

    db.session.commit()
    flash(f'Документ {doc.doc_number} {"отправлен на согласование" if action == "submit" else "сохранён как черновик"}.', 'success')
    return redirect(url_for('documents.view', doc_id=doc.id))


@documents.route('/<int:doc_id>/print')
@login_required
def print_doc(doc_id):
    doc = Document.query.get_or_404(doc_id)
    if not current_user.can_access('documents') and doc.author_id != current_user.id:
        abort(403)
    items = doc.items.all()
    return render_template('documents/print.html', doc=doc, items=items)
def _unpack_extras(justification):
    """Parse the packed 'Label: Value' lines back into form-field names."""
    label_to_field = {
        'Заказано': 'ordered_by',
        'Плательщик НДС': 'vat_payer',
        'Валюта': 'currency',
        'Дата оплаты': 'payment_date',
        'Основание': 'basis',
        'Контрагент': 'counterparty',
        'Условия оплаты': 'payment_terms',
        'Условия оказания услуг': 'service_terms',
        'Срок оказания услуг': 'service_date',
        'Статья бюджета': 'budget_line',
    }
    out = {}
    for line in (justification or '').split('\n'):
        if ': ' in line:
            label, val = line.split(': ', 1)
            field = label_to_field.get(label.strip())
            if field:
                out[field] = val.strip()
    return out


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
        'Контрагент': request.form.get('counterparty'),
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