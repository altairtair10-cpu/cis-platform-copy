import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-key-change-in-production'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = True

class DevelopmentConfig(Config):
    DEBUG = True
    db_url = os.environ.get('DATABASE_URL', '')
    SQLALCHEMY_DATABASE_URI = db_url.replace('postgresql://', 'postgresql+psycopg://') or \
        'sqlite:///cis_dev.db'

class ProductionConfig(Config):
    DEBUG = False
    db_url = os.environ.get('DATABASE_URL', '')
    SQLALCHEMY_DATABASE_URI = db_url.replace('postgresql://', 'postgresql+psycopg://')

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
