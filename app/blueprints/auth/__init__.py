from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, login_required, current_user
import secrets
from app import db, limiter
from app.audit import log_action
from app.models import User, DEPARTMENTS, Document
from wtforms import StringField, PasswordField, SelectField, BooleanField
from wtforms.validators import DataRequired, Email, Length, Optional
from flask_wtf import FlaskForm
from werkzeug.security import generate_password_hash


def _split_name(full):
    """Split a 'First Last' string into (first, last)."""
    parts = (full or '').strip().split(' ', 1)
    first = parts[0] if parts else ''
    last  = parts[1] if len(parts) > 1 else ''
    return first, last


auth = Blueprint('auth', __name__, url_prefix='/auth',
                 template_folder='../../app/templates/auth')

class LoginForm(FlaskForm):
    email    = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember = BooleanField('Remember me')

class UserForm(FlaskForm):
    full_name  = StringField('Full name', validators=[DataRequired(), Length(max=120)])
    email      = StringField('Email', validators=[DataRequired(), Email()])
    password   = PasswordField('Password', validators=[Optional(), Length(min=6)])
    role       = SelectField('Role', choices=[
        ('field',       'Field Worker'),
        ('mechanic',    'Mechanic'),
        ('transport',   'Transport'),
        ('hse',         'HSE'),
        ('dept_head',   'Department Head'),
        ('hr',          'HR'),
        ('accountant',  'Accountant'),
        ('procurement', 'Procurement'),
        ('director',    'Director'),
        ('it_admin',    'IT Admin'),
    ])
    department = StringField('Department', validators=[Optional(), Length(max=100)])
    language   = SelectField('Language', choices=[('ru','Русский'),('en','English'),('kz','Қазақша')])
    is_active  = BooleanField('Active')

class SignupForm(FlaskForm):
    full_name = StringField('Full name', validators=[DataRequired()])
    email     = StringField('Email', validators=[DataRequired(), Email()])
    password  = PasswordField('Password', validators=[DataRequired(), Length(min=8)])

@auth.route('/login', methods=['GET', 'POST'])
@limiter.limit('10 per minute; 60 per hour', methods=['POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.lower()).first()
        if user and user.check_password(form.password.data) and user.is_active:
            login_user(user, remember=form.remember.data)
            from datetime import datetime
            user.last_login = datetime.utcnow()
            log_action('login', 'user', user.id)
            db.session.commit()
            next_page = request.args.get('next')
            # only allow same-site relative redirects (prevents open redirect)
            if not next_page or not next_page.startswith('/') or next_page.startswith('//'):
                next_page = None
            return redirect(next_page or url_for('dashboard.index'))
        log_action('login_failed', details=form.email.data.lower()[:120])
        db.session.commit()
        flash('Invalid email or password.', 'danger')
    return render_template('login.html', form=form)

@auth.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))

@auth.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
    form = SignupForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        if not email.endswith('@cis.kz'):
            flash('Please use your @cis.kz work email.', 'danger')
            return render_template('signup.html', form=form)
        if User.query.filter_by(email=email).first():
            flash('An account with this email already exists.', 'danger')
            return render_template('signup.html', form=form)
        first, last = _split_name(form.full_name.data)
        user = User(
            first_name=first,
            last_name=last,
            email=email,
            role='field',
            is_active=False,
        )
        user.password_hash = generate_password_hash(form.password.data, method='pbkdf2:sha256')
        db.session.add(user)
        db.session.flush()
        log_action('signup', 'user', user.id, details=email)
        db.session.commit()
        flash('Account created. An admin will review and activate your account soon.', 'success')
        return redirect(url_for('auth.login'))
    return render_template('signup.html', form=form)

@auth.route('/set-language/<lang>')
@login_required
def set_language(lang):
    if lang in ['ru', 'en', 'kz']:
        current_user.language = lang
        db.session.commit()
    return redirect(request.referrer or url_for('dashboard.index'))

# ── SETTINGS ──────────────────────────────────────────────────────────────────

@auth.route('/settings')
@login_required
def settings():
    stats = None
    if current_user.role in ('it_admin', 'director'):
        stats = {
            'users':        User.query.count(),
            'active_users': User.query.filter_by(is_active=True).count(),
            'documents':    Document.query.count(),
        }
    return render_template('auth/settings.html', departments=DEPARTMENTS, stats=stats)

@auth.route('/settings/profile', methods=['POST'])
@login_required
def settings_profile():
    first = (request.form.get('first_name') or '').strip()
    last  = (request.form.get('last_name') or '').strip()
    if not first or not last:
        flash('First and last name are required.', 'danger')
        return redirect(url_for('auth.settings'))
    current_user.first_name = first
    current_user.last_name  = last
    current_user.position   = (request.form.get('position') or '').strip() or None
    current_user.department = (request.form.get('department') or '').strip() or None
    db.session.commit()
    flash('Profile updated.', 'success')
    return redirect(url_for('auth.settings'))

@auth.route('/settings/password', methods=['POST'])
@login_required
def settings_password():
    current = request.form.get('current_password') or ''
    new     = request.form.get('new_password') or ''
    confirm = request.form.get('confirm_password') or ''
    if not current_user.check_password(current):
        flash('Current password is incorrect.', 'danger')
        return redirect(url_for('auth.settings'))
    if len(new) < 8:
        flash('New password must be at least 8 characters.', 'danger')
        return redirect(url_for('auth.settings'))
    if new != confirm:
        flash('New passwords do not match.', 'danger')
        return redirect(url_for('auth.settings'))
    current_user.set_password(new)
    current_user.must_change_password = False
    log_action('password_changed', 'user', current_user.id)
    db.session.commit()
    flash('Password changed successfully.', 'success')
    return redirect(url_for('auth.settings'))

@auth.route('/settings/preferences', methods=['POST'])
@login_required
def settings_preferences():
    lang = request.form.get('language')
    if lang in ('ru', 'en', 'kz'):
        current_user.language = lang
    session['email_notifications'] = bool(request.form.get('email_notifications'))
    session['inapp_notifications'] = bool(request.form.get('inapp_notifications'))
    db.session.commit()
    flash('Preferences saved.', 'success')
    return redirect(url_for('auth.settings'))

@auth.route('/users')
@login_required
def users():
    if current_user.role != 'it_admin':
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard.index'))
    all_users = User.query.order_by(User.id).all()
    return render_template('auth/users.html', users=all_users)

@auth.route('/users/new', methods=['GET', 'POST'])
@login_required
def new_user():
    if current_user.role != 'it_admin':
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard.index'))
    form = UserForm()
    if request.method == 'GET':
        form.is_active.data = True
    if form.validate_on_submit():
        if User.query.filter_by(email=form.email.data.lower()).first():
            flash('Email already exists.', 'danger')
            return render_template('auth/user_form.html', form=form, title='New user')
        first, last = _split_name(form.full_name.data)
        user = User(
            first_name = first,
            last_name  = last,
            email      = form.email.data.lower(),
            role       = form.role.data,
            department = form.department.data,
            language   = form.language.data,
            is_active  = form.is_active.data,
        )
        temp_password = form.password.data or secrets.token_urlsafe(9)
        user.set_password(temp_password)
        user.must_change_password = True
        db.session.add(user)
        db.session.flush()
        log_action('user_created', 'user', user.id, details=user.email)
        db.session.commit()
        if form.password.data:
            flash(f'User {user.full_name} created. They must set a new password at first login.', 'success')
        else:
            flash(f'User {user.full_name} created. Temporary password: {temp_password} '
                  f'(share it securely — they must change it at first login).', 'success')
        return redirect(url_for('auth.users'))
    return render_template('auth/user_form.html', form=form, title='New user')

@auth.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_user(user_id):
    if current_user.role != 'it_admin':
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard.index'))
    user = User.query.get_or_404(user_id)
    form = UserForm(obj=user)
    if request.method == 'GET':
        form.full_name.data = user.full_name
    if form.validate_on_submit():
        first, last = _split_name(form.full_name.data)
        user.first_name = first
        user.last_name  = last
        user.email      = form.email.data.lower()
        user.role       = form.role.data
        user.department = form.department.data
        user.language   = form.language.data
        user.is_active  = form.is_active.data
        if form.password.data:
            user.set_password(form.password.data)
            user.must_change_password = True
        log_action('user_updated', 'user', user.id, details=user.email)
        db.session.commit()
        flash(f'User {user.full_name} updated.', 'success')
        return redirect(url_for('auth.users'))
    return render_template('auth/user_form.html', form=form, title='Edit user', user=user)

@auth.route('/users/<int:user_id>/deactivate', methods=['POST'])
@login_required
def deactivate_user(user_id):
    if current_user.role != 'it_admin':
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard.index'))
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('Cannot deactivate yourself.', 'danger')
        return redirect(url_for('auth.users'))
    user.is_active = not user.is_active
    status = 'activated' if user.is_active else 'deactivated'
    log_action(f'user_{status}', 'user', user.id, details=user.email)
    db.session.commit()
    flash(f'User {user.full_name} {status}.', 'success')
    return redirect(url_for('auth.users'))