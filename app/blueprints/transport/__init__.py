from flask import Blueprint, render_template, request
from flask_login import login_required
from app.models import TransportRun
from app.decorators import requires_permission

transport = Blueprint('transport', __name__, url_prefix='/transport',
                      template_folder='../../app/templates/transport')

@transport.route('/')
@login_required
@requires_permission('transport')
def index():
    page = request.args.get('page', 1, type=int)
    pagination = TransportRun.query.order_by(TransportRun.scheduled.desc())\
                                    .paginate(page=page, per_page=25, error_out=False)
    runs = pagination.items
    return render_template('transport/index.html', runs=runs, pagination=pagination)