"""Реестр, просмотр, печать, вложения, экспорт, шаблоны маршрутов."""
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


@documents.route('/')
@login_required
def index():
    status = request.args.get('status')
    year = request.args.get('year', type=int)
    doc_type = request.args.get('doc_type')
    page = request.args.get('page', 1, type=int)

    panel_counts = _panel_counts(doc_type)

    query = _visible_docs_query(current_user)
    if status:
        query = query.filter_by(status=status)
    if doc_type:
        query = query.filter_by(doc_type=doc_type)
    if year:
        from sqlalchemy import extract
        query = query.filter(extract('year', Document.created_at) == year)
    query = query.order_by(Document.created_at.desc())

    pagination = query.paginate(page=page, per_page=25, error_out=False)
    docs = pagination.items

    from sqlalchemy import extract, distinct
    years = sorted({y for (y,) in db.session.query(
        distinct(extract('year', Document.created_at))).all() if y}, reverse=True)
    return render_template('documents/index.html', docs=docs, panel_counts=panel_counts,
                           years=years, sel_year=year, sel_type=doc_type,
                           pagination=pagination,
                           doc_types=DOC_TYPES, statuses=DOC_STATUSES)


@documents.route('/new')
@login_required
def new():
    return render_template('documents/new.html', doc_types=DOC_TYPES)


@documents.route('/<int:doc_id>')
@login_required
def view(doc_id):
    doc = Document.query.get_or_404(doc_id)
    if not _can_view_doc(current_user, doc):
        abort(403)
    items     = doc.items.all()
    comments  = doc.comments.order_by('created_at').all()
    approvals = doc.approvals.order_by(DocumentApproval.step).all()
    panel_counts = _panel_counts()
    return render_template('documents/view.html', doc=doc, items=items,
                           comments=comments, approvals=approvals, panel_counts=panel_counts)


@documents.route('/<int:doc_id>/attachments/upload', methods=['POST'])
@login_required
def upload_attachment(doc_id):
    doc = Document.query.get_or_404(doc_id)
    if not current_user.can_access('documents') and doc.author_id != current_user.id:
        abort(403)

    file = request.files.get('file')
    if not file or not file.filename:
        flash('Please choose a file.', 'warning')
        return redirect(url_for('documents.view', doc_id=doc.id))

    if not allowed_file(file.filename):
        flash('That file type is not allowed.', 'danger')
        return redirect(url_for('documents.view', doc_id=doc.id))

    stored_filename, backend, size_bytes = save_upload(file)
    if size_bytes > MAX_FILE_SIZE_MB * 1024 * 1024:
        flash(f'File is larger than {MAX_FILE_SIZE_MB} MB.', 'danger')
        return redirect(url_for('documents.view', doc_id=doc.id))

    from werkzeug.utils import secure_filename
    attachment = DocumentAttachment(
        document_id=doc.id,
        original_filename=secure_filename(file.filename),
        stored_filename=stored_filename,
        storage_backend=backend,
        content_type=file.content_type,
        size_bytes=size_bytes,
        uploaded_by=current_user.id,
    )
    db.session.add(attachment)
    db.session.commit()
    log_action('attachment_uploaded', 'document', doc.id, details=attachment.original_filename)
    flash('File attached.', 'success')
    return redirect(url_for('documents.view', doc_id=doc.id))


@documents.route('/<int:doc_id>/attachments/<int:attachment_id>/download')
@login_required
def download_attachment(doc_id, attachment_id):
    doc = Document.query.get_or_404(doc_id)
    if not _can_view_doc(current_user, doc):
        abort(403)
    attachment = DocumentAttachment.query.filter_by(id=attachment_id, document_id=doc.id).first_or_404()
    return send_attachment(attachment)


@documents.route('/<int:doc_id>/attachments/<int:attachment_id>/delete', methods=['POST'])
@login_required
def delete_attachment(doc_id, attachment_id):
    doc = Document.query.get_or_404(doc_id)
    if not current_user.can_access('documents') and doc.author_id != current_user.id:
        abort(403)
    attachment = DocumentAttachment.query.filter_by(id=attachment_id, document_id=doc.id).first_or_404()
    db.session.delete(attachment)
    db.session.commit()
    flash('Attachment removed.', 'success')
    return redirect(url_for('documents.view', doc_id=doc.id))


@documents.route('/<int:doc_id>/print')
@login_required
def print_doc(doc_id):
    doc = Document.query.get_or_404(doc_id)
    if (not current_user.can_access('documents')
            and doc.author_id != current_user.id
            and not _is_assigned_approver(doc, current_user)):
        abort(403)
    items = doc.items.all()
    extras = _unpack_extras(doc.justification)
    approvals = doc.approvals.order_by(DocumentApproval.step).all()
    total = float(doc.total_cost or 0)
    vat_yes = (extras.get('vat_payer') or '').strip().lower() in ('да', 'yes', 'true', '1')
    vat = round(total * 0.16, 2) if vat_yes else 0.0
    vat_display = 'Да' if vat_yes else 'Нет'
    sig_step = max((a.step for a in approvals), default=0)
    if doc.doc_type == 'po_services':
        template = 'documents/print_po_services.html'
    elif doc.doc_type == 'po_trebovanie':
        template = 'documents/print_po_goods.html'
    else:
        template = 'documents/print.html'
    return render_template(template, doc=doc, items=items, extras=extras,
                           approvals=approvals, total=total, vat=vat,
                           vat_display=vat_display, sig_step=sig_step)


@documents.route('/route-templates/save', methods=['POST'])
@login_required
def save_route_template():
    import json as _json
    from app.models import RouteTemplate
    name = (request.form.get('template_name') or '').strip()
    raw = request.form.get('template_json') or ''
    if not name or not raw:
        return jsonify({'error': 'name and route required'}), 400
    try:
        data = _json.loads(raw)
        assert isinstance(data.get('stages'), list)
    except Exception:
        return jsonify({'error': 'bad route data'}), 400
    tpl = RouteTemplate.query.filter_by(name=name).first()
    if tpl is None:
        tpl = RouteTemplate(name=name, created_by=current_user.id)
        db.session.add(tpl)
    tpl.data = _json.dumps(data, ensure_ascii=False)
    log_action('route_template_saved', details=name)
    db.session.commit()
    return jsonify({'ok': True, 'id': tpl.id, 'name': tpl.name})


@documents.route('/export.xlsx')
@login_required
def export_xlsx():
    """Flat Excel export: one row per item, with the document number.
    Filters: ?doc_type=&year=2026&month=7 (all optional; no type = all types)."""
    if not (current_user.can_access('documents') or current_user.can_access('documents_read')
            or current_user.can_access('documents_procurement')):
        abort(403)
    import io
    from openpyxl import Workbook
    from sqlalchemy import extract

    year = request.args.get('year', type=int)
    month = request.args.get('month', type=int)
    doc_type = request.args.get('doc_type') or None
    if doc_type and doc_type not in DOC_TYPES:
        abort(400)

    query = Document.query
    if doc_type:
        query = query.filter_by(doc_type=doc_type)
    if year:
        query = query.filter(extract('year', Document.created_at) == year)
    if month:
        query = query.filter(extract('month', Document.created_at) == month)
    docs = query.order_by(Document.created_at).all()

    wb = Workbook()
    ws = wb.active
    ws.title = (DOC_TYPES.get(doc_type, 'Документы')[:31] if doc_type else 'Документы')
    ws.append(['Номер', 'Тип', 'Дата', 'Статус', 'Отдел', 'Автор', 'Код ДА',
               'Наименование', 'Характеристика/прим.', 'Кол-во', 'Ед.',
               'Цена', 'Сумма'])
    from app.models import DOC_STATUSES
    for doc in docs:
        items = doc.items.all() or [None]
        for it in items:
            ws.append([
                doc.doc_number,
                DOC_TYPES.get(doc.doc_type, doc.doc_type),
                doc.created_at.strftime('%d.%m.%Y'),
                DOC_STATUSES.get(doc.status, doc.status),
                doc.department or '',
                doc.author.full_name if doc.author else '',
                (doc.related_defect.event_code if doc.related_defect else '') or '',
                it.name if it else '',
                (it.note or '') if it else '',
                float(it.quantity) if it and it.quantity is not None else None,
                (it.unit or '') if it else '',
                float(it.price) if it and it.price is not None else None,
                (float(it.quantity) * float(it.price))
                    if it and it.quantity is not None and it.price is not None else None,
            ])
    for col, width in zip('ABCDEFGHIJKLM', [16, 22, 11, 14, 12, 20, 12, 40, 24, 8, 6, 12, 14]):
        ws.column_dimensions[col].width = width

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    suffix = f'-{doc_type}' if doc_type else ''
    suffix += f'-{year}' if year else ''
    suffix += f'-{month:02d}' if month else ''
    from flask import send_file
    log_action('documents_exported',
               details=f'type={doc_type or "all"} year={year} month={month} docs={len(docs)}')
    db.session.commit()
    return send_file(buf, as_attachment=True,
                     download_name=f'documents{suffix}.xlsx',
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
