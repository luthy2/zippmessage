from flask import Flask
from flask.ext.sqlalchemy import SQLAlchemy
from flask.ext.login import LoginManager
from flask_oauth import OAuth
from config import SECRET_KEY




app = Flask(__name__)
app.config.from_object('config')
db = SQLAlchemy(app)
lm = LoginManager()
lm.init_app(app)
lm.login_view = 'login'
lm.login_message = u'you must login to view this page'
app.secret_key = SECRET_KEY
oauth = OAuth()

twitter = oauth.remote_app('twitter',
    # unless absolute urls are used to make requests, this will be added
    # before all URLs.  This is also true for request_token_url and others.
    base_url='https://api.twitter.com/1/',
    # where flask should look for new request tokens
    request_token_url='https://api.twitter.com/1/oauth/request_token',
    # where flask should exchange the token with the remote application
    access_token_url='https://api.twitter.com/1/oauth/access_token',
    # twitter knows two authorizatiom URLs.  /authorize and /authenticate.
    # they mostly work the same, but for sign on /authenticate is
    # expected because this will give the user a slightly different
    # user interface on the twitter side.
    authorize_url='https://api.twitter.com/1/oauth/authorize',
    # the consumer keys from the twitter application registry.
    consumer_key='4nSJO5pDAuJzdXZOvmiPZt0Zn',
    consumer_secret='DzS2AbqlbtIXCYLYB1lzQvEODcKIHCz3UmWMUILql9aiIQshQQ'
)



from app import views, models