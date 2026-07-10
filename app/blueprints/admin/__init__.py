import os
import uuid
from types import SimpleNamespace
from flask import (Blueprint, render_template, redirect, url_for, flash,
                   request, abort)
from flask_login import login_required, current_user
from app.models import (EquipmentType, ReferenceDepartment, Location,
                        AppSetting, DocNumberSetting, DOC_TYPES, db)
from app.audit import log_action
from app.decorators import requires_role
from app.storage import save_upload, send_attachment

admin = Blueprint('admin', __name__, url_prefix='/admin',
                  template_folder='../../app/templates/admin')

LOGO_EXTENSIONS = {'png', 'jpg', 'jpeg', 'svg', 'webp'}

# section registry: (model, url slug, human name)
_SECTIONS = {
    'equipment-types': (EquipmentType, 'equipment type'),
    'departments':     (ReferenceDepartment, 'department'),
    'locations':       (Location, 'location'),
}


def _get_model(section):
    if section not in _SECTIONS:
        abort(404)
    return _SECTIONS[section][0]


# ── HUB ───────────────────────────────────────────────────────────────────────

@admin.route('/')
@login_required
@requires_role('it_admin')
def index():
    counts = {
        'equipment_types': EquipmentType.query.count(),
        'departments':     ReferenceDepartment.query.count(),
        'locations':       Location.query.count(),
    }
    return render_template('admin/index.html', counts=counts)


# ── REFERENCE DATA (generic add / rename / toggle for all three lists) ────────

@admin.route('/reference-data')
@login_required
@requires_role('it_admin')
def reference_data():
    equipment_types = EquipmentType.query.order_by(EquipmentType.name).all()
    departments = ReferenceDepartment.query.order_by(ReferenceDepartment.name).all()
    locations = Location.query.order_by(Location.name).all()
    return render_template('admin/reference_data.html',
                           equipment_types=equipment_types,
                           departments=departments,
                           locations=locations)


@admin.route('/reference-data/<section>/add', methods=['POST'])
@login_required
@requires_role('it_admin')
def ref_add(section):
    model = _get_model(section)
    name = (request.form.get('name') or '').strip()
    if not name:
        flash('Name is required.', 'warning')
    elif model.query.filter_by(name=name).first():
        flash('That entry already exists.', 'warning')
    else:
        row = model(name=name)
        db.session.add(row)
        db.session.flush()
        log_action(f'ref_{section}_added', section, row.id, details=name)
        db.session.commit()
        flash('Added.', 'success')
    return redirect(url_for('admin.reference_data'))


@admin.route('/reference-data/<section>/<int:row_id>/rename', methods=['POST'])
@login_required
@requires_role('it_admin')
def ref_rename(section, row_id):
    model = _get_model(section)
    row = model.query.get_or_404(row_id)
    new_name = (request.form.get('name') or '').strip()
    if not new_name:
        flash('Name is required.', 'warning')
    elif new_name != row.name and model.query.filter_by(name=new_name).first():
        flash('That name is already in use.', 'warning')
    elif new_name != row.name:
        log_action(f'ref_{section}_renamed', section, row.id,
                   details=f'{row.name} -> {new_name}')
        row.name = new_name
        db.session.commit()
        flash('Renamed.', 'success')
    return redirect(url_for('admin.reference_data'))


@admin.route('/reference-data/<section>/<int:row_id>/toggle', methods=['POST'])
@login_required
@requires_role('it_admin')
def ref_toggle(section, row_id):
    model = _get_model(section)
    row = model.query.get_or_404(row_id)
    row.is_active = not row.is_active
    log_action(f'ref_{section}_{"activated" if row.is_active else "deactivated"}',
               section, row.id, details=row.name)
    db.session.commit()
    return redirect(url_for('admin.reference_data'))


# ── Backwards-compatible routes (previous admin panel URLs) ──────────────────

@admin.route('/reference-data/equipment-types/add', methods=['POST'],
             endpoint='add_equipment_type')
@login_required
@requires_role('it_admin')
def add_equipment_type():
    return ref_add('equipment-types')

@admin.route('/reference-data/equipment-types/<int:type_id>/toggle', methods=['POST'],
             endpoint='toggle_equipment_type')
@login_required
@requires_role('it_admin')
def toggle_equipment_type(type_id):
    return ref_toggle('equipment-types', type_id)

@admin.route('/reference-data/departments/add', methods=['POST'],
             endpoint='add_department')
@login_required
@requires_role('it_admin')
def add_department():
    return ref_add('departments')

@admin.route('/reference-data/departments/<int:dept_id>/toggle', methods=['POST'],
             endpoint='toggle_department')
@login_required
@requires_role('it_admin')
def toggle_department(dept_id):
    return ref_toggle('departments', dept_id)


# ── BRANDING ──────────────────────────────────────────────────────────────────

@admin.route('/branding', methods=['GET', 'POST'])
@login_required
@requires_role('it_admin')
def branding():
    if request.method == 'POST':
        name = (request.form.get('company_name') or '').strip()
        if name:
            AppSetting.set('company_name', name)
            log_action('branding_company_name', details=name)

        logo = request.files.get('logo')
        if logo and logo.filename:
            ext = logo.filename.rsplit('.', 1)[-1].lower() if '.' in logo.filename else ''
            if ext not in LOGO_EXTENSIONS:
                flash('Logo must be PNG, JPG, SVG or WEBP.', 'danger')
                return redirect(url_for('admin.branding'))
            stored_name, backend, size = save_upload(logo)
            AppSetting.set('logo_filename', stored_name)
            AppSetting.set('logo_backend', backend)
            AppSetting.set('logo_original', logo.filename)
            log_action('branding_logo_uploaded', details=logo.filename)

        db.session.commit()
        flash('Branding updated.', 'success')
        return redirect(url_for('admin.branding'))

    return render_template('admin/branding.html',
                           company_name=AppSetting.get('company_name', 'CIS Platform'),
                           logo_set=bool(AppSetting.get('logo_filename')))


@admin.route('/branding/logo/remove', methods=['POST'])
@login_required
@requires_role('it_admin')
def remove_logo():
    AppSetting.set('logo_filename', None)
    log_action('branding_logo_removed')
    db.session.commit()
    flash('Logo removed — default restored.', 'success')
    return redirect(url_for('admin.branding'))


# Public: the logo must render on the login page too, so no @login_required.
@admin.route('/branding/logo')
def logo():
    filename = AppSetting.get('logo_filename')
    if not filename:
        abort(404)
    shim = SimpleNamespace(
        storage_backend=AppSetting.get('logo_backend', 'local'),
        stored_filename=filename,
        original_filename=AppSetting.get('logo_original', filename),
    )
    resp = send_attachment(shim)
    # render inline instead of download
    resp.headers['Content-Disposition'] = 'inline'
    return resp


# ── DOCUMENT NUMBERING ────────────────────────────────────────────────────────

DEFAULT_PREFIXES = {
    'purchase_req': 'ТМЦ', 'trebovanie': 'ТРБ', 'po_services': 'РОУ',
    'defect_act': 'ДА', 'memo': 'СЗ', 'order': 'ПР', 'act': 'АКТ',
    'incoming': 'ВХ', 'outgoing': 'ИСХ',
}


@admin.route('/numbering', methods=['GET', 'POST'])
@login_required
@requires_role('it_admin')
def numbering():
    if request.method == 'POST':
        for doc_type in DEFAULT_PREFIXES:
            value = (request.form.get(f'prefix_{doc_type}') or '').strip()
            row = DocNumberSetting.query.filter_by(doc_type=doc_type).first()
            if row is None:
                row = DocNumberSetting(doc_type=doc_type)
                db.session.add(row)
            if value != (row.prefix or ''):
                log_action('numbering_prefix_changed', 'doc_type', None,
                           details=f'{doc_type}: {row.prefix} -> {value or "(default)"}')
            row.prefix = value or None
        db.session.commit()
        flash('Numbering settings saved.', 'success')
        return redirect(url_for('admin.numbering'))

    settings = {r.doc_type: r.prefix for r in DocNumberSetting.query.all()}
    rows = [(dt, DEFAULT_PREFIXES[dt], settings.get(dt) or '') for dt in DEFAULT_PREFIXES]
    return render_template('admin/numbering.html', rows=rows, doc_types=DOC_TYPES)
