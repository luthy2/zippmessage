from app import db
from app import app
from app import embedly
from urlparse import urlparse
from datetime import datetime
from collections import Counter
import requests


approved_contacts = db.Table('approved_contacts',
	db.Column('from_contact_id', db.Integer, db.ForeignKey('user.id')),
	db.Column('to_contact_id', db.Integer, db.ForeignKey('user.id'))
)

recipients = db.Table('message_recipients',
	db.Column('message_id', db.Integer, db.ForeignKey('message.id')),
	db.Column('user_id', db.Integer, db.ForeignKey('user.id'))
)


class UserMessage(db.Model):
	user_id = db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key = True)
	message_id = db.Column('message_id', db.Integer, db.ForeignKey('message.id'), primary_key = True)

	is_read = db.Column('is_read', db.Boolean, default = False)
	is_bookmarked = db.Column('is_bookmarked', db.Boolean, default = False)
	tags = db.Column(db.String())


	def __init__(self, message, is_read, is_bookmarked, tags):
		self.message = message
		self.is_bookmarked = is_bookmarked
		self.is_read = is_read
		self.tags = tags

	message = db.relationship('Message', backref = 'message')


	def usermessage_tags(self):
		# if there are no tags the field will be an empty string
		if self.tags == '':
			return False
		else:
			#creates and returns ['list', 'of', 'tags']
			tags = [t.strip() for t in self.tags.split(',') if t != '']
			tags = filter(None, tags)
			return tags


class User(db.Model):
	id = db.Column(db.Integer, primary_key = True)
	oauth_token = db.Column(db.String(200))
	oauth_secret = db.Column(db.String(200))
	username = db.Column(db.String(80))
	email = db.Column(db.String(240))
	# email_token = db.Column(db.String)
	# notifications_status = db.Column(db.Integer)
	# api_token = db.Column(db.String)
	sent_messages = db.relationship('Message', backref='author', lazy='dynamic')
	inbox_messages = db.relationship('UserMessage', cascade = 'all, delete-orphan', backref = 'user', lazy ='dynamic')
	activity_feed = db.relationship('Activity', backref='owner', lazy='dynamic')
	actions_created = db.relationship('Activity', backref='subject', lazy='dynamic')

	contacts = db.relationship('User',
								secondary = approved_contacts,
								primaryjoin = (approved_contacts.c.from_contact_id == id),
								secondaryjoin = (approved_contacts.c.to_contact_id == id),
								backref = db.backref('followers', lazy = 'dynamic'),
								lazy = 'dynamic')

	def __init__(self, username, contacts, sent_messages, inbox_messages):
		self.username = username
		self.contacts = contacts
		self.inbox_messages = inbox_messages
		self.sent_messages = sent_messages

	def __repr__(self):
		return '<User %r>' % (self.username)


	def get_id(self):
		try:
			return unicode(self.id) #python 2
		except NameError:
			return str(self.id) #python 3

	def is_authenticated(self):
		return True

	def is_active(self):
		return True

	def is_anonymous(self):
		return False

	def add_contact(self, user):
		if not self.is_contact(user):
			self.contacts.append(user)
			return self

	def remove_contact(self, user):
		if self.is_contact(user):
			self.contacts.remove(user)
			return self

	def is_contact(self, user):
		return self.contacts.filter(approved_contacts.c.to_contact_id == user.id).count() > 0

	# def create_api_token(self):
	# 	return 'token'
	#
	# def verify_api_token(self, token):
	# 	if token == self.api_token:
	# 		return True
	# 	else:
	# 		return False
	#
	# def create_email_token(self):
	# 	return token
	#
	# def verify_email_token(self, token):
	# 	if token == self.email_token:
	# 		return True
	# 	else:
	# 		return False

	def inbox(self):
		return UserMessage.query.filter(UserMessage.user_id == self.id).filter(UserMessage.is_read == False).order_by(UserMessage.message_id.desc())

	def bookmarks(self):
		return UserMessage.query.filter(UserMessage.user_id == self.id).filter( UserMessage.is_bookmarked == True).order_by(UserMessage.message_id.desc())

	def bookmark_message(self, message_id):
		user_message = UserMessage.query.filter(UserMessage.user_id == self.id).filter(UserMessage.message_id == message_id).one()
		user_message.is_read = True
		user_message.is_bookmarked = True
		db.session.commit()
		return self

	def dismiss_message(self, message_id):
		user_message = UserMessage.query.filter(UserMessage.user_id == self.id).filter(UserMessage.message_id == message_id).one()
		user_message.is_read = True
		user_message.is_bookmarked = False
		db.session.commit()
		return self

	def user_activity(self):
		activity = Activity.query.filter(Activity.owner_id == self.id).limit(50).order_by(self.timestamp.desc())
		return activity

	def create_activity(self, owner_id, action, message_id, timestamp = datetime.utcnow()):
		a = Activity(owner_id = owner_id, subject_id = self.id, action = action, message_id = message_id, timestamp = timestamp)
		db.session.add(a)
		db.session.commit(a)
		return self


	def tags_for_user(self):
		# empty list
		user_tags = []
		# iterate through the tag strings, appending them to the empty list
		bookmarks = self.bookmarks()
		for item in bookmarks:
			user_tags += item.tags.lower().split(',')
		#list comprehension to remove empty strings, and strip whitespace
		user_tags = [tag.strip() for tag in user_tags if tag != '']
		#there could still be empty strings from spaces so filter '' again
		user_tags = filter(None, user_tags)
		#creates a Counter of tags with the number of each, order by most common
		user_tags = Counter(user_tags)
		return user_tags


	def get_bookmarks_with_tag(self, tag):
		# we don't need to check if it's bookmarked because an unbookmarked message can't have tags
		# this will produce false matches, and might crash if there are no tags
		return UserMessage.query.filter(UserMessage.user_id == self.id).filter(UserMessage.tags.contains(tag))


class Message(db.Model):
	id= db.Column(db.Integer, primary_key = True)
	title = db.Column(db.String(100))
	url = db.Column(db.String(300))
	from_user = db.Column(db.Integer, db.ForeignKey('user.id'))
	is_delivered = db.Column(db.Boolean, default = False)
	points = db.Column(db.Integer)
	timestamp = db.Column(db.DateTime)
	message_activity = db.relationship("Activity", backref = 'message', lazy = 'dynamic')
	# private = db.Column(db.Boolean, default = True)

	recipients = db.relationship(	'User',
									secondary = recipients,
									primaryjoin = (recipients.c.message_id == id),
									secondaryjoin = (recipients.c.user_id == User.id),
									backref = db.backref('received_messages', lazy = 'dynamic'), lazy = 'dynamic')






	def __init__(self, title, url, author, timestamp):
		self.title = title
		self.url = url
		self.author = author
		self.timestamp = timestamp

	def __repr__(self):
		return '<Message %r>' % (self.title)


	def get_id(self):
		try:
			return unicode(self.id) #python 2
		except NameError:
			return str(self.id) #python 3


	def short_url(self):
		parse_object = urlparse(self.url)
		return parse_object.netloc

	def score(self, gravity = 1.8):
		p = self.points
		ts = self.timestamp
		now = datetime.utcnow()
		tdelta = now-ts
		s = tdelta.total_seconds / 3600.0
		score = (p / s**gravity)
		return score

	def format_timestamp(self):
		ts = self.timestamp
		now = datetime.utcnow()
		tdelta = now - ts
		s = tdelta.total_seconds()
		if s <= 59:
			s = s//1
			return '{0}s'.format(s)
		elif 60 <= s < 3600:
			s = s//60
			return '{0}m ago'.format(int(s))
		elif 3600 <= s < 86400:
			s = s//3600
			return '{0}h ago'.format(int(s))
		elif 86400 <= s < 604800:
			s = s//86400
			return '{0}d ago'.format(int(s))
		else:
			s = s//604800
			return '{0}w ago'.format(int(s))

	def request_url(self):
		resp = embedly.oembed(self.url, words = 25)
		if not resp["type"] == "error":
			return resp
		else:
			return False

	def get_content(self):
		resp = embedly.extract(self.url, autoplay= 'false', words = 25)
		if not resp["type"] == "error":
			return resp
		else:
			return False

	def render_url(self):
		content = get_url_content(self.url)
		return content

	def url_logo(self):
		short_url = self.short_url()
		return "https://logo.clearbit.com/%s?size=18" % short_url

	def deliver_message(self):
		if self.is_delivered is not True:
			self.is_delivered = True
			return self

	def add_recipient(self, user):
		recipient = User.query.get(user)
		self.recipients.append(recipient)
		return self

	def send_message(self, user):
		u = User.query.get(user)
		u.inbox_messages.append(UserMessage(message = self, is_read = False, is_bookmarked = False, tags = ''))
		db.session.add(u)
		db.session.commit()
		print "message added to inbox for " + str(u.username)
		return self


def twitter_tag(url):
	url = url
	TWITTER_SCRIPT_TAG = 	'<blockquote class="twitter-tweet tw-align-center" data-cards="hidden">' \
							'<a href="%s"></a></blockquote>' \
							'<script async src="https://platform.twitter.com/widgets.js" ' \
							'charset="utf-8"></script>'
	return TWITTER_SCRIPT_TAG % url


def spotify_tag(url):
	#custom rendering for spotify
	parse_object = urlparse(url)
	path = parse_object.path
	path = path.replace('/',':')
	p = 'spotify%s' % path

	spotify_tag =	'<div class = "list-group-item">' \
					'<iframe src="https://embed.spotify.com/?uri=%s"' \
					'width="100%%" height="90" frameborder="0" allowtransparency="true"></iframe>' \
					'</div>'
	return spotify_tag % p

def article_tag(resp, msg_url = None):
	url = ''
	image_tag = ''
	title_tag = ''
	description_tag= ''
	small_image_tag=''

	if url in resp:
		url = resp['url']
	else:
		url = msg_url or ''

	provider = provider_url(url)
	provider_tag = '<p style = "color:gray"><img src="https://logo.clearbit.com/%s?size=18"><small> %s</small></p>' % (provider, provider)

	if 'title' in resp:
		title = resp['title']
		title_tag = '<h4 class = "list-group-item-heading article-title-text" style="padding-top:2%%">%s</h4>' % title

	if 'description' in resp:
		description = resp['description']
		description_tag = '<p class = "list-group-item-text article-body-text">%s</p>' % description


	if 'thumbnail_url' in resp:
		img_url = resp['thumbnail_url']
		image_tag = '<li class = "list-group-item article"><img src="%s" style="max-width:100%%"></li>' % img_url
		small_image_tag ='<li class = "list-group-item article article-small"><img src="%s" style="max-width:100%%"></li>' % img_url


	tag = 	'<ul class = "list-group hidden-xs">' \
	'%s' \
	'<a class = "list-group-item"  href = "%s" target="_blank">' \
	'%s' \
	'%s' \
	'%s' \
	'</a>'\
	'</ul>'\
	'<ul class = "list-group visible-xs">' \
	'%s' \
	'<a class = "list-group-item"  href = "%s" target="_blank">' \
	'%s' \
	'%s' \
	'%s' \
	'</a>'\
	'</ul>'

	return tag % (image_tag, url, title_tag, description_tag, provider_tag, small_image_tag, url, title_tag, description_tag, provider_tag)

def render_no_style(url):
	#custom render for urls that fail embedly lookup
	provider = provider_url(url)
	no_style_tag = '<a href = "%s" class = "list-group-item" target = "_blank">Content via %s</a>'
	return no_style_tag % (url , provider)

def image_tag(url):
	p = provider_url(url)
	image_tag = '<ul class="list-group">'\
				'<li class = "list-group-item" >' \
				'<img id = "img-message" src = "%s" width="100%%">' \
				'<p style="padding-top:2%%">Image via <a href = "%s" target="_blank" rel="noopener">%s</a></p>'\
				'</li>'\
				'</ul>'
	return image_tag % (url, url, p)

def provider_url(url):
	resp = requests.get(url)
	url = resp.url
	parse_object = urlparse(url)
	provider = parse_object.netloc
	return provider or 'No Source'


def get_url_content(message_url):
	resp = embedly.oembed(message_url, words = 25)
	if resp["type"]== "error":
		return render_no_style(message_url)
	else:
		if 'url' in resp:
			url = resp["url"]
		else:
			url = message_url
		if 'twitter.com' and 'status' in url:
			return twitter_tag(url)
		elif 'spotify.com' in url:
			return spotify_tag(url)
		elif resp['type'] == 'link':
			return article_tag(resp, msg_url = message_url)
		elif resp["type"] == 'photo':
			return image_tag(url)
		elif resp['type'] == 'video':
			return '<div class ="embed-responsive embed-responsive-16by9">'+resp['html']+'</div>'
		elif 'soundcloud.com' in url:
			return resp['html']
		elif 'medium.com' in resp['provider_url']:
			 return resp['html']
		elif 'airbnb.com' in resp['provider_url']:
			message_url = message_url.encode('utf-8')
			return article_tag(resp, msg_url = message_url)
		elif 'amazon.com' in resp['provider_url']:
			return article_tag(resp, msg_url = url)
		else:
			return render_no_style(message_url)


class Activity(db.Model):
	owner_id = db.Column(db.Integer, db.ForeignKey('user.id'), primary_key = True) #index for construction of feeds
	subject_id = db.Column(db.Integer, db.ForeignKey('user.id'), primary_key=True) #who performed the action
	action = db.Column(db.String()) #the type of action
	message_id = db.Column(db.Integer, db.ForeignKey("message.id"), primary_key=True) #the message the action was performed on
	timestamp = db.Column(db.Datetime) #when

	def __init__(self, owner_id, subject_id, action, message_id, timestamp):
		self.owner_id = owner_id #who receives the activity
		self.subject_id = subject_id #who performed the action
		self.action = action
		self.message_id = message_id
		self.timestamp = timestamp
