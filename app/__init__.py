from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_oauth import OAuth
from embedly import Embedly
from config import SECRET_KEY, MEMCACHEDCLOUD_SERVERS, MEMCACHEDCLOUD_USERNAME, MEMCACHEDCLOUD_PASSWORD
import logging
import sys
import bmemcached
import urlparse
import json


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
    consumer_key='hDdtxxgJc8P6V6ZKiNksD4ryi',
    consumer_secret='b0U9ZC31BcwMnBx9KWezHhqDwq2lcq87dMwxyNi2fsp9qV4dtn'
)



app.logger.addHandler(logging.StreamHandler(sys.stdout))
app.logger.setLevel(logging.ERROR)

from app import views, models
