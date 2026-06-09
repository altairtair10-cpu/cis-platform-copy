from flask import Blueprint, render_template
from flask_login import login_required
from app.models import Equipment, MaintenanceLog
from app.decorators import requires_permission

equipment = Blueprint('equipment', __name__, url_prefix='/equipment',
                      template_folder='../../app/templates/equipment')

@equipment.route('/')
@login_required
@requires_permission('equipment')
def index():
    units = Equipment.query.order_by(Equipment.unit_id).all()
    return render_template('equipment/index.html', units=units)

@equipment.route('/<int:unit_id>')
@login_required
@requires_permission('equipment')
def view(unit_id):
    unit = Equipment.query.get_or_404(unit_id)
    logs = MaintenanceLog.query.filter_by(equipment_id=unit.id)\
                               .order_by(MaintenanceLog.created_at.desc()).all()
    return render_template('equipment/view.html', unit=unit, logs=logs)
