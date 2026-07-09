"""Central audit trail helper.

Usage:  log_action('document_approved', 'document', doc.id, details='ТМЦ-2026-001')
The row is added to the current db.session; the calling route's commit persists it.
"""
from flask import request, has_request_context
from flask_login import current_user


def log_action(action, entity_type=None, entity_id=None, details=None):
    from app import db
    from app.models import AuditLog

    ip = None
    if has_request_context():
        ip = (request.headers.get('X-Forwarded-For', request.remote_addr) or '')[:64]

    db.session.add(AuditLog(
        user_id=current_user.id if current_user and current_user.is_authenticated else None,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details,
        ip=ip,
    ))
