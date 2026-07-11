from flask import Flask, flash, redirect, request, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_wtf import CSRFProtect
from flask_babel import Babel
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from config.config import config

db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()
csrf = CSRFProtect()
babel = Babel()
limiter = Limiter(key_func=get_remote_address, storage_uri='memory://')

def init_sentry():
    """Error monitoring — active only when SENTRY_DSN is set (production)."""
    import os
    dsn = os.environ.get('SENTRY_DSN')
    if dsn:
        import sentry_sdk
        from sentry_sdk.integrations.flask import FlaskIntegration
        sentry_sdk.init(
            dsn=dsn,
            integrations=[FlaskIntegration()],
            send_default_pii=False,      # do not send user data
            traces_sample_rate=0.0,      # errors only, no performance tracing
        )


def create_app(config_name='default'):
    init_sentry()
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

    from app.i18n import select_locale, compile_catalogs
    import os as _os2
    compile_catalogs(_os2.path.join(_os2.path.dirname(_os2.path.dirname(__file__)), 'translations'))
    app.config.setdefault('BABEL_DEFAULT_LOCALE', 'ru')
    app.config.setdefault('BABEL_TRANSLATION_DIRECTORIES',
                          _os2.path.join(_os2.path.dirname(_os2.path.dirname(__file__)), 'translations'))
    babel.init_app(app, locale_selector=select_locale)

    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'

    from app.blueprints.auth import auth as auth_bp
    from app.blueprints.dashboard import dashboard as dashboard_bp
    from app.blueprints.documents import documents as documents_bp
    from app.blueprints.equipment import equipment as equipment_bp
    from app.blueprints.transport import transport as transport_bp
    from app.blueprints.hr import hr as hr_bp
    from app.blueprints.errors import errors as errors_bp
    from app.blueprints.contracts import contracts as contracts_bp
    from app.blueprints.inventory import inventory as inventory_bp
    from app.blueprints.ai import ai as ai_bp
    from app.blueprints.admin import admin as admin_bp
    app.register_blueprint(contracts_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(documents_bp)
    app.register_blueprint(equipment_bp)
    app.register_blueprint(transport_bp)
    app.register_blueprint(hr_bp)
    app.register_blueprint(inventory_bp)
    app.register_blueprint(ai_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(errors_bp)

    @app.after_request
    def security_headers(resp):
        resp.headers.setdefault('X-Content-Type-Options', 'nosniff')
        resp.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
        resp.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
        resp.headers.setdefault('Permissions-Policy', 'camera=(), microphone=(), geolocation=()')
        if not app.debug and not app.testing:
            resp.headers.setdefault('Strict-Transport-Security',
                                    'max-age=31536000; includeSubDomains')
        return resp

    @app.before_request
    def enforce_password_change():
        """Users flagged with a temporary password must set a new one first."""
        from flask_login import current_user
        allowed = ('auth.settings', 'auth.settings_password', 'auth.logout',
                   'auth.set_language', 'static')
        if (current_user.is_authenticated
                and getattr(current_user, 'must_change_password', False)
                and request.endpoint
                and request.endpoint not in allowed):
            flash('Please set a new password before continuing. / Пожалуйста, смените временный пароль.', 'warning')
            return redirect(url_for('auth.settings'))

    import os as _os
    if (config_name == 'production'
            and _os.environ.get('ENABLE_SCHEDULER', '1') == '1'):
        from app.scheduler import start_scheduler
        start_scheduler(app)

    @app.context_processor
    def inject_ms_sso():
        from app.services.ms_auth import enabled
        return dict(ms_sso_enabled=enabled())

    @app.context_processor
    def inject_branding():
        from app.models import AppSetting
        try:
            return dict(branding=dict(
                company_name=AppSetting.get('company_name', 'CIS Platform'),
                has_logo=bool(AppSetting.get('logo_filename')),
            ))
        except Exception:
            # table may not exist yet (fresh DB before migration)
            return dict(branding=dict(company_name='CIS Platform', has_logo=False))

    @app.context_processor
    def inject_notifications():
        from flask_login import current_user
        from app.models import Notification
        if current_user.is_authenticated:
            notifs = Notification.query.filter_by(
                user_id=current_user.id, is_read=False
            ).order_by(Notification.created_at.desc()).limit(10).all()
            return dict(notifications=notifs, unread_count=len(notifs))
        return dict(notifications=[], unread_count=0)
    return app