"""Background jobs: sheet syncs + ТО-due checks on a schedule.

Runs inside the web process (APScheduler). Two protections against duplicate
work with multiple gunicorn workers: a Postgres advisory lock per job run
(the second worker simply skips), and all jobs are no-ops when the relevant
integration is not configured.
"""
import logging

log = logging.getLogger(__name__)

LOCK_SYNC = 420001   # arbitrary app-wide advisory lock keys


def _run_locked(app, lock_key, fn):
    """Execute fn under a Postgres advisory lock; skip if another worker holds it.
    On SQLite (dev) locks are skipped and fn just runs."""
    from sqlalchemy import text
    from app import db

    with app.app_context():
        if db.engine.dialect.name != 'postgresql':
            fn()
            return
        conn = db.engine.connect()
        try:
            got = conn.execute(text('SELECT pg_try_advisory_lock(:k)'),
                               {'k': lock_key}).scalar()
            if not got:
                return
            try:
                fn()
            finally:
                conn.execute(text('SELECT pg_advisory_unlock(:k)'), {'k': lock_key})
        finally:
            conn.close()


def _sync_job(app):
    def work():
        from app import db
        from app.models import AppSetting
        from app.services.equipment_sync import sync_equipment
        from app.services.maintenance_sync import sync_maintenance, check_maintenance_due
        try:
            if AppSetting.get('equipment_spreadsheet_id'):
                sync_equipment()
            if AppSetting.get('maintenance_spreadsheet_id'):
                sync_maintenance()
                check_maintenance_due()
            if AppSetting.get('payments_spreadsheet_id'):
                from app.services.payments_sync import sync_payments
                sync_payments()
            db.session.commit()
            log.info('scheduled sync completed')
        except Exception:
            db.session.rollback()
            log.exception('scheduled sync failed')
    _run_locked(app, LOCK_SYNC, work)


def start_scheduler(app):
    from apscheduler.schedulers.background import BackgroundScheduler

    scheduler = BackgroundScheduler(timezone='UTC', daemon=True)
    # каждые 15 минут: статусы техники + реестр ТО + проверка «пора ли ТО»
    scheduler.add_job(_sync_job, 'interval', minutes=15, args=[app],
                      id='sheet_sync', max_instances=1, coalesce=True)
    scheduler.start()
    app.extensions['scheduler'] = scheduler
    log.info('background scheduler started')
    return scheduler
