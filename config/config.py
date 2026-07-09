import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-key-change-in-production'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = True

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
    db_url = os.environ.get('DATABASE_URL', '')
    SQLALCHEMY_DATABASE_URI = db_url.replace('postgresql://', 'postgresql+psycopg://')

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}