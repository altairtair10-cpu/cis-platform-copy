from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.models import User, PTORequest, db
from app.decorators import requires_permission
from datetime import datetime

hr = Blueprint('hr', __name__, url_prefix='/hr',
               template_folder='../../app/templates/hr')

@hr.route('/')
@login_required
@requires_permission('hr')
def index():
    staff = User.query.filter_by(is_active=True).order_by(User.first_name, User.last_name).all()
    pto = PTORequest.query.filter_by(status='pending').all()
    return render_template('hr/index.html', staff=staff, pto=pto)

@hr.route('/pto')
@login_required
def pto():
    my_requests = PTORequest.query.filter_by(user_id=current_user.id).order_by(PTORequest.created_at.desc()).all()
    return render_template('hr/pto.html', my_requests=my_requests)

@hr.route('/pto/new', methods=['GET', 'POST'])
@login_required
def pto_new():
    if request.method == 'POST':
        leave_type = request.form.get('leave_type', 'annual')
        start_date = datetime.strptime(request.form['start_date'], '%Y-%m-%d').date()
        end_date = datetime.strptime(request.form['end_date'], '%Y-%m-%d').date()
        reason = request.form.get('reason', '')

        if end_date < start_date:
            flash('End date cannot be before the start date.', 'danger')
            return render_template('hr/pto_new.html')

        req = PTORequest(
            user_id=current_user.id,
            leave_type=leave_type,
            start_date=start_date,
            end_date=end_date,
            reason=reason,
            status='pending'
        )
        db.session.add(req)
        db.session.commit()

        from app.models import Notification
        approvers = User.query.filter(
            User.role.in_(['it_admin', 'director', 'hr']),
            User.is_active == True
        ).all()
        for approver in approvers:
            db.session.add(Notification(
                user_id = approver.id,
                title   = f'New PTO request from {current_user.full_name}',
                body    = f'{leave_type} leave: {start_date} to {end_date}',
                link    = '/hr/',
                is_read = False,
            ))
        db.session.commit()
        flash('Request submitted successfully.', 'success')
        return redirect(url_for('hr.pto'))
    return render_template('hr/pto_new.html')


def _decide_pto(req_id, decision):
    """Shared approve/deny logic: record the decider and notify the employee."""
    from app.models import Notification
    req = PTORequest.query.get_or_404(req_id)
    if req.status != 'pending':
        flash('This request has already been decided.', 'warning')
        return redirect(url_for('hr.index'))
    req.status = 'approved' if decision == 'approve' else 'denied'
    req.approved_by = current_user.id
    db.session.add(Notification(
        user_id = req.user_id,
        title   = 'Your PTO request was ' + ('approved' if decision == 'approve' else 'denied'),
        body    = f'{req.leave_type} leave: {req.start_date} to {req.end_date}',
        link    = '/hr/pto',
        is_read = False,
    ))
    db.session.commit()
    flash('Request ' + ('approved.' if decision == 'approve' else 'denied.'), 'success')
    return redirect(url_for('hr.index'))


@hr.route('/pto/<int:req_id>/approve', methods=['POST'])
@login_required
@requires_permission('hr')
def pto_approve(req_id):
    return _decide_pto(req_id, 'approve')

@hr.route('/pto/<int:req_id>/deny', methods=['POST'])
@login_required
@requires_permission('hr')
def pto_deny(req_id):
    return _decide_pto(req_id, 'deny')


from . import orders  # noqa: E402,F401  (HR-приказы: приём, журнал, карточки)