from flask import Blueprint, render_template
from flask_login import login_required
from app.models import User, PTORequest, WorkLog
from app.decorators import requires_permission

hr = Blueprint('hr', __name__, url_prefix='/hr',
               template_folder='../../app/templates/hr')

@hr.route('/')
@login_required
@requires_permission('hr')
def index():
    staff = User.query.filter_by(is_active=True).order_by(User.last_name).all()
    pto   = PTORequest.query.filter_by(status='pending').all()
    return render_template('hr/index.html', staff=staff, pto=pto)
