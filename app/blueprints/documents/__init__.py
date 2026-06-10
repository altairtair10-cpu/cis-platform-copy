from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from app import db
from app.models import Document, DocumentItem, DocumentComment, DOC_TYPES, DOC_STATUSES
from app.decorators import requires_permission
from datetime import datetime

documents = Blueprint('documents', __name__, url_prefix='/documents',
                      template_folder='../../app/templates/documents')

@documents.route('/')
@login_required
def index():
    if current_user.can_access('documents_own'):
        docs = Document.query.filter_by(author_id=current_user.id)\
                             .order_by(Document.created_at.desc()).all()
    else:
        docs = Document.query.order_by(Document.created_at.desc()).all()
    return render_template('documents/index.html', docs=docs,
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
        for i, name in enumerate(names):
            if name.strip():
                item = DocumentItem(
                    document_id = doc.id,
                    name        = name.strip(),
                    unit        = units[i] if i < len(units) else '',
                    quantity    = float(qtys[i]) if i < len(qtys) and qtys[i] else None,
                    note        = notes[i] if i < len(notes) else '',
                )
                db.session.add(item)

        action = request.form.get('action', 'draft')
        if action == 'submit':
            doc.status = 'pending'
            system_comment = DocumentComment(
                document_id = doc.id,
                author_id   = current_user.id,
                text        = f'Document submitted for approval by {current_user.full_name}.',
                is_system   = True,
            )
            db.session.add(system_comment)

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
    items    = doc.items.all()
    approvals = doc.approvals.order_by('step').all()
    comments  = doc.comments.order_by('created_at').all()
    return render_template('documents/view.html', doc=doc, items=items,
                           approvals=approvals, comments=comments,
                           doc_types=DOC_TYPES, statuses=DOC_STATUSES)

@documents.route('/<int:doc_id>/approve', methods=['POST'])
@login_required
def approve(doc_id):
    doc = Document.query.get_or_404(doc_id)
    action  = request.form.get('action')
    comment_text = request.form.get('comment', '')

    if action in ['approve', 'reject']:
        doc.status = 'approved' if action == 'approve' else 'rejected'
        comment = DocumentComment(
            document_id = doc.id,
            author_id   = current_user.id,
            text        = comment_text or f'Document {action}d by {current_user.full_name}.',
            is_system   = False,
        )
        db.session.add(comment)
        db.session.commit()
        flash(f'Document {action}d successfully.', 'success')

    return redirect(url_for('documents.view', doc_id=doc_id))
@documents.route('/defect-act/new', methods=['GET', 'POST'])
@login_required
def new_defect_act():
    from app.models import Equipment
    from datetime import datetime
    equipment = Equipment.query.order_by(Equipment.unit_id).all()
    now = datetime.now().strftime('%d.%m.%Y %H:%M')
    return render_template('documents/defect.html', equipment=equipment, now=now)

@documents.route('/defect-act/submit', methods=['POST'])
@login_required
def submit_defect_act():
    flash('Дефектный акт сохранён.', 'success')
    return redirect(url_for('documents.index'))

@documents.route('/trebovanie/new')
@login_required
def new_trebovanie():
    return render_template('documents/trebovanie.html')