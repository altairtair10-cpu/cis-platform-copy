"""Автоматическая отметка оплат ПО из таблицы финансистов.

Финансисты ежедневно пополняют Google-таблицу строками с номерами оплаченных
ПО (РОУ-2026-014 и т.п.). Синхронизация находит эти номера среди ПО в статусе
«На оплате», проставляет оплату и переводит документ в «Закрывающие документы»
с уведомлением автора.
"""
import re
from datetime import datetime


def fetch_payment_cells():
    from app.models import AppSetting
    from app.services.gsheets import get_client

    spreadsheet_id = AppSetting.get('payments_spreadsheet_id')
    if not spreadsheet_id:
        raise RuntimeError('Payments spreadsheet is not configured (Admin → Integrations)')
    ss = get_client().open_by_key(spreadsheet_id)
    sheet_name = AppSetting.get('payments_sheet_name')
    ws = ss.worksheet(sheet_name) if sheet_name else ss.get_worksheet(0)
    return ws.get_all_values()


def _norm(s):
    return re.sub(r'\s+', '', (s or '')).upper()


def sync_payments(rows=None):
    """Returns list of doc_numbers marked as paid this run."""
    from app import db
    from app.models import Document, DocumentComment, Notification, AppSetting

    if rows is None:
        rows = fetch_payment_cells()
    blob = _norm(' '.join(' '.join(r) for r in rows))

    pending = Document.query.filter(
        Document.doc_type.in_(('po_services', 'po_trebovanie')),
        Document.status == 'awaiting_payment').all()
    paid_numbers = []
    for doc in pending:
        if not doc.doc_number:
            continue
        if _norm(doc.doc_number) in blob:
            doc.paid_at = datetime.utcnow()
            doc.status = 'closing_docs'
            paid_numbers.append(doc.doc_number)
            db.session.add(DocumentComment(
                document_id=doc.id, author_id=doc.author_id,
                text='Оплата подтверждена по таблице финансового отдела. '
                     'Ожидаются закрывающие документы от автора.', is_system=True))
            db.session.add(Notification(
                user_id=doc.author_id, title=f'ПО {doc.doc_number} оплачен',
                body='Предоставьте закрывающие документы.',
                link=f'/documents/{doc.id}', is_read=False))
    AppSetting.set('payments_last_sync', datetime.utcnow().isoformat())
    db.session.commit()
    return paid_numbers
