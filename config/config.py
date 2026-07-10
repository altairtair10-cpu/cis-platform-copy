import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-key-change-in-production'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None          # token valid for the whole session
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = timedelta(hours=12)
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_DURATION = timedelta(days=14)
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', 'instance/uploads')
    MAX_CONTENT_LENGTH = 20 * 1024 * 1024  # 20 MB max upload

    # ── Session / cookie hardening ──────────────────────────────
    SESSION_COOKIE_HTTPONLY  = True            # JavaScript cannot read the login cookie
    SESSION_COOKIE_SAMESITE  = 'Lax'           # cookie not sent on cross-site requests
    PERMANENT_SESSION_LIFETIME = timedelta(hours=12)
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = 'Lax'
    REMEMBER_COOKIE_DURATION = timedelta(days=7)

class DevelopmentConfig(Config):
    DEBUG = True
    SESSION_COOKIE_SECURE  = False             # localhost is http — cookie must work over http locally
    REMEMBER_COOKIE_SECURE = False
    db_url = os.environ.get('DATABASE_URL', '')
    SQLALCHEMY_DATABASE_URI = db_url.replace('postgresql://', 'postgresql+psycopg://') or \
        'sqlite:///cis_dev.db'

class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE  = True              # https only in production (Railway)
    REMEMBER_COOKIE_SECURE = True
    PREFERRED_URL_SCHEME = 'https'
    db_url = os.environ.get('DATABASE_URL', '')
    SQLALCHEMY_DATABASE_URI = db_url.replace('postgresql://', 'postgresql+psycopg://')

class TestingConfig(Config):
    TESTING = True
    DEBUG = False
    WTF_CSRF_ENABLED = False            # forms tested without tokens
    RATELIMIT_ENABLED = False
    SQLALCHEMY_DATABASE_URI = 'sqlite://'   # in-memory

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}