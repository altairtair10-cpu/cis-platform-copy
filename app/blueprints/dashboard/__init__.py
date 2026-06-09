from flask import Blueprint, render_template
from flask_login import login_required, current_user
from app.models import Document, Equipment, TransportRun, PTORequest, User
from app.decorators import requires_permission

dashboard = Blueprint('dashboard', __name__,
                      template_folder='../../app/templates/dashboard')

@dashboard.route('/')
@dashboard.route('/dashboard')
@login_required
def index():
    stats = {
        'equipment_total':    Equipment.query.count(),
        'equipment_deployed': Equipment.query.filter_by(status='deployed').count(),
        'equipment_idle':     Equipment.query.filter_by(status='idle').count(),
        'open_requests':      Document.query.filter_by(status='pending').count(),
        'staff_total':        User.query.filter_by(is_active=True).count(),
        'transport_today':    TransportRun.query.count(),
    }
    recent_docs = Document.query.order_by(Document.created_at.desc()).limit(5).all()
    return render_template('dashboard.html', stats=stats, recent_docs=recent_docs)
