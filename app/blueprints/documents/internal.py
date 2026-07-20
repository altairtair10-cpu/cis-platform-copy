"""Внутренние документы (Documentolog-style): служебные записки, приказы,
акты, входящие/исходящие письма.

Жизненный цикл: Создание → Согласование → Подпись → Регистрация →
На исполнении → Исполнен. Маршрут согласования — общий движок helpers.
После подписи документ автоматически «регистрируется» (registered_at)
и уходит получателям на исполнение (см. approvals.py); когда все получатели
отметили исполнение — документ «Исполнен»."""
from datetime import datetime
from flask import render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from app import db
from app.models import (Document, DocumentComment, DocumentRecipient,
                        DOC_TYPES, User, Notification)
from app.audit import log_action
from . import documents
from .helpers import (_build_route, _save_form_attachments, _notify_approvers,
                      _notify_current_approvers, _sanitize_html,
                      INTERNAL_DOC_TYPES)

# Шаблон текста документа — как в Documentolog (записка служебная)
DEFAULT_BODY_HTML = (
    '<p>Констатирующая часть <i>(причина, основание или обоснование '
    'составления письма, «В связи, в целях… и т.д.»)</i>.</p>'
    '<p>Заключительная часть <i>(выводы, предложения, просьбы, решения '
    '«Прошу Вас… и т.д.»)</i>.</p>'
    '<p>Приложение: наименование на __ л. в __ экз. '
    '<i>(при необходимости)</i></p>'
)


def _internal_form_context():
    import json as _json
    from app.models import RouteTemplate
    users = User.query.filter_by(is_active=True)\
                      .order_by(User.first_name, User.last_name).all()
    route_templates = RouteTemplate.query.order_by(RouteTemplate.name).all()
    templates_json = _json.dumps(
        [{'id': t.id, 'name': t.name, 'data': _json.loads(t.data)}
         for t in route_templates], ensure_ascii=False)
    reply_candidates = Document.query\
        .filter(Document.doc_type.in_(INTERNAL_DOC_TYPES))\
        .order_by(Document.created_at.desc()).limit(100).all()
    return {
        'executors': users,
        'templates_json': templates_json,
        'reply_candidates': reply_candidates,
        'internal_types': {t: DOC_TYPES[t] for t in INTERNAL_DOC_TYPES},
        'now': datetime.now().strftime('%d.%m.%Y %H:%M'),
        'default_body': DEFAULT_BODY_HTML,
    }


@documents.route('/internal/new', methods=['GET'])
@login_required
def new_internal():
    doc_type = request.args.get('doc_type', 'memo')
    if doc_type not in INTERNAL_DOC_TYPES:
        doc_type = 'memo'
    ctx = _internal_form_context()
    return render_template('documents/internal_new.html',
                           doc=None, sel_type=doc_type, recipients=[], **ctx)


def _apply_internal_form(doc):
    """Заполняет поля документа из формы (общая часть create/update)."""
    doc.title = (request.form.get('summary') or 'Внутренний документ')[:256]
    doc.purpose = request.form.get('summary')
    doc.body_html = _sanitize_html(request.form.get('body_html') or '')
    doc.doc_language = request.form.get('doc_language') or 'ru'
    doc.case_index = (request.form.get('case_index') or '')[:64] or None

    needed_by = request.form.get('needed_by')
    doc.needed_by = None
    if needed_by:
        try:
            doc.needed_by = datetime.strptime(needed_by, '%Y-%m-%d').date()
        except ValueError:
            pass

    in_reply_to_id = request.form.get('in_reply_to_id', type=int)
    doc.in_reply_to_id = None
    if in_reply_to_id:
        rel = Document.query.filter(
            Document.id == in_reply_to_id,
            Document.doc_type.in_(INTERNAL_DOC_TYPES)).first()
        doc.in_reply_to_id = rel.id if rel else None


def _apply_recipients(doc):
    """Заменяет получателей документа на выбранных в форме. Возвращает
    количество получателей."""
    for r in doc.recipients.all():
        db.session.delete(r)
    seen = set()
    for rid in request.form.getlist('recipient_ids[]'):
        if not rid.strip().isdigit():
            continue
        rid = int(rid)
        if rid in seen:
            continue
        if not db.session.get(User, rid):
            continue
        seen.add(rid)
        db.session.add(DocumentRecipient(document_id=doc.id, user_id=rid,
                                         status='pending'))
    return len(seen)


@documents.route('/internal/submit', methods=['POST'])
@login_required
def submit_internal():
    action = request.form.get('action', 'draft')
    doc_type = request.form.get('doc_type', 'memo')
    if doc_type not in INTERNAL_DOC_TYPES:
        doc_type = 'memo'
    signatory_id = request.form.get('signatory_id', type=int)

    if action == 'submit' and not signatory_id:
        action = 'draft'
        flash('Документ сохранён как черновик: не выбран Подписывающий. '
              'Укажите подписывающего и отправьте документ ещё раз.', 'warning')

    doc = Document(
        doc_type    = doc_type,
        title       = 'Внутренний документ',
        department  = current_user.department,
        author_id   = current_user.id,
        executor_id = current_user.id,
        status      = 'pending' if action == 'submit' else 'draft',
        current_step = 0,
    )
    _apply_internal_form(doc)

    db.session.add(doc)
    db.session.flush()

    n_recipients = _apply_recipients(doc)
    if action == 'submit' and n_recipients == 0:
        action = 'draft'
        doc.status = 'draft'
        flash('Документ сохранён как черновик: не выбраны Получатели.', 'warning')

    doc.generate_number()
    log_action('document_created', 'document', doc.id, details=doc.doc_number)
    _save_form_attachments(doc)

    db.session.add(DocumentComment(
        document_id=doc.id,
        author_id=current_user.id,
        text=(f'Документ «{DOC_TYPES.get(doc.doc_type, doc.doc_type)}» '
              f'{"отправлен на согласование" if action == "submit" else "сохранён как черновик"} '
              f'пользователем {current_user.full_name}.'),
        is_system=True,
    ))

    _build_route(doc, action, signatory_id)
    db.session.commit()

    if action == 'submit':
        _notify_approvers(doc)
        db.session.commit()

    flash(f'Документ {doc.doc_number} '
          f'{"отправлен на согласование" if action == "submit" else "сохранён как черновик"}.',
          'success')
    return redirect(url_for('documents.view', doc_id=doc.id))


@documents.route('/internal/<int:doc_id>/edit', methods=['GET'])
@login_required
def edit_internal(doc_id):
    doc = Document.query.get_or_404(doc_id)
    if doc.author_id != current_user.id:
        abort(403)
    if doc.doc_type not in INTERNAL_DOC_TYPES or doc.status not in ('draft', 'returned'):
        flash('Этот документ нельзя редактировать.', 'warning')
        return redirect(url_for('documents.view', doc_id=doc_id))
    ctx = _internal_form_context()
    recipients = [r.user_id for r in doc.recipients.all()]
    return render_template('documents/internal_new.html',
                           doc=doc, sel_type=doc.doc_type,
                           recipients=recipients, **ctx)


@documents.route('/internal/<int:doc_id>/update', methods=['POST'])
@login_required
def update_internal(doc_id):
    doc = Document.query.get_or_404(doc_id)
    if doc.author_id != current_user.id:
        abort(403)
    if doc.doc_type not in INTERNAL_DOC_TYPES or doc.status not in ('draft', 'returned'):
        flash('Этот документ нельзя редактировать.', 'warning')
        return redirect(url_for('documents.view', doc_id=doc_id))

    was_draft = (doc.status == 'draft')
    action = request.form.get('action', 'save')
    signatory_id = request.form.get('signatory_id', type=int)

    _apply_internal_form(doc)
    n_recipients = _apply_recipients(doc)
    _save_form_attachments(doc)

    if action == 'submit' and was_draft:
        # у черновика маршрут строится заново из формы
        if not signatory_id:
            flash('Не выбран Подписывающий — документ остаётся черновиком.', 'warning')
            action = 'save'
        elif n_recipients == 0:
            flash('Не выбраны Получатели — документ остаётся черновиком.', 'warning')
            action = 'save'
        else:
            for appr in doc.approvals.all():
                db.session.delete(appr)
            db.session.flush()
            doc.current_step = 0
            _build_route(doc, 'submit', signatory_id)
            doc.status = 'pending'

    if action == 'submit':
        doc.status = 'pending'
        db.session.add(DocumentComment(
            document_id=doc.id, author_id=current_user.id,
            text=(f'Документ отредактирован и отправлен на согласование '
                  f'пользователем {current_user.full_name}.'),
            is_system=True,
        ))
        db.session.commit()
        if was_draft:
            _notify_approvers(doc)
        else:
            _notify_current_approvers(
                doc, f'Документ повторно на согласовании: {doc.doc_number}')
        msg = 'Документ отправлен на согласование.'
    else:
        db.session.add(DocumentComment(
            document_id=doc.id, author_id=current_user.id,
            text=f'Документ обновлён пользователем {current_user.full_name}.',
            is_system=True,
        ))
        msg = 'Изменения сохранены.'

    log_action('document_updated', 'document', doc.id, details=doc.doc_number)
    db.session.commit()
    flash(msg, 'success')
    return redirect(url_for('documents.view', doc_id=doc.id))


@documents.route('/<int:doc_id>/recipient-done', methods=['POST'])
@login_required
def recipient_done(doc_id):
    """Получатель отмечает исполнение. Когда все отметили — документ «Исполнен»."""
    doc = Document.query.get_or_404(doc_id)
    if (doc.doc_type not in INTERNAL_DOC_TYPES + ('purchase_req',)
            or doc.status != 'in_execution'):
        flash('Документ не находится на исполнении.', 'warning')
        return redirect(url_for('documents.view', doc_id=doc_id))

    rec = DocumentRecipient.query.filter_by(
        document_id=doc.id, user_id=current_user.id, status='pending').first()
    if rec is None and current_user.role == 'it_admin':
        rec = DocumentRecipient.query.filter_by(
            document_id=doc.id, status='pending').first()
    if rec is None:
        flash('Вы не являетесь получателем этого документа '
              'или уже отметили исполнение.', 'warning')
        return redirect(url_for('documents.view', doc_id=doc_id))

    rec.status = 'done'
    rec.done_at = datetime.utcnow()
    note = (request.form.get('note') or '').strip()
    if note:
        rec.note = note[:256]

    db.session.add(DocumentComment(
        document_id=doc.id, author_id=current_user.id,
        text=(f'Исполнение отмечено получателем {rec.user.full_name}.'
              + (f' Комментарий: {note}' if note else '')),
        is_system=True,
    ))

    db.session.flush()
    still_pending = DocumentRecipient.query.filter_by(
        document_id=doc.id, status='pending').count()
    if still_pending == 0:
        doc.status = 'executed'
        db.session.add(DocumentComment(
            document_id=doc.id, author_id=current_user.id,
            text='Все получатели отметили исполнение. Документ исполнен.',
            is_system=True,
        ))
        db.session.add(Notification(
            user_id=doc.author_id,
            title=f'Документ {doc.doc_number} исполнен',
            body=(doc.title or '')[:100],
            link=f'/documents/{doc.id}', is_read=False,
        ))

    log_action('document_recipient_done', 'document', doc.id,
               details=doc.doc_number)
    db.session.commit()
    flash('Исполнение отмечено.' + (' Документ исполнен.' if still_pending == 0 else ''),
          'success')
    return redirect(url_for('documents.view', doc_id=doc_id))
