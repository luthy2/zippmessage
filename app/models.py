from app import db
from app import app
from urlparse import urlparse
from datetime import datetime

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
	is_liked = db.Column('is_liked', db.Boolean, default = False)
	
	
	def __init__(self, message, is_read, is_liked):
		self.message = message
		self.is_liked = is_liked
		self.is_read = is_read
	
	message = db.relationship('Message', backref = 'message')
		
		
	
	
	
	
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
		return UserMessage.query.filter(UserMessage.user_id == self.id).filter( UserMessage.is_read == False)
		
	def likes(self):
		return UserMessage.query.filter(UserMessage.user_id == self.id).filter( UserMessage.is_liked == True)
		
	def like_message(self, message_id):
		user_message = UserMessage.query.filter(UserMessage.user_id == self.id).filter(UserMessage.message_id == message_id).one()
		user_message.is_read = True
		user_message.is_liked = True
		return self
		
	def dismiss_message(self, message_id):
		user_message = UserMessage.query.filter(UserMessage.user_id == self.id).filter(UserMessage.message_id == message_id).one()
		user_message.is_read = True
		db.session.commit()
		return self
		

class Message(db.Model):
	id= db.Column(db.Integer, primary_key = True)
	title = db.Column(db.String(100))
	url = db.Column(db.String(240))
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
		url = self.url
		parse_object = urlparse(url)
		return parse_object.netloc
	
		
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
		u.inbox_messages.append(UserMessage(message = self, is_read = False, is_liked = False))
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
			return '{0}m'.format(int(s))
		elif 3600 <= s < 86400:
			s = s//3600
			return '{0}h'.format(int(s))
		elif 86400 <= s < 604800:
			s = s//86400
			return '{0}d'.format(int(s))
		else:
			s = s//604800
			return '{0}w'.format(int(s))
	