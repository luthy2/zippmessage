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
			return tags


class User(db.Model):
	id = db.Column(db.Integer, primary_key = True)
	oauth_token = db.Column(db.String(200))
	oauth_secret = db.Column(db.String(200))
	username = db.Column(db.String(80))
	email = db.Column(db.String(240))

	sent_messages = db.relationship('Message', backref='author', lazy='dynamic')
	inbox_messages = db.relationship('UserMessage', cascade = 'all, delete-orphan', backref = 'user', lazy ='dynamic')


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

	def inbox(self):
		return UserMessage.query.filter(UserMessage.user_id == self.id).filter(UserMessage.is_read == False).order_by(UserMessage.message_id.desc())

	def bookmarks(self):
		return UserMessage.query.filter(UserMessage.user_id == self.id).filter( UserMessage.is_bookmarked == True)

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

	def tags_for_user(self):
		# empty list
		user_tags = []
		# iterate through the tag strings, appending them to the empty list
		bookmarks = self.bookmarks()
		for item in bookmarks:
			user_tags += item.tags.lower().split(',')
		#list comprehension to remove empty strings, and strip whitespace
		user_tags = [tag.strip() for tag in user_tags if tag != '']
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
	timestamp = db.Column(db.DateTime)
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

	def request_url(self):
		resp = embedly.oembed(self.url, words = 25, luxe = 1)
		if not resp["type"] == "error":
			return resp
		else:
			return False

	def get_content(self):
		resp = embedly.extract(self.url, autoplay= 'true')
		if not resp["type"] == "error":
			return resp
		else:
			return False

	def render_url(self):
		resp = self.request_url()
		if not resp:
			return render_no_style(self.url)
		else:
			if 'url' in resp:
				url = resp["url"]
			else:
				url = self.url
			if 'twitter.com' in url:
				return twitter_tag(url)
			elif 'soundcloud.com' in url:
				return soundcloud_tag(url)
			elif 'spotify.com' in url:
				return spotify_tag(url)
			elif resp['type'] == 'link':
				return article_tag(resp)
			elif resp["type"] == 'photo':
				return image_tag(url)
			else:
				return render_no_style(self.url)




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
		return self


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


def twitter_tag(url):
	url = url
	TWITTER_SCRIPT_TAG = 	'<div class="list-group-item">'\
							'<blockquote class="twitter-tweet tw-align-center">' \
							'<a href="%s"></a></blockquote>' \
							'<script async src="https://platform.twitter.com/widgets.js" ' \
							'charset="utf-8"></script>'\
							'</div>'
	return TWITTER_SCRIPT_TAG % url

def soundcloud_tag(url):
	#custom rendering for soundcloud
	resp = requests.get('https://api.soundcloud.com/oembed?format=json&url=%s&iframe=true' % url)
	if not 'error' in resp:
		return resp['html']
	else:
		return render_no_style(url)

def spotify_tag(url):
	#custom rendering for spotify
	parse_object = urlparse(url)
	path = parse_object.path
	path = path.replace('/',':')
	p = 'spotify%s' % path

	spotify_tag =	'<div class = "list-group-item">' \
					'<iframe src="https://embed.spotify.com/?uri=%s"' \
					'width="100%%" height="80" frameborder="0" allowtransparency="true"></iframe>' \
					'</div>'
	return spotify_tag % p

def article_tag(resp):
	title = resp['title']
	description = resp['description']
	url = resp['url']

	tag = 	'<a class = "list-group-item"  href = "%s" target="_blank">' \
			'<h4 class = "list-group-item-heading">%s</h4>' \
			'<p class = "list-group-item-text">%s</p>' \
			'</a>'

	return tag % (url, title, description)

def render_no_style(url):
	#custom render for urls that fail embedly lookup
	parse_object = urlparse(url)
	short_url = parse_object.netloc
	no_style_tag = '<a href = "%s" class = "list-group-item">Content via %s</a>'
	return no_style_tag % url , short_url

def image_tag(url):
	image_tag = '<li class = "list-group-item" >' \
				'<img src = "%s" width="100%%">' \
				'</li>'
	return image_tag % url
