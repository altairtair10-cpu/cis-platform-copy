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

class DevelopmentConfig(Config):
    DEBUG = True
    db_url = os.environ.get('DATABASE_URL', '')
    SQLALCHEMY_DATABASE_URI = db_url.replace('postgresql://', 'postgresql+psycopg://') or \
        'sqlite:///cis_dev.db'

class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True
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
