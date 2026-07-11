from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.models import Equipment, MaintenanceLog, Document, AppSetting, db
from app.audit import log_action
from app.services.equipment_sync import sync_equipment, sync_if_stale, last_sync_dt
from app.services.maintenance_sync import (sync_maintenance, check_maintenance_due,
                                            to_status)
from app.decorators import requires_permission
from datetime import datetime

equipment = Blueprint('equipment', __name__, url_prefix='/equipment',
                      template_folder='../../app/templates/equipment')

def _to_float(value):
    """Parse a form field into a float, tolerating blanks/commas. Returns None if unusable."""
    if value is None:
        return None
    value = value.strip().replace(',', '.')
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None

@equipment.route('/')
@login_required
@requires_permission('equipment')
def index():
    sync_if_stale()   # refresh from the Google Sheet if data is older than 10 min
    page = request.args.get('page', 1, type=int)
    pagination = Equipment.query.order_by(Equipment.unit_id)\
                                 .paginate(page=page, per_page=25, error_out=False)
    units = pagination.items

    # KPI counts must reflect ALL equipment, not just the current page.
    counts = {
        'total':       Equipment.query.count(),
        'deployed':    Equipment.query.filter_by(status='deployed').count(),
        'idle':        Equipment.query.filter_by(status='idle').count(),
        'maintenance': Equipment.query.filter_by(status='maintenance').count(),
    }
    return render_template('equipment/index.html', units=units, pagination=pagination,
                           counts=counts, last_sync=last_sync_dt(),
                           sync_configured=bool(AppSetting.get('equipment_spreadsheet_id')))

@equipment.route('/<int:unit_id>')
@login_required
@requires_permission('equipment')
def view(unit_id):
    unit = Equipment.query.get_or_404(unit_id)
    logs = MaintenanceLog.query.filter_by(equipment_id=unit.id)\
                               .order_by(MaintenanceLog.created_at.desc()).all()
    docs = Document.query.filter_by(equipment_id=unit.id)\
                         .order_by(Document.created_at.desc()).all()
    from app.models import ServiceRecord
    from app.services.to_stock import check_to_parts
    to_parts_status = check_to_parts(unit)
    records = ServiceRecord.query.filter_by(equipment_id=unit.id)\
                                 .order_by(ServiceRecord.date.desc()).limit(7).all()
    open_defects = Document.query.filter_by(equipment_id=unit.id, doc_type='defect_act',
                                            defect_closed=False)\
                                 .order_by(Document.created_at.desc()).all()
    return render_template('equipment/view.html', unit=unit, logs=logs, docs=docs,
                           records=records, open_defects=open_defects,
                           to_state=to_status(unit), to_parts_status=to_parts_status)

@equipment.route('/<int:unit_id>/log', methods=['POST'])
@login_required
@requires_permission('equipment')
def add_log(unit_id):
    unit = Equipment.query.get_or_404(unit_id)

    description = request.form.get('description', '').strip()
    if not description:
        flash('Please describe the work performed.', 'warning')
        return redirect(url_for('equipment.view', unit_id=unit.id))

    parts_used = request.form.get('parts_used', '').strip() or None
    cost       = _to_float(request.form.get('cost'))
    new_status = request.form.get('status') or unit.status
    next_service_raw = request.form.get('next_service', '').strip()

    kind = request.form.get('kind')
    log = MaintenanceLog(
        equipment_id = unit.id,
        logged_by    = current_user.id,
        description  = description,
        parts_used   = parts_used,
        cost         = cost,
        kind         = kind if kind in ('ТО', 'Р') else None,
    )
    db.session.add(log)

    unit.status = new_status
    unit.last_service = datetime.utcnow().date()
    if next_service_raw:
        try:
            unit.next_service = datetime.strptime(next_service_raw, '%Y-%m-%d').date()
        except ValueError:
            pass

    db.session.commit()
    flash('Maintenance logged successfully.', 'success')
    return redirect(url_for('equipment.view', unit_id=unit.id))

@equipment.route('/dashboard')
@login_required
@requires_permission('equipment')
def dashboard():
    """Embedded external equipment dashboard (URL managed in the admin panel)."""
    dashboard_url = AppSetting.get('equipment_dashboard_url')
    return render_template('equipment/dashboard.html', dashboard_url=dashboard_url)


@equipment.route('/sync', methods=['POST'])
@login_required
@requires_permission('equipment')
def sync():
    try:
        created, updated = sync_equipment()
        log_action('equipment_synced', details=f'+{created} new, {updated} updated')
        db.session.commit()
        flash(f'Синхронизировано с таблицей: новых {created}, обновлено {updated}.', 'success')
    except Exception as exc:
        flash(f'Не удалось синхронизировать статусы: {exc}', 'danger')
    if AppSetting.get('maintenance_spreadsheet_id'):
        try:
            new_recs, matched, unmatched = sync_maintenance()
            due = check_maintenance_due()
            log_action('maintenance_synced',
                       details=f'+{new_recs} records, {matched} tabs, {len(due)} due')
            db.session.commit()
            msg = f'Реестр ТО: новых записей {new_recs}, вкладок сопоставлено {matched}.'
            if unmatched:
                msg += f' Не сопоставлено: {", ".join(unmatched[:5])}' + ('…' if len(unmatched) > 5 else '')
            flash(msg, 'success' if not unmatched else 'warning')
        except Exception as exc:
            flash(f'Не удалось синхронизировать реестр ТО: {exc}', 'danger')
    return redirect(url_for('equipment.index'))


@equipment.route('/<int:unit_id>/to-parts/add', methods=['POST'])
@login_required
@requires_permission('equipment')
def add_to_part(unit_id):
    from app.models import ToPart
    unit = Equipment.query.get_or_404(unit_id)
    name = (request.form.get('name') or '').strip()
    if not name:
        flash('Укажите название материала.', 'warning')
        return redirect(url_for('equipment.view', unit_id=unit.id))
    db.session.add(ToPart(
        equipment_id=unit.id, name=name[:256],
        qty=_to_float(request.form.get('qty')) or 1,
        unit=(request.form.get('unit') or '').strip()[:32] or None,
        note=(request.form.get('note') or '').strip()[:256] or None))
    log_action('to_part_added', 'equipment', unit.id, details=name)
    db.session.commit()
    return redirect(url_for('equipment.view', unit_id=unit.id))


@equipment.route('/to-parts/<int:part_id>/delete', methods=['POST'])
@login_required
@requires_permission('equipment')
def delete_to_part(part_id):
    from app.models import ToPart
    part = ToPart.query.get_or_404(part_id)
    unit_id = part.equipment_id
    log_action('to_part_removed', 'equipment', unit_id, details=part.name)
    db.session.delete(part)
    db.session.commit()
    return redirect(url_for('equipment.view', unit_id=unit_id))
