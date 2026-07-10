from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app.models import EquipmentType, ReferenceDepartment, db

admin = Blueprint('admin', __name__, url_prefix='/admin',
                  template_folder='../../app/templates/admin')


def _require_it_admin():
    return current_user.role == 'it_admin'


@admin.route('/reference-data')
@login_required
def reference_data():
    if not _require_it_admin():
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard.index'))
    equipment_types = EquipmentType.query.order_by(EquipmentType.name).all()
    departments = ReferenceDepartment.query.order_by(ReferenceDepartment.name).all()
    return render_template('admin/reference_data.html',
                           equipment_types=equipment_types, departments=departments)


@admin.route('/reference-data/equipment-types/add', methods=['POST'])
@login_required
def add_equipment_type():
    if not _require_it_admin():
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard.index'))
    name = request.form.get('name', '').strip()
    if not name:
        flash('Name is required.', 'warning')
    elif EquipmentType.query.filter_by(name=name).first():
        flash('That equipment type already exists.', 'warning')
    else:
        db.session.add(EquipmentType(name=name))
        db.session.commit()
        flash('Equipment type added.', 'success')
    return redirect(url_for('admin.reference_data'))


@admin.route('/reference-data/equipment-types/<int:type_id>/toggle', methods=['POST'])
@login_required
def toggle_equipment_type(type_id):
    if not _require_it_admin():
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard.index'))
    et = EquipmentType.query.get_or_404(type_id)
    et.is_active = not et.is_active
    db.session.commit()
    return redirect(url_for('admin.reference_data'))


@admin.route('/reference-data/departments/add', methods=['POST'])
@login_required
def add_department():
    if not _require_it_admin():
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard.index'))
    name = request.form.get('name', '').strip()
    if not name:
        flash('Name is required.', 'warning')
    elif ReferenceDepartment.query.filter_by(name=name).first():
        flash('That department already exists.', 'warning')
    else:
        db.session.add(ReferenceDepartment(name=name))
        db.session.commit()
        flash('Department added.', 'success')
    return redirect(url_for('admin.reference_data'))


@admin.route('/reference-data/departments/<int:dept_id>/toggle', methods=['POST'])
@login_required
def toggle_department(dept_id):
    if not _require_it_admin():
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard.index'))
    dept = ReferenceDepartment.query.get_or_404(dept_id)
    dept.is_active = not dept.is_active
    db.session.commit()
    return redirect(url_for('admin.reference_data'))