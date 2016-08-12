web: gunicorn app:app
init: python db_create.py
upgrade: python db_upgrade.py
worker: celery worker --app=zippmessage
