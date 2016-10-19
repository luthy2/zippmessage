import os

from flask import request, g, render_template, render_template_string, session, url_for, redirect, flash, jsonify, send_from_directory, make_response
from flask_login import login_user, logout_user, current_user, login_required
from app import app, db, lm, twitter, bm, celery, mailgun_api, mailgun_auth
from forms import NewMessageForm, RecipientsForm, TagForm, EmailForm
from models import User, Message, UserMessage, Activity, get_url_content
from datetime import datetime
import urllib
import time
import requests
import math
import keen

@app.before_request
def before_request():
	g.user = None
	if 'user_id' in session:
		g.user = User.query.get(session['user_id'])



@app.after_request
def after_request(response):
	db.session.remove()
	return response


@app.errorhandler(404)
def not_found_error():
	return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('500.html'), 500

@lm.user_loader
def load_user(id):
	return User.query.get(int(id))

@twitter.tokengetter
def get_twitter_token():
	"""This is used by the API to look for the auth token and secret
	it should use for API calls.  During the authorization handshake
	a temporary set of token and secret is used, but afterwards this
	function has to return the token and secret.  If you don't want
	to store this in the database, consider putting it into the
	session instead.
	"""

	user = g.user
	if user is not None:
		return user.oauth_token, user.oauth_secret



@app.route('/login')
def login():
	"""Calling into authorize will cause the OpenID auth machinery to kick
    in.  When all worked out as expected, the remote application will
    redirect back to the callback URL provided.
    """
	return twitter.authorize(callback=url_for('oauthorized', next=request.args.get('next') or request.referrer or None))

@app.route('/logout')
def logout():
	logout_user()
	current_user = None
	session.pop('user_id', None)
	session.pop('user', None)
	session.pop('flashed_messages', None)
	flash('You were signed out')
	return redirect(url_for('index'))


@app.route('/oauthorized')
def oauthorized():
	"""Called after authorization.  After this function finished handling,
	the OAuth information is removed from the session again.  When this
	happened, the tokengetter from above is used to retrieve the oauth
	token and secret.
	Because the remote application could have re-authorized the application
	it is necessary to update the values in the database.
	If the application redirected back after denying, the response passed
	to the function will be `None`.  Otherwise a dictionary with the values
	the application submitted.  Note that Twitter itself does not really
	redirect back unless the user clicks on the application name.
	"""
	resp = twitter.authorized_response()
	if resp is None:
		flash(u'You denied the request to sign in.')
		return redirect(next_url)

	user = User.query.filter_by(username=resp['screen_name']).first()
	first_login = False
	# user never signed on
	if user is None:
		first_login = True
		user = User(username = resp['screen_name'], contacts=(), sent_messages=(), inbox_messages=())
		#**todo issue a user a new token for  mobile auth. **
		db.session.add(user)
		user.add_contact(user)

	# in any case we update the authenciation token in the db
	# In case the user temporarily revoked access we will have
	# new tokens here.
	user.oauth_token = resp['oauth_token']
	user.oath_secret = resp['oauth_token_secret']

	session['user_id'] = user.id
	current_user = user
	login_user(user)
	db.session.commit()
	if first_login is True:
		send_analytics.delay("signup", userId=str(user.id))
		return redirect(url_for('find_contacts'))
	return redirect(redirect_url() or url_for('inbox'))


@app.route('/', methods = ["GET", "POST"])
@app.route('/index', methods = ["GET", "POST"])
def index():
	if g.user is None:
		return redirect(url_for('home'))
	return redirect(url_for('inbox'))

@app.route('/home')
def home():
	return render_template('home.html')

@app.route('/welcome', methods = ['GET', 'POST'])
@login_required
def welcome():
	user = g.user
	return render_template('welcome.html', title = "Welcome!")

@app.route('/inbox', methods = ["GET", "POST"])
@login_required
def inbox():
	user = g.user
	user_tags = user.tags_for_user().most_common(16)
	activity = user.user_activity()
	form = NewMessageForm()
	send_analytics.delay('pageview', userId=str(user.id), title='inbox')
	# cache_bookmarks.delay(user.id)
	if form.validate_on_submit():
			message = Message(title = form.message_title.data or 'check this out!',
								url = form.message_url.data,
								author = g.user,
								timestamp = datetime.utcnow())
			db.session.add(message)
			db.session.commit()
			session['message_id'] = message.id
			return redirect(url_for('recipients'))
	return render_template('inbox.html', user=user, user_tags = user_tags, title = "Inbox", form= form, activity = activity)

@app.route('/activity', methods=["GET", "POST"])
@login_required
def activity():
	user = g.user
	activity = user.user_activity()
	return render_template('activity.html', activity=activity)

# @app.route('/top', methods = ["GET", "POST"])
# @login_required
# def top():
# 	user = g.user
# 	inbox = user.ranked_inbox()
# 	return render_template('inbox.html', user=user, inbox = inbox, title = "Top")

@app.route('/contacts', methods = ["GET", "POST"])
@login_required
def contacts():
	user = g.user
	contacts = user.contacts
	return render_template('contacts.html', user = user, title = 'Contacts', contacts = contacts, inbox = inbox)

@app.route('/contacts/find', methods = ["GET", "POST"])
@login_required
def find_contacts():
	user = g.user
	resp = twitter.get('friends/ids.json', data = {"screen_name":str(user.username)}, token = user.oauth_token)
	not_contacts=[]
	not_users = []
	c = []
	error = None
	if resp.status == 200:
		ids = resp.data.get("ids")
		size = int(math.ceil(len(ids)/100.0))
		s = 0
		for i in range(size):
			_ids = ids[s:(s+100)]
			s += 100
			_r = twitter.post('users/lookup.json', data = {"user_id":_ids}, token = user.oauth_token)
			if _r.status == 200:
				friends = _r.data
				for f in friends:
					u = User.query.filter(User.username.ilike(str(f["screen_name"]))).first() #check if they are a user
					if u:
						if user.is_contact(u): #check if they're our friend
							c.append(f) # if not, let us add them
						else:
							not_contacts.append(f)
					else:
						not_users.append(f) #if they not a user let us invite them
			else:
				print _r.status
				error = "We're having trouble connecting to twitter. Try again later."
				return render_template('find_contacts.html', contacts = c, not_contacts=not_contacts, not_users = not_users, title = "Find Contacts", error=error)
	else:
		not_users, not_contacts, c = None, None, None
		error = "We're having trouble connecting to twitter right now. Try again later."
		print resp.status, resp.data

	return render_template('find_contacts.html', not_contacts=not_contacts, contacts = c, not_users = not_users, title = "Find Contacts", error=error, user = user)



@app.route('/user/<username>')
@login_required
def user(username):
	_user = User.query.filter(User.username.ilike(username)).first()
	history=None
	tags=None
	if _user:
		if _user.id == g.user.id:
			history = Message.query.filter(Message.author==g.user).order_by(Message.timestamp.desc()).limit(50)
			tags=_user.tags_for_user()
	return render_template('user.html', user = _user, tags = tags, title = 'Profile', inbox=inbox, history = history)

@app.route('/user/<username>/edit', methods = ["GET", "POST"])
@login_required
def edit_user(username):
	user = User.query.filter(User.username.ilike(username)).first()
	form = EmailForm()
	if form.validate_on_submit():
		user.email = form.email.data
		user.notifications_status = form.notifications_status.data
		db.session.add(user)
		db.session.commit()
		return redirect(url_for('user', username = username))
	return render_template('edit_user.html',form = form, user = user, title = user.username + " - edit")


@app.route('/settings', methods = ["GET", "POST"])
@login_required
def settings():
	user = g.user
	return render_template('settings.html', title = 'Settings', inbox=inbox)


@app.route('/compose', methods = ["GET", "POST"])
@login_required
def compose():
	user = g.user
	inbox = user.inbox()
	form = NewMessageForm()
	if form.validate_on_submit():
		message = Message(title = form.message_title.data or 'check this out!',
							url = form.message_url.data,
							author = g.user,
							timestamp = datetime.utcnow())
		db.session.add(message)
		db.session.commit()
		cache_url.delay(message.url)
		session['message_id'] = message.id
		return redirect(url_for('recipients'))

	return render_template('compose.html', form=form, title = "Compose", inbox =inbox)


@app.route('/recipients', methods = ["GET", "POST"])
@login_required
def recipients():
	user = g.user
	form = RecipientsForm()

	form.recipients.choices = [(contact.id, contact.username) for contact in user.contacts]

	message_id = session['message_id']
	message = Message.query.get(message_id)

	if request.method == 'POST':
		recipients = form.recipients.data
		if form.validate_on_submit():
			for recipient_id in recipients:
				message.add_recipient(recipient_id)
				message.send_message(recipient_id)
				send_analytics.delay('message sent', fromUser={"userId":str(g.user.id)}, toUser={"userId":str(recipient_id)})
				print 'sending email...'
				if recipient_id!= g.user.id:
					send_new_msg_email.delay(g.user.id, recipient_id, message.id)
			message.deliver_message()
			db.session.commit()
			session.pop('message_id', None)
			flash('Message Sent!')
			return redirect(url_for('index'))

		else:
			flash(form.errors)

	return render_template('selectrecipient.html', user = user, title = "Recipients", message = message, form = form)

@app.route('/bookmarks', methods = 	["GET", "POST"])
@app.route('/bookmarks/<int:page>', methods = ["GET", "POST"])
@login_required
def bookmarks(page=1):
	user = g.user
	key = 'bookmarks:%s:%s' % (user.id, page)
	# if bm.get(key):
	# 	cache_bookmarks.delay(user.id, page=page+1)
	# 	return bm.get(key)
	# else:
	b = user.bookmarks().paginate(page,12,False)
	user_tags = user.tags_for_user().most_common(20)
	send_analytics.delay("pageview", title="bookmarks", page=page)
	# bm.set(key, bookmarks, 600)
	return render_template('bookmarks.html', user = user, bookmarks = b, user_tags = user_tags, title = "Bookmarks")

@app.route('/follow/<username>')
@login_required
def follow(username):
	user = User.query.filter(User.username.ilike(username)).first()
	if user is None:
		flash('User %s not found.' % username)
		return redirect(redirect_url())
	if user == g.user:
		flash('You can\'t follow yourself!')
		return redirect(redirect_url())
	u = g.user.add_contact(user)
	if u is None:
		flash('Cannot follow ' + nickname + '.')
		return redirect(redirect_url())
	db.session.add(u)
	db.session.commit()
	send_followed_email.delay(g.user.id, user.id)
	send_analytics.delay("follow", follower={"userId":str(g.user.id)}, followed={"userId":str(user.id)})
	flash('You are now following ' + username + '!')
	return redirect(redirect_url())

@app.route('/unfollow/<username>')
@login_required
def unfollow(username):
	user = User.query.filter(User.username.ilike(username)).first()
	if user is None:
		flash('User %s not found.' % username)
		return redirect(redirect_url())
	if user == g.user:
		flash('You can\'t unfollow yourself!')
		return redirect(redirect_url())
	u = g.user.remove_contact(user)
	if u is None:
		flash('Cannot unfollow ' + nickname + '.')
		return redirect(redirect_url())
	db.session.add(u)
	db.session.commit()
	send_analytics.delay("follow", unfollower={"userId":str(g.user.id)}, unfollowed={"userId":str(user.id)})
	flash('You have stopped following ' + username + '.')
	return redirect(redirect_url())

@app.route('/bookmark/<message_id>', methods = ["GET", "POST"])
@login_required
def bookmark(message_id):
	user = g.user
	message = UserMessage.query.filter(UserMessage.message_id == message_id).filter(UserMessage.user_id == user.id).one()
	form = TagForm()

	if message is None:
		flash('Message not found.')
		return redirect(url_for('index'))

	m = user.bookmark_message(message_id)
	author_id = message.message.author.id
	send_analytics.delay("message bookmark", fromUser={"userId":str(author_id)}, toUser={"userId":str(g.user.id)}, messageId=str(message_id))
	if m is None:
		flash('Could not bookmark message')
		return redirect(url_for('index'))

	if form.validate_on_submit():
		#form data will be in format 'list, of, tags' we add a comma to the end so we can add more tags later
		tags = form.tags.data + ','
		# we can use the += operator because there will at least be an empty string. convert input to lowercase.
		message.tags += tags.lower()
		if g.user.id != message.message.author.id:
			user.create_activity(message.message.author.id, 'bookmarked', message.message.id)
		db.session.add(message, user)
		db.session.commit()
		# cache_bookmarks.delay(user.id)
		flash("tags updated")
		send_analytics.delay("bookmark tag", userId=str(g.user.id), tags=message.usermessage_tags())
		return redirect(redirect_url())
	else:
		flash(form.errors)

		return render_template("bookmark.html", message = message, user = user, form = form, title = "Edit Bookmark")


@app.route('/dismiss/<message_id>')
@login_required
def dismiss(message_id):
	message = UserMessage.query.filter(UserMessage.message_id == message_id)
	user = g.user
	if message is None:
		flash('Message not found.')
		return redirect(url_for('index'))
	m = user.dismiss_message(message_id)
	if m is None:
		flash('Could not dismiss message')
		return redirect(url_for('index'))
	db.session.add(user)
	db.session.commit()
	# cache_bookmarks.delay(user.id)
	send_analytics.delay("message dismiss", messageId = str(message_id), userId=str(user.id))
	flash('Message dismissed')
	return redirect(redirect_url())


@app.route('/quickshare', methods = ["GET", "POST"])
@login_required
def quickshare():
	user = g.user
	quickshare = "Sent via quickshare"
	form = RecipientsForm()

	form.recipients.choices = [(contact.id, contact.username) for contact in user.contacts]

	message = Message(title = quickshare, url = request.args.get('url'), author = g.user, timestamp = datetime.utcnow())
	cache_url.delay(message.url)
	if request.method == 'POST':
		if form.validate_on_submit():
			recipients = form.recipients.data
			for recipient_id in recipients:
				message.add_recipient(recipient_id)
				message.send_message(recipient_id)
				send_analytics.delay("message sent", fromUser={"userId":str(g.user.id)}, toUser={"userId":str(recipient_id)})
				if recipient_id!= g.user.id:
					send_new_msg_email.delay(str(g.user.id), str(recipient_id), str(message.id))
					flash('Message Sent!')
			message.deliver_message()
			db.session.commit()
			send_analytics.delay("quickshare", userId=str(user.id))
			return redirect(request.args.get('url'))

		else:
			flash(form.errors)

	return render_template('selectrecipient.html', user = user, title = "Recipients", message = message, form = form)



@app.route('/share/<message_id>', methods = ["GET", "POST"])
@login_required
def share(message_id):
	#user and original message
	user = g.user
	message = Message.query.get(message_id)
	inbox = user.inbox()


	#select recipients
	form = RecipientsForm()
	form.recipients.choices = [(contact.id, contact.username) for contact in user.contacts]

	#if the form was submitted
	if request.method == 'POST':
		recipients = form.recipients.data
		if form.validate_on_submit():
			#create a new message using the parent message as the paramas
			new_message = Message(title = message.title,
			url = message.url,
			author = g.user,
			timestamp = datetime.utcnow())
			db.session.add(new_message)
			db.session.commit()

			#append the new recipients
			for recipient_id in recipients:
				new_message.add_recipient(recipient_id)
				new_message.send_message(recipient_id)
				send_analytics.delay("message sent", fromUser={"userId":str(user.id)}, toUser={"userId":str(recipient_id)})
				send_analytics.delay("message sent shared", fromUser={"userId":str(user.id)}, toUser={"userId":str(recipient_id)})
				if recipient_id!=g.user.id:
					send_new_msg_email.delay(g.user.id, recipient_id, message.id)

			#deliver message
			new_message.deliver_message()
			if g.user.id != message.author.id:
				user.create_activity(owner_id = message.author.id, action='reshared', message_id = message.id)
			# message.incr_pts(points=2)
			# new_message.incr_pts(points=2)
			db.session.add(new_message)
			db.session.commit()
			send_analytics.delay("message shared", userId=str(user.id))
			flash('Message Shared!')
			return redirect(redirect_url())

		else:
			flash(form.errors)

	return render_template('selectrecipient.html', user = user, title = "Recipients", message = message, form = form)


@app.route('/tag/<name>', methods = ["GET", "POST"])
@app.route('/tag/<name>/<int:page>', methods = ["GET", "POST"])
@login_required
def tag(name, page = 1):
	user = g.user
	user_tags=dict(user.tags_for_user())
	tag_name = urllib.unquote(name)
	bookmarks = user.get_bookmarks_with_tag(tag_name)
	tag_count = bookmarks.count()
	bookmarks = bookmarks.paginate(page,12,False)
	send_analytics.delay("pageview", userId=str(user.id), title="tag", page=page)
	return render_template('tag.html', user = user, title = "#" + name, bookmarks = bookmarks, name = name, tag_count=tag_count)

@app.route('/tags', methods = ["GET", "POST"])
@login_required
def tags():
	user = g.user
	user_tags = dict(user.tags_for_user())
	send_analytics.delay("pageview", userId=str(user.id), title="tags")
	return render_template('tags.html', user = user, title = 'Tags', user_tags = user_tags)



def redirect_url(default='index'):
	return request.args.get('next') or request.referrer or url_for(request.referrer) or url_for(default)

@app.route('/reader', methods = ["GET", "POST"])
@app.route('/reader/<int:page>', methods = ["GET", "POST"])
@login_required
def reader(page = 1):
	user = g.user
	inbox = user.inbox().paginate(page,1,False)
	send_analytics.delay("pageview", userId=str(user.id), title="reader", page=page)
	return render_template('reader.html', user = user, title = 'Reader', inbox = inbox)


# @app.route('/message/<message_id>')
# @login_required
# def message(message_id):
# 	user = g.user
# 	m = Message.query.get(message_id)
# 	comments = message.message_comments.filter_by(Comment.commenter == g.user).order_by(Comment.id.desc()).all()
# 	# Should be able to see all of your own comments on a message
# 	# All comments in reply to your own comments
# 	return render_template("message.html", message = m)

@app.route('/message/reader/<message_id>', methods = ["GET", "POST"])
@login_required
def message_reader(message_id):
	user = g.user
	m = Message.query.get(message_id)
	send_analytics.delay("pageview", userId=str(user.id), title="message reader", messageId=str(message_id))
	return render_template('message_reader.html', user = user, title = 'Reader', message = m)


@app.route("/explore", methods = ["GET", "POST"] )
def explore():
	bot = User.query.filter(User.username.ilike('zippbot')).first()
	m = UserMessage.query.filter(UserMessage.user_id==bot.id).order_by(UserMessage.message_id.desc()).limit(12).all()
	items = []
	for i in m:
		item = {}
		item["id"] = i.message_id
		if bm.get(str(i.message.url)):
			item["content"] = bm.get(str(i.message.url))
			items.append(item)
		else:
			item["content"] = i.message.render_url()
			bm.set(str(i.message.url), item["content"], 172000)
			items.append(item)
	return render_template('explore.html', title = 'Explore', items = items)

@app.route('/history', methods=["GET", "POST"])
@login_required
def history():
	user =g.user
	history = Message.query.filter(Message.author==user).order_by(Message.timestamp.desc()).limit(50)
	return render_template("history.html", history=history)

@app.route('/collections')
def collection_home():
	user = g.user
	return render_template('collection_home.html')

@app.route('/collection/<str:unique_id>')
def collection(unique_id):
	uid = unique_id.lower()
	collection = Collection.query.filter(Collection.unique_id == uid).first()
	return render_template('collection.html', collection = collection)

@app.route('/user/collections')
@app.login_required
def user_collections():
	user = g.user
	user_collections = Collection.query.filter(Collection.creator.id == user.id).order_by(Collection.timestamp.desc()).limit(8)
	return render_template('user_collections.html', user = user, user_collections = user_collections)

#start of api routes---------------------------------------------------------#

@app.route('/api/1/heartbeat', methods = ["GET", "POST"])
def api_heartbeat():
	data = {"ok": True}
	return jsonify(data)

@app.route('/api/1/user')
@login_required
def api_user():
	return jsonify(username = g.user.username, id = g.user.id, tags = dict(g.user.tags_for_user()))

@app.route('/api/1/user/inbox', methods = ["GET"])
@login_required
def api_user_inbox():
	offset = request.args.get('offset')
	inbox_start = time.time()
	inbox = g.user.inbox()
	inbox_end = time.time()
	inbox_done = inbox_end - inbox_start
	print "inbox done in" , inbox_done
	if offset:
		offset = int(offset)
		inbox = inbox.from_self().offset(offset).limit(6)
		load_next.delay(int(g.user.id), offset=(offset+6))
	else:
		inbox = inbox.limit(6)
		load_next.delay(int(g.user.id))
	data = []
	for item in inbox.all():
		msg_start = time.time()
		message = {}
		message['id'] = item.message_id
		message['note']=item.message.title
		message['from_user']=item.message.author.username
		message['user_profile_img']= item.message.author.get_profile_img_url()
		print message['user_profile_img']
		message['timedelta']=item.message.format_timestamp()
		url = item.message.url
		url = url.encode('utf-8')
		if bm.get(url):
			message['content']= bm.get(url)
			msg_end = time.time()
			print "content from cache in ", msg_end - msg_start
		else:
			content = item.message.render_url()
			msg_end = time.time()
			print "cache miss, content rendered in ", msg_end - msg_start
			message['content'] = content.encode('utf-8')
			bm.set(url, message['content'], 172800)
			msg_cached = time.time()
			print "message cached in ", msg_end-msg_cached
		data.append(message)
	return jsonify(data)

@app.route('/api/1/user/bookmarks', methods = ["GET"])
@login_required
def api_user_bookmarks():
	bookmarks = g.user.bookmarks()
	data = []
	for item in bookmarks.all():
		message = {}
		message['id']=item.message_id
		message['note']=item.message.title
		message['from_user']=item.message.author.username
		message['url']=item.message.url
		message['tags'] = item.usermessage_tags()
		resp = item.message.request_url()
		if resp:
			message['title'] = resp["title"]
			message['description'] = resp["description"]
		data.append(message)
	return jsonify(data)


@app.route('/api/1/bookmark/<int:message_id>', methods = ["GET", "POST"])
@login_required
def api_bookmark_message(message_id):
	user = g.user

	message = UserMessage.query.filter(UserMessage.message_id == message_id)
	if message is None:
		return jsonify(error = 'Message not found.')
	m = user.bookmark_message(message_id)
	if m is None:
		return jsonify(error = 'Message could not be bookmarked')
	db.session.add(user)
	db.session.commit()
	return jsonify(ok = True, msg = 'Message' + str(message_id) + ' bookmarked')

@app.route('/api/1/dismiss/<int:message_id>', methods = ["GET", "POST"])
@login_required
def api_dismiss_message(message_id):
	user = g.user
	message = UserMessage.query.filter(UserMessage.message_id == message_id)
	if message is None:
		return jsonify(error = 'Message not found.')
	m = user.dismiss_message(message_id)
	if m is None:
	    return jsonify(error = 'Message could not be dismissed')
	db.session.add(user)
	db.session.commit()
	send_analytics.delay("message dismiss", userId=str(user.id), messageId=str(message_id))
	return jsonify(ok = True, msg = 'Message' + str(message_id) + ' dismissed')

@app.route('/api/1/m/user/inbox', methods = ["GET", "POST"])
@login_required
def m_api_inbox():
	user = g.user
	inbox = user.inbox()
	data = []
	for message in inbox.all():
		m = {'id': int(message.message.id), 'note': message.message.title, 'author':message.message.author.username, 'url':message.message.url}
		c = message.message.get_content()
		if c:
			if "title" in c:
				m['title']=c['title']
			else:
				m["title"]=''
			if "description" in c:
				m["description"] = c["description"]
			else:
				m["description"] = 	None
			if 'url' in c.get('media',{}):
				m["img"] = c['media']['url']
			else:
				m['img'] = None
		else:
			m['title']=None
			m['description']=None
			m['img']=None
		data.append(m)
		print jsonify(data)
	return jsonify(data)


@app.route('/api/1/collection/create', methods=["POST"])
def api_create_collection():
	data = request.data.json()
	collection = Collection()
	for item in data["items"]:
		collection.collection_items.append(CollectionItem(parent=self, content=str(item)))
	collection.is_public = data["is_public"]
	db.session.add(collection)
	db.session.commmit()
	return jsonify(ok=True)

# @app.route('api/1/m/login', methods = ["GET", "POST"])
# def m_api_login():
# 	return redirect(url_for())


#
#
# @app.route('api/1/message/create', methods = ["GET", "POST"])
# @app.login_required
# def api_message_create():
# 	data = request.get_json()
# 	data = dict(data)
# 	title = data["title"]
# 	url = data["url"]
# 	timestamp = datetime.utcnow()
# 	message = Message( 	title = title,
# 						url = url,
# 						author = g.user,
# 						timestamp = timestamp)
# 	db.session.add(message)
# 	db.session.commit()
# 	recipients = [int(i) for i in data['recipient_ids']]
# 	for r in recipients:
# 		message.add_recipient(r)
# 		message.send_message(r)
# 	message.deliver_message()
# 	db.session.commit()
# 	return jsonify(ok=True)




# @app.route('/api/1/activity/messages')
# @login_required
# def api_activity_create():
# 	data = request.get_json()
# 	subject_id = data["owner_id"]
# 	owner_id = data["owner_id"]
# 	action = data['action']
# 	msg_id = data['message_id']
# 	message = Message.query.get(msg_id)
# 	owner2_id = message.author.id
# 	owner_activity = MessageActivity(	owner_id = owner_id,
# 										subject_id = subject_id,
# 										action = action,
# 										message_id = msg_id )
# 	db.session.add(owner_activity)
#
# 	if owner_id != owner2_id:
# 		owner2_activity = MessageActivity(	owner_id = onwer2_id,
# 											subject_id = subject_id,
# 											action = action,
# 											message_id = msg_id )
# 		db.session.add(owner2_activity)
#
# 	db.session.commit()
# 	return jsonify(ok="true")

@app.route('/api/1/activity/create', methods=["GET","POST"])
@login_required
def api_user_activity():
	user = g.user
	data = request.get_json()
	action = data["action"]
	message_id = data["message_id"]
	m = Message.query.get(message_id)
	owner_id = m.author.id
	u = None
	if owner_id != user.id:
		u = user.create_activity(owner_id = owner_id, action=action, message_id= message_id)
		if u[1]:
			activity = u[1].id
			send_activity_email.delay(activity)
			send_analytics.delay("reaction", fromUser={"userId":str(user.id)}, toUser={"userId":str(owner_id)}, messageId=str(message_id), reactionName=action)
			# m.incr_pts()
		else:
			return jsonify(error="action could not be performed. You might have done this already.")
	return jsonify(ok=True)


#Mobile routes
@app.route('/m/user/inbox')
@login_required
def mobile_inbox():
	user = g.user
	return render_template("mobile_inbox.html")

@app.route('/m/user/bookmarks', methods = 	["GET", "POST"])
@app.route('/m/user/bookmarks/<int:page>', methods = ["GET", "POST"])
@login_required
def mobile_bookmarks(page=1):
	user = g.user
	key = 'bookmarks:%s:%s' % (user.id, page)
	#TODO
	# if bm.get(key):
	# 	cache_bookmarks.delay(user.id, page=page+1)
	# 	return bm.get(key)
	# else:
	b = user.bookmarks().paginate(page,12,False)
	send_analytics.delay("pageview", title="bookmarks", page=page)
	# bm.set(key, bookmarks, 600)
	return render_template('mobile_bookmarks.html', user = user, bookmarks = b, title = "Bookmarks")




#*********----------------------ASYNC TASKS-----------------------********
@celery.task
def cache_url(url):
	url = url.encode('utf-8')
	if bm.get(url):
		return True
	else:
		content = get_url_content(url)
		content = content.encode('utf-8')
		print 'content cached via thread'
		return bm.set(url, content, 172800)

@celery.task
def load_next(user_id, offset=6):
	#routine to preload the next items in a user inbox
	with app.app_context():
		user = User.query.get(user_id)
		next_items = user.inbox().from_self().offset(offset).limit(6)
		for item in next_items.all():
			msg_start = time.time()
			message = {}
			message['id'] = item.message_id
			message['note']=item.message.title
			message['from_user']=item.message.author.username
			message['timedelta']=item.message.format_timestamp()
			url = item.message.url
			url = url.encode('utf-8')
			if bm.get(url):
				message['content']= bm.get(url)
				msg_end = time.time()
				print "content from cache in ", msg_end - msg_start
			else:
				content = item.message.render_url()
				msg_end = time.time()
				print "cache miss, content rendered in ", msg_end - msg_start
				message['content'] = content.encode('utf-8')
				bm.set(url, message['content'], 172800)
				msg_cached = time.time()
				print "message cached in ", msg_end-msg_cached
	print 'Next 6 items cached'
	return True

@celery.task
def cache_bookmarks(user_id, page=1):
	with app.app_context():
		s = time.time()
		g.user = User.query.get(user_id)
		user = g.user
		b = user.bookmarks().paginate(page,12,False)
		user_tags = user.tags_for_user().most_common(20)
		bookmarks = render_template('bookmarks.html', user = user, bookmarks = b, user_tags = user_tags, title = "Bookmarks")

		# key naming convention is object:id:field
		# in this case bookmarks:user_id:page
		key='bookmarks:%s:%s' % (user.id, page)
		e = time.time()
		td = s-e
		print 'Bookmarks page %s cached in %s seconds' % (page, td)
		return bm.set(key, bookmarks, 600)

@celery.task
def send_reminder_email(recipient_id, message_id):
	with app.app_context():
		recipient = User.query.get(recipient_id)
		message = message.query.get(message_id)
		if recipient.email:
			r_email = str(recipient.email)
			if recipient.notifications_status == True:
				html = render_template('reminder_email.html', recipient = recipient.username, message = message)
				resp = requests.post(	mailgun_api,
										auth = ("api",mailgun_auth),
										data = {"from":"Zipp - Reminder <info@zippmsg.com>",
												"to":r_email,
												"subject":"Scheduled Reminder",
												"html":html})
				print resp
				return resp
	return False

@celery.task
def send_followed_email(sender_id, recipient_id):
	with app.app_context():
		print "email task added to queue "
		recipient = User.query.get(recipient_id)
		sender = User.query.get(sender_id)
		r_email  = recipient.email
		if r_email:
			if recipient.notifications_status == True:
				html = render_template('follow_email.html', sender = sender.username, recipient = recipient.username)
				r_email = r_email.encode('utf-8')
				r_email = str(r_email)
				resp = requests.post( 	mailgun_api,
					auth = ("api",mailgun_auth),
					data = {"from":"Zipp - Notifications <info@zippmsg.com>",
							"to":r_email,
							"subject":"New Follower!",
							"html":html})
				print resp
				return resp
	return False

@celery.task
def send_activity_email(activity_id):
	if activity_id:
		with app.app_context():
			activity = Activity.query.filter(Activity.id==activity_id)
			recipient = activity.owner.id
			sender = activity.subject.id
			r_email  = recipient.email
			if r_email:
				if recipient.notifications_status == True:
					r_email = r_email.encode('utf-8')
					r_email = str(r_email)
					html = render_template('activity_email.html', sender = sender.username, recipient = recipient.username, action = activity.action)
					resp = requests.post( 	mailgun_api,
						auth = ("api",mailgun_auth),
						data = {"from":"Zipp - Notifications <info@zippmsg.com>",
						"to":r_email,
						"subject":"New activity on your message!",
						"html":html})
					print  'activity email sent'
					return resp
	else:
		return False

@celery.task
def send_new_msg_email(sender_id, recipient_id, message_id):
	with app.app_context():
		print 'task added to queue'
		sender = User.query.get(sender_id)
		recipient = User.query.get(recipient_id)
		message = Message.query.get(message_id)
		r_email = recipient.email
		url = message.url
		url = url.encode('utf-8')
		content = bm.get(url) or message.render_url()
		if r_email:
			if recipient.notifications_status == True:
				r_email = r_email.encode('utf-8')
				html = render_template('new_message_email.html', sender = sender.username, recipient = recipient.username, note = message.title, content = content, timedelta = message.format_timestamp())
				resp = requests.post( 	mailgun_api,
									auth = ("api",mailgun_auth),
									data = {"from":"Zipp - Notifications <info@zippmsg.com>",
											"to":r_email,
											"subject":"New Message!",
											"html":html})
				print 'email sent', resp
				return resp
	return False

@celery.task
def send_analytics(collection, **kwargs):
	for kw in kwargs:
		event = {kw:kwargs[kw]}
	resp = keen.add_event(collection, event)
	if resp == 200 or 201:
		print "event successfully created"
		return True
	else:
		print resp
		return False



#*****--------------------------HELPER ROUTES------------------------******
@app.route('/favicon.ico', methods = ["GET", "POST"])
def favicon():
	return send_from_directory(os.path.join(app.root_path, 'static'), 'favicon.ico')

@app.route('/styles.css')
def styles():
	return send_from_directory(os.path.join(app.root_path, 'static/css'), "zipp-styles.css")

@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
	if g.user != User.query.get(1):
		return 403
	users = User.query.all()
	n_users = len(users)
	messages_sent = len(Message.query.all())
	activities = len(Activity.query.all())
	send_analytics.delay("test", test="test")
	return render_template('dashboard.html', n_users=n_users, messages_sent=messages_sent, activities = activities, users = users)


@app.route('/438498thv893h4jnksxcv9n34ukkjdknuodoh8rg9', methods = ["GET", "POST"])
def demo():
	g.user = User.query.filter(User.username.ilike("zippdemo")).first()
	user = g.user
	login_user(user)
	user_tags = user.tags_for_user().most_common(20)
	activity = user.user_activity()
	form = NewMessageForm()
	send_analytics.delay('pageview', userId=str(user.id), title='demoInbox')
	# cache_bookmarks.delay(user.id)
	if form.validate_on_submit():
			message = Message(title = form.message_title.data or 'check this out!',
								url = form.message_url.data,
								author = g.user,
								timestamp = datetime.utcnow())
			db.session.add(message)
			db.session.commit()
			session['message_id'] = message.id
			return redirect(url_for('recipients'))
	return render_template('inbox.html', user=user, user_tags = user_tags, title = "Inbox", form= form, activity = activity)
