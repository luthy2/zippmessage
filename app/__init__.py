from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_oauthlib.client import OAuth
from embedly import Embedly
from config import SECRET_KEY, MEMCACHEDCLOUD_SERVERS, MEMCACHEDCLOUD_USERNAME, MEMCACHEDCLOUD_PASSWORD, CELERY_BROKER, KEEN_PROJECT_ID, KEEN_WRITE_KEY, KEEN_READ_KEY
import logging
import sys
import bmemcached
import urlparse
import json
import redis
import celery
import keen

app = Flask(__name__)
app.config.from_object('config')
db = SQLAlchemy(app)
lm = LoginManager()
lm.init_app(app)
lm.login_view = 'login'
lm.login_message = u'you must login to view this page'
app.secret_key = SECRET_KEY
oauth = OAuth()
embedly = Embedly('3ec6801e9b5e4931925749186fd75996')
bm = bmemcached.Client(MEMCACHEDCLOUD_SERVERS, MEMCACHEDCLOUD_USERNAME, MEMCACHEDCLOUD_PASSWORD)
celery = celery.Celery('app', broker = CELERY_BROKER)
mailgun_api = "https://api.mailgun.net/v3/zippmsg.com/messages"
mailgun_auth = "key-96d0fea83b79dd08312c6c68ea308679"


twitter = oauth.remote_app('twitter',
    # unless absolute urls are used to make requests, this will be added
    # before all URLs.  This is also true for request_token_url and others.
    base_url='https://api.twitter.com/1.1/',
    # where flask should look for new request tokens
    request_token_url='https://api.twitter.com/oauth/request_token',
    # where flask should exchange the token with the remote application
    access_token_url='https://api.twitter.com/oauth/access_token',
    # twitter knows two authorizatiom URLs.  /authorize and /authenticate.
    # they mostly work the same, but for sign on /authenticate is
    # expected because this will give the user a slightly different
    # user interface on the twitter side.
    authorize_url='https://api.twitter.com/oauth/authenticate',
    # the consumer keys from the twitter application registry.
    consumer_key='OQf7Rxc5hFw79JlTLzY58SUD2',
    consumer_secret='thcXQfWuuzfE6ggwAfiqs1vXwtT8k7GWSSPuPq8hHzc0GX6UHZ'
)



app.logger.addHandler(logging.StreamHandler(sys.stdout))
app.logger.setLevel(logging.ERROR)

from app import views, models
