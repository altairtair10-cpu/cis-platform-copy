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

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(documents_bp)
    app.register_blueprint(equipment_bp)
    app.register_blueprint(transport_bp)
    app.register_blueprint(hr_bp)
    app.register_blueprint(errors_bp)

    return app
