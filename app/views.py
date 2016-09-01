import os

from flask import request, g, render_template, render_template_string, session, url_for, redirect, flash, jsonify, send_from_directory, make_response
from flask_login import login_user, logout_user, current_user, login_required
from app import app, db, lm, twitter, bm, celery, mailgun_api, mailgun_auth
from forms import NewMessageForm, RecipientsForm, TagForm, EmailForm
from models import User, Message, UserMessage, get_url_content
from datetime import datetime
import urllib
import time
import requests

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
	if "twitter_token" in session:
		return session.get("twitter_token")
	else:
		if user is not None:
			return user.oauth_token, user.oauth_secret



@app.route('/login')
def login():
	"""Calling into authorize will cause the OpenID auth machinery to kick
    in.  When all worked out as expected, the remote application will
    redirect back to the callback URL provided.
    """
	return twitter.authorize(callback=url_for('oauth_authorized', next=request.args.get('next') or request.referrer or None))

@app.route('/logout')
def logout():
	logout_user()
	current_user = None
	session.pop('user_id', None)
	session.pop('user', None)
	session.pop('flashed_messages', None)
	flash('You were signed out')
	return redirect(url_for('index'))


@app.route('/oauth-authorized')
@twitter.authorized_handler
def oauth_authorized(resp):
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
    next_url = request.args.get('next') or url_for('index')
    if resp is None:
        flash(u'You denied the request to sign in.')
        return redirect(next_url)

    user = User.query.filter_by(username=resp['screen_name']).first()

    # user never signed on
    if user is None:
        user = User(username = resp['screen_name'], contacts=(), sent_messages=(), inbox_messages=())
		#**todo issue a user a new token for  mobile auth. **
        db.session.add(user)
        user.add_contact(user)

    # in any case we update the authenciation token in the db
    # In case the user temporarily revoked access we will have
    # new tokens here.
    user.oauth_token = resp['oauth_token']
    user.oath_secret = resp['oauth_token_secret']
	session['twitter_token'] = (resp["oauth_token"], resp['oauth_token_secret'])
    db.session.commit()

    session['user_id'] = user.id

    login_user(user)
    flash('You were signed in')

    return redirect(next_url or url_for('inbox'))


@app.route('/', methods = ["GET", "POST"])
@app.route('/index', methods = ["GET", "POST"])
def index():
	if g.user is None:
		return render_template('home.html')
	return redirect(url_for('inbox'))

@app.route('/welcome', methods = ['GET', 'POST'])
@login_required
def welcome():
	user = g.user
	return render_template('welcome.html', title = "Welcome!")

@app.route('/inbox', methods = ["GET", "POST"])
@app.route('/inbox/<int:page>', methods = ["GET", "POST"])
@login_required
def inbox(page=1):
	form = NewMessageForm()
	user = g.user
	user_tags = user.tags_for_user().most_common(20)
	if form.validate_on_submit():
			message = Message(title = form.message_title.data,
								url = form.message_url.data,
								author = g.user,
								timestamp = datetime.utcnow())
			db.session.add(message)
			db.session.commit()
			session['message_id'] = message.id
			flash('Choose Receipients')
			return redirect(url_for('recipients'))

	#activity = MessageActivity.query.filter_by(MessageActivity.owner_id == user.id)
	return render_template('inbox.html', user=user, user_tags = user_tags, title = "Inbox", form= form)


@app.route('/top', methods = ["GET", "POST"])
@login_required
def top():
	user = g.user
	inbox = user.inbox()
	return render_template('inbox.html', user=user, inbox = inbox, title = "Top")

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
	s = time.time()
	f = twitter.request('friends/ids.json', method= data ={'screen_name':str(user.username)})
	f = twitter.request('users', data = {'user_id':f['ids']})
	e = time.time()
	print "data from twitter in", s-e
	friends = [(i["name"], i['profile_image_url']) for i in f]
	for i in friends:
		if not User.query.filter(User.username.ilike(i[0])).first():
			friends.remove(i)
	return render_template('find_contacts.html', friends = friends)


@app.route('/user/<username>')
@login_required
def user(username):
	_user = User.query.filter(User.username.ilike(username)).first()
	tags = _user.tags_for_user().most_common(20)
	return render_template('user.html', user = _user, tags = tags, title = 'Profile', inbox=inbox)

@app.route('/user/<username>/edit', methods = ["GET", "POST"])
@login_required
def edit_user(username):
	user = User.query.filter(User.username.ilike(username)).first()
	form = EmailForm()
	if form.validate_on_submit():
		user.email = form.email.data
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
		message = Message(title = form.message_title.data,
							url = form.message_url.data,
							author = g.user,
							timestamp = datetime.utcnow())
		db.session.add(message)
		db.session.commit()
		cache_url.delay(message.url)
		session['message_id'] = message.id
		flash('Choose Receipients')
		return redirect(url_for('recipients'))
	else:
		form.flash_errors()
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
			for recipient in recipients:
				message.add_recipient(recipient)
				message.send_message(recipient)
				print 'sending email...'
				if recipient!= g.user.id:
					send_new_msg_email.delay(g.user.id, recipient, message.id)
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
	bookmarks = user.bookmarks().paginate(page,12,False)
	user_tags = user.tags_for_user().most_common(20)
	return render_template('bookmarks.html', user = user, bookmarks = bookmarks, user_tags = user_tags, title = "Bookmarks")

@app.route('/follow/<username>')
@login_required
def follow(username):
	user = User.query.filter_by(username=username).first()
	if user is None:
		flash('User %s not found.' % username)
		return redirect(url_for('index'))
	if user == g.user:
		flash('You can\'t follow yourself!')
		return redirect(url_for('user', username=username))
	u = g.user.add_contact(user)
	if u is None:
		flash('Cannot follow ' + nickname + '.')
		return redirect(url_for('user', username=username))
	db.session.add(u)
	db.session.commit()
	send_followed_email.delay(g.user.id, user.id)
	flash('You are now following ' + username + '!')
	return redirect(url_for('user', username=username))

@app.route('/unfollow/<username>')
@login_required
def unfollow(username):
    user = User.query.filter_by(username=username).first()
    if user is None:
        flash('User %s not found.' % username)
        return redirect(url_for('index'))
    if user == g.user:
        flash('You can\'t unfollow yourself!')
        return redirect(url_for('user', username))
    u = g.user.remove_contact(user)
    if u is None:
        flash('Cannot unfollow ' + nickname + '.')
        return redirect(url_for('user', username=username))
    db.session.add(u)
    db.session.commit()
    flash('You have stopped following ' + username + '.')
    return redirect(url_for('user', username=username))

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
	if m is None:
		flash('Could not bookmark message')
		return redirect(url_for('index'))

	if form.validate_on_submit():
		#form data will be in format 'list, of, tags' we add a comma to the end so we can add more tags later
		tags = form.tags.data + ','
		# we can use the += operator because there will at least be an empty string. convert input to lowercase.
		message.tags += tags.lower()
		db.session.add(message, user)
		db.session.commit()
		flash("tags updated")
		return redirect(url_for(redirect_url()))
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
    flash('Message dismissed')
    return redirect(url_for(redirect_url()))


@app.route('/quickshare', methods = ["GET", "POST"])
@login_required
def quickshare():
	user = g.user
	quickshare = "Sent via quickshare"
	form = RecipientsForm()

	form.recipients.choices = [(contact.id, contact.username) for contact in user.contacts]

	message = Message(title = quickshare, url = request.args.get('url'), author = g.user, timestamp = datetime.utcnow())
	db.session.add(message)
	db.session.commit()
	cache_url.delay(message.url)
	if request.method == 'POST':
		recipients = form.recipients.data
		if form.validate_on_submit():
			db.session.add(message)
			for recipient in recipients:
				message.add_recipient(recipient)
				message.send_message(recipient)
				message.deliver_message()
				if recipient!= g.user.id:
					send_new_msg_email.delay(g.user.id, recipient, message.id)
				flash('Message Sent!')
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
			for recipient in recipients:
				new_message.add_recipient(recipient)
				new_message.send_message(recipient)
				if recipient!=g.user.id:
					send_new_msg_email.delay(g.user.id, recipient, message.id)

			#deliver message
			new_message.deliver_message()
			db.session.commit()
			flash('Message Shared!')
			return redirect(url_for(redirect_url()))

		else:
			flash(form.errors)

	return render_template('selectrecipient.html', user = user, title = "Recipients", message = message, form = form)


@app.route('/tag/<name>', methods = ["GET", "POST"])
@app.route('/tag/<name>/<int:page>', methods = ["GET", "POST"])
@login_required
def tag(name, page = 1):
	user = g.user
	tag_name = urllib.unquote(name)
	bookmarks = user.get_bookmarks_with_tag(tag_name).paginate(page,12,False)
	return render_template('tag.html', user = user, title = "#" + name, bookmarks = bookmarks, name = name)

@app.route('/tags', methods = ["GET", "POST"])
@login_required
def tags():
	user = g.user
	user_tags = dict(user.tags_for_user())
	return render_template('tags.html', user = user, title = 'Tags', user_tags = user_tags)



def redirect_url(default='index'):
	return request.args.get('next') or request.referrer or url_for(request.referrer) or url_for(default)

@app.route('/reader', methods = ["GET", "POST"])
@app.route('/reader/<int:page>', methods = ["GET", "POST"])
@login_required
def reader(page = 1):
	user = g.user
	inbox = user.inbox().paginate(page,1,False)
	return render_template('reader.html', user = user, title = 'Reader', inbox = inbox)


#start of api routes#

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
	else:
		inbox = inbox.limit(6)
	data = []
	for item in inbox.all():
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
	return jsonify(ok = True, msg = 'Message' + str(message_id) + ' dismissed')

@app.route('/api/1/m/user/inbox', methods = ["GET", "POST"])
@login_required
def m_api_inbox():
	user = g.user
	inbox = user.inbox()
	data = []
	for message in inbox.all():
		m = {'id': str(message.message.id), 'note': message.message.title, 'author':message.message.author.username, 'url':message.message.url}
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
	return jsonify(data)



#
#
# @app.route('api/1/message/create', methods = ["GET", "POST"])
# @app.login_required
# def compose_digest():
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

# @app.route('api/1/user/activity')
# @login_required
# def api_user_activity():
# 	user = g.user
# 	activity = MessageActivity.query.filter_by(MessageActivity.owner_id == user.id)
# 	return jsonify(activity_feed)

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

# @celery.task
# def send_analytics():
# 	params = {'v':1,'tid':'UA-82204986-1','cid':'','t':''}
# 	request.post('http://www.google-analytics.com',params = params)

@celery.task
def send_followed_email(sender_id, recipient_id):
	with app.app_context():
		print "email task added to queue "
		recipient = User.query.get(reicipient_id)
		sender = User.query.get(sender_id)
		r_email  = recipient.email
		r_email = r_email.encode('utf-8')
		html = render_template('follow_email.html', sender = sender.username, recipient = recipient.username)
		if recipient_email:
			user_email = str(user_email)
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
def send_new_msg_email(sender_id, recipient_id, message_id):
	with app.app_context():
		print 'task added to queue'
		sender = User.query.get(sender_id)
		recipient = User.query.get(recipient_id)
		message = Message.query.get(message_id)
		r_email = recipient.email
		r_email = r_email.encode('utf-8')
		url = message.url
		url = url.encode('utf-8')
		content = bm.get(url) or message.render_url()
		html = render_template('new_message_email.html', sender = sender.username, recipient = recipient.username, note = message.title, content = content, timedelta = message.format_timestamp())
		if r_email:
			resp = requests.post( 	mailgun_api,
								auth = ("api",mailgun_auth),
								data = {"from":"Zipp - Notifications <info@zippmsg.com>",
										"to":r_email,
										"subject":"New Message!",
										"html":html})
			print resp
			return resp
	return False



@app.route('/favicon.ico', methods = ["GET", "POST"])
def favicon():
	return send_from_directory(os.path.join(app.root_path, 'static'), 'favicon.ico')



@app.route('/admin/dashboard')
@login_required
def admind_dashboard():
	if g.user != User.query.get(1):
		return abort(), 403
	n_users = len(User.query.all())
	messages_sent = len(Message.query.all())
	return render_template('dashboard.html', n_users=n_users, messages_sent=messages_sent)
