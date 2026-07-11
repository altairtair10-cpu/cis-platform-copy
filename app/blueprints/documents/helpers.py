"""Общая логика документооборота: видимость, маршруты, уведомления."""
from flask import request, flash
from flask_login import current_user
from sqlalchemy import or_
from app import db
from app.models import (Document, DocumentApproval, DocumentAttachment,
                        DocumentComment, Notification)
from app.storage import save_upload, allowed_file, MAX_FILE_SIZE_MB

PROCUREMENT_DOC_TYPES = ('purchase_req', 'po_services')

def _to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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
        'Требование на приобретение материалов': 'material_request',
    }
    out = {}
    for line in (justification or '').split('\n'):
        if ': ' in line:
            label, val = line.split(': ', 1)
            field = label_to_field.get(label.strip())
            if field:
                out[field] = val.strip()
    return out


def _assigned_doc_ids_subquery(user):
    """Document IDs where this user is (or was) an assigned approver at any step —
    regardless of their role's blanket permissions. Being routed to a document
    as a reviewer/signatory is its own authorization to see and act on it."""
    return db.session.query(DocumentApproval.document_id).filter_by(approver_id=user.id)


def _is_assigned_approver(doc, user):
    return DocumentApproval.query.filter_by(document_id=doc.id, approver_id=user.id).first() is not None


PROCUREMENT_DOC_TYPES = ('purchase_req', 'po_services')


def _can_view_doc(user, doc):
    """View access: broad permission, own doc, routed approver, or procurement
    for procurement document types."""
    if user.can_access('documents') or user.can_access('documents_read'):
        return True
    if doc.author_id == user.id or _is_assigned_approver(doc, user):
        return True
    return (doc.doc_type in PROCUREMENT_DOC_TYPES
            and user.can_access('documents_procurement'))


def _visible_docs_query(user):
    """Documents a user may see: everything (broad 'documents' permission),
    or their own + anything they're routed to approve/review + procurement types
    for procurement staff."""
    query = Document.query
    if user.can_access('documents') or user.can_access('documents_read'):
        return query
    conditions = [
        Document.author_id == user.id,
        Document.id.in_(_assigned_doc_ids_subquery(user)),
    ]
    if user.can_access('documents_procurement'):
        conditions.append(Document.doc_type.in_(PROCUREMENT_DOC_TYPES))
    return query.filter(or_(*conditions))


def _panel_counts(doc_type=None):
    """Status counters for the left panel via a single aggregate query —
    stays fast no matter how many documents accumulate over the years."""
    from sqlalchemy import func
    visible = _visible_docs_query(current_user).subquery()
    query = db.session.query(visible.c.status, func.count()).group_by(visible.c.status)
    if doc_type:
        query = query.filter(visible.c.doc_type == doc_type)
    counts = dict(query.all())
    counts['_total'] = sum(counts.values())
    return counts


def _build_route(doc, action, signatory_id):
    """Create DocumentApproval records. Shared by all forms.

    Order: reviewer stages first (steps 0..k-1, in form order), the signatory
    signs LAST (step k) — Создание → Согласование → Подпись.

    New form format: each stage emits stage_no[] (aligned with stage_type[])
    and its reviewers as stage_reviewer_<no>[]. Legacy flat stage_reviewer[]
    is treated as a single parallel stage.
    """
    if action != 'submit' or not signatory_id:
        return
    stage_nos = request.form.getlist('stage_no[]')
    stages = []
    if stage_nos:
        for no in stage_nos:
            ids = [int(r) for r in request.form.getlist(f'stage_reviewer_{no}[]')
                   if r.strip().isdigit()]
            if ids:
                stages.append(ids)
    else:
        ids = [int(r) for r in request.form.getlist('stage_reviewer[]')
               if r.strip().isdigit()]
        if ids:
            stages.append(ids)

    step = 0
    for ids in stages:
        for rid in ids:
            db.session.add(DocumentApproval(document_id=doc.id, approver_id=rid,
                                            step=step, status='pending'))
        step += 1
    # the signatory always signs last
    db.session.add(DocumentApproval(document_id=doc.id, approver_id=signatory_id,
                                    step=step, status='pending'))


def _save_form_attachments(doc):
    """Save files posted in the 'attachments' field of a create/edit form.
    Mirrors the validation in upload_attachment()."""
    from werkzeug.utils import secure_filename
    for f in request.files.getlist('attachments'):
        if not f or not f.filename:
            continue
        if not allowed_file(f.filename):
            flash(f'Файл «{f.filename}» не загружен: недопустимый тип.', 'warning')
            continue
        stored_filename, backend, size_bytes = save_upload(f)
        if size_bytes > MAX_FILE_SIZE_MB * 1024 * 1024:
            flash(f'Файл «{f.filename}» не загружен: больше {MAX_FILE_SIZE_MB} МБ.', 'warning')
            continue
        db.session.add(DocumentAttachment(
            document_id=doc.id,
            original_filename=secure_filename(f.filename),
            stored_filename=stored_filename,
            storage_backend=backend,
            content_type=f.content_type,
            size_bytes=size_bytes,
            uploaded_by=current_user.id,
        ))


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
