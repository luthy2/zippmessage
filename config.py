import os
import json

basedir = os.path.abspath(os.path.dirname(__file__))


WTF_CSRF_ENABLED = True
SECRET_KEY = '],.iukY07|sJ}?_g&R#RnFmLAr1@2tgdQ!NzYR}-7+O8_Sz;lwc<){$Bav j^!Oo'

if os.environ.get('DATABASE_URL') is None:
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(basedir, 'app.db')
else:
    SQLALCHEMY_DATABASE_URI = os.environ['DATABASE_URL']

SQLALCHEMY_MIGRATE_REPO = os.path.join(basedir, 'db_repository')
SQLALCHEMY_RECORD_QUERIES = True

DATABASE_QUERY_TIMEOUT = 0.5

MEMCACHEDCLOUD_SERVERS = os.environ.get('MEMCACHEDCLOUD_SERVERS').split(',')
MEMCACHEDCLOUD_USERNAME = os.environ.get('MEMCACHEDCLOUD_USERNAME')
MEMCACHEDCLOUD_PASSWORD = os.environ.get('MEMCACHEDCLOUD_PASSWORD')

CELERY_BROKER = os.environ.get('MEMCACHEDCLOUD_SERVERS')
CELERY_RESULT_BACKEND = os.environ.get('MEMCACHEDCLOUD_SERVERS')
CELERY_TASK_SERIALIZER = json
BROKER_POOL_LIMIT = 1
