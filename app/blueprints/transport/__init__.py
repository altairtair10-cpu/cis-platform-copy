from flask import Blueprint, render_template
from flask_login import login_required
from app.models import TransportRun
from app.decorators import requires_permission

transport = Blueprint('transport', __name__, url_prefix='/transport',
                      template_folder='../../app/templates/transport')

@transport.route('/')
@login_required
@requires_permission('transport')
def index():
    runs = TransportRun.query.order_by(TransportRun.scheduled.desc()).all()
    return render_template('transport/index.html', runs=runs)
