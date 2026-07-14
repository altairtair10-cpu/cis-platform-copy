"""Согласование, подпись, возврат, повторная отправка, исполнение."""
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
                      _notify_current_approvers, PROCUREMENT_DOC_TYPES,
                      INTERNAL_DOC_TYPES)


@documents.route('/<int:doc_id>/approve', methods=['POST'])
@login_required
def approve(doc_id):
    # Lock the document row for the duration of this decision so two approvers
    # acting on the same parallel stage at the same instant can't both see
    # "I'm the last pending one" and double-advance current_step. Row locking
    # is a Postgres-only concern here (production); SQLite (used in tests)
    # doesn't support FOR UPDATE, so skip it there rather than fail loudly.
    _lockable = db.session.get_bind().dialect.name == 'postgresql'
    doc_query = Document.query.filter_by(id=doc_id)
    doc = (doc_query.with_for_update().first() if _lockable else doc_query.first())
    if doc is None:
        abort(404)
    action = request.form.get('action')
    comment_text = request.form.get('comment', '').strip()

    if action in ['approve', 'reject', 'return']:
        # No blanket role check here on purpose: being the assigned approver for
        # this document's current step (checked just below) is the real
        # authorization, regardless of the approver's role. A finance/HR/mechanic
        # user who was specifically routed to review this document must be able
        # to act on it even though their role has no broad 'documents' permission.
        if doc.status != 'pending':
            flash('Этот документ уже обработан и больше не ожидает согласования.', 'warning')
            return redirect(url_for('documents.view', doc_id=doc_id))

        approval_query = DocumentApproval.query.filter_by(
            document_id=doc_id,
            approver_id=current_user.id,
            step=doc.current_step,
            status='pending'
        )
        approval = (approval_query.with_for_update().first() if _lockable else approval_query.first())

        if not approval and current_user.role == 'it_admin':
            fallback_query = DocumentApproval.query.filter_by(
                document_id=doc_id,
                step=doc.current_step,
                status='pending'
            )
            approval = (fallback_query.with_for_update().first() if _lockable else fallback_query.first())

        if not approval:
            flash('Вы не можете выполнить это действие для данного документа.', 'warning')
            return redirect(url_for('documents.view', doc_id=doc_id))

        if action == 'return' and not comment_text:
            flash('Укажите причину возврата документа.', 'warning')
            return redirect(url_for('documents.view', doc_id=doc_id))
        if action == 'reject' and not comment_text:
            flash('Укажите причину отклонения документа.', 'warning')
            return redirect(url_for('documents.view', doc_id=doc_id))

        if action == 'return':
            doc.status = 'returned'
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
            log_action('document_returned', 'document', doc.id, details=doc.doc_number)
            db.session.commit()
            flash('Документ возвращён автору на доработку.', 'success')
            return redirect(url_for('documents.view', doc_id=doc_id))

        approval.status = 'approved' if action == 'approve' else 'rejected'
        approval.decided_at = datetime.utcnow()
        if comment_text:
            approval.comment = comment_text

        if action == 'reject':
            doc.status = 'rejected'
            doc.current_step = -1
            # Close out any other still-pending approvals (other reviewers in this
            # stage, or later stages/signatory) so the trail doesn't show phantom
            # "awaiting approval" items on a document that's already dead.
            DocumentApproval.query.filter_by(document_id=doc_id, status='pending')\
                .update({'status': 'skipped'}, synchronize_session=False)
        else:
            db.session.flush()   # decision above must be visible to the count
            pending_at_step = DocumentApproval.query.filter_by(
                document_id=doc_id,
                step=doc.current_step,
                status='pending'
            ).count()

            if pending_at_step == 0:
                next_step_approvals = DocumentApproval.query.filter_by(
                    document_id=doc_id,
                    step=doc.current_step + 1
                ).count()

                if next_step_approvals > 0:
                    doc.current_step += 1
                    _notify_current_approvers(doc, f'Документ на согласование: {doc.doc_number}')
                else:
                    doc.status = 'approved'
                    if doc.doc_type in ('po_services', 'po_trebovanie'):
                        # подписанный ПО (услуги или товары) уходит на оплату казначею
                        doc.status = 'awaiting_payment'
                        for fin in User.query.filter_by(role='accountant', is_active=True).all():
                            db.session.add(Notification(
                                user_id=fin.id,
                                title=f'ПО на оплату: {doc.doc_number}',
                                body=(doc.title or '')[:100],
                                link=f'/documents/{doc.id}', is_read=False))
                    if doc.doc_type == 'purchase_req':
                        for proc in User.query.filter_by(role='procurement', is_active=True).all():
                            db.session.add(Notification(
                                user_id=proc.id,
                                title=f'Требование подписано: {doc.doc_number}',
                                body=(doc.title or '')[:100],
                                link=f'/documents/{doc.id}', is_read=False))
                    if doc.doc_type in INTERNAL_DOC_TYPES:
                        # подписанный внутренний документ регистрируется и
                        # уходит получателям на исполнение
                        from app.models import DocumentRecipient
                        doc.registered_at = datetime.utcnow()
                        recips = DocumentRecipient.query.filter_by(
                            document_id=doc.id).all()
                        if recips:
                            doc.status = 'in_execution'
                            for r in recips:
                                db.session.add(Notification(
                                    user_id=r.user_id,
                                    title=f'Документ на исполнение: {doc.doc_number}',
                                    body=(doc.title or '')[:100],
                                    link=f'/documents/{doc.id}', is_read=False))
                        else:
                            doc.status = 'executed'
                        db.session.add(DocumentComment(
                            document_id=doc.id, author_id=current_user.id,
                            text=(f'Документ подписан и зарегистрирован '
                                  f'({doc.doc_number}). '
                                  + ('Отправлен получателям на исполнение.'
                                     if recips else 'Получатели не указаны — '
                                     'документ считается исполненным.')),
                            is_system=True))

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

        log_action(f'document_{"approved" if action == "approve" else "rejected"}',
                   'document', doc.id, details=doc.doc_number)
        db.session.commit()
        flash(f'Документ {"согласован" if action == "approve" else "отклонён"}.', 'success')

    elif action == 'comment' and comment_text:
        if (doc.author_id != current_user.id
                and not current_user.can_access('documents')
                and not _is_assigned_approver(doc, current_user)):
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
    log_action('document_resubmitted', 'document', doc.id, details=doc.doc_number)
    db.session.commit()
    flash('Документ повторно отправлен на согласование.', 'success')
    return redirect(url_for('documents.view', doc_id=doc_id))


@documents.route('/<int:doc_id>/mark-executed', methods=['POST'])
@login_required
def mark_executed(doc_id):
    doc = Document.query.get_or_404(doc_id)
    if doc.doc_type != 'purchase_req' or doc.status not in ('approved', 'in_execution'):
        flash('Документ нельзя отметить исполненным.', 'warning')
        return redirect(url_for('documents.view', doc_id=doc_id))
    if not (current_user.role in ('procurement', 'it_admin', 'director')
            or current_user.can_access('documents_procurement')):
        abort(403)
    doc.status = 'executed'
    db.session.add(DocumentComment(
        document_id=doc.id, author_id=current_user.id,
        text=f'Требование исполнено ({current_user.full_name}).', is_system=True))
    db.session.add(Notification(
        user_id=doc.author_id, title=f'Требование {doc.doc_number} исполнено',
        body=(doc.title or '')[:100], link=f'/documents/{doc.id}', is_read=False))
    log_action('document_executed', 'document', doc.id, details=doc.doc_number)
    db.session.commit()
    flash('Требование отмечено исполненным.', 'success')
    return redirect(url_for('documents.view', doc_id=doc_id))


@documents.route('/<int:doc_id>/mark-paid', methods=['POST'])
@login_required
def mark_paid(doc_id):
    """Ручная отметка оплаты (казначей) — резерв на случай задержки таблицы."""
    doc = Document.query.get_or_404(doc_id)
    if doc.doc_type not in ('po_services', 'po_trebovanie') or doc.status != 'awaiting_payment':
        flash('Документ не ожидает оплаты.', 'warning')
        return redirect(url_for('documents.view', doc_id=doc_id))
    if current_user.role not in ('accountant', 'director', 'it_admin'):
        abort(403)
    from datetime import datetime as _dt
    doc.paid_at = _dt.utcnow()
    doc.status = 'closing_docs'
    db.session.add(DocumentComment(
        document_id=doc.id, author_id=current_user.id,
        text=f'Оплата произведена (отмечено вручную: {current_user.full_name}). '
             f'Ожидаются закрывающие документы от автора.', is_system=True))
    db.session.add(Notification(
        user_id=doc.author_id, title=f'ПО {doc.doc_number} оплачен',
        body='Предоставьте закрывающие документы.',
        link=f'/documents/{doc.id}', is_read=False))
    log_action('po_marked_paid', 'document', doc.id, details=doc.doc_number)
    db.session.commit()
    flash('Оплата отмечена. Автору отправлено уведомление о закрывающих документах.', 'success')
    return redirect(url_for('documents.view', doc_id=doc_id))


@documents.route('/<int:doc_id>/closing-docs-received', methods=['POST'])
@login_required
def closing_docs_received(doc_id):
    doc = Document.query.get_or_404(doc_id)
    if doc.doc_type not in ('po_services', 'po_trebovanie') or doc.status != 'closing_docs':
        flash('Документ не ожидает закрывающих документов.', 'warning')
        return redirect(url_for('documents.view', doc_id=doc_id))
    if current_user.role not in ('accountant', 'director', 'it_admin'):
        abort(403)
    doc.status = 'closed'
    db.session.add(DocumentComment(
        document_id=doc.id, author_id=current_user.id,
        text=f'Закрывающие документы получены ({current_user.full_name}). ПО закрыт.',
        is_system=True))
    db.session.add(Notification(
        user_id=doc.author_id, title=f'ПО {doc.doc_number} закрыт',
        body='Закрывающие документы приняты бухгалтерией.',
        link=f'/documents/{doc.id}', is_read=False))
    log_action('po_closed', 'document', doc.id, details=doc.doc_number)
    db.session.commit()
    flash('ПО закрыт.', 'success')
    return redirect(url_for('documents.view', doc_id=doc_id))
