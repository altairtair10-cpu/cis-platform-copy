from functools import wraps
from flask import abort, flash, redirect, url_for
from flask_login import current_user

def requires_role(*roles):
    """Restrict a route to specific roles."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('auth.login'))
            if current_user.role not in roles and current_user.role != 'it_admin':
                abort(403)
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def requires_permission(module):
    """Restrict a route to users with a specific module permission."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('auth.login'))
            if not current_user.can_access(module):
                abort(403)
            return f(*args, **kwargs)
        return decorated_function
    return decorator
