from flask import Blueprint, render_template
from flask_login import login_required, current_user
from app.models import Document, Equipment, TransportRun, PTORequest, User

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
        'equipment_maint':    Equipment.query.filter_by(status='maintenance').count(),
        'docs_total':         Document.query.count(),
        'docs_pending':       Document.query.filter_by(status='pending').count(),
        'docs_approved':      Document.query.filter_by(status='approved').count(),
        'staff_total':        User.query.filter_by(is_active=True).count(),
        'staff_role':         User.query.filter_by(role=current_user.role, is_active=True).count(),
    }
    recent_docs = Document.query.order_by(Document.created_at.desc()).limit(8).all()
    return render_template('dashboard.html', stats=stats, recent_docs=recent_docs)