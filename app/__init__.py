from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from config.config import config

db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()

def create_app(config_name='default'):
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

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
    app.register_blueprint(contracts_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(documents_bp)
    app.register_blueprint(equipment_bp)
    app.register_blueprint(transport_bp)
    app.register_blueprint(hr_bp)
    app.register_blueprint(inventory_bp)
    app.register_blueprint(errors_bp)
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
