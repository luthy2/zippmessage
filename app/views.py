from flask import request, g, render_template, session, url_for, redirect, request, flash
from flask_login import login_user, logout_user, current_user, login_required
from app import app, db, lm, twitter
from forms import NewMessageForm, RecipientsForm, TagForm
from models import User, Message, UserMessage
from datetime import datetime
import urllib


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

        db.session.add(user)
        user.add_contact(user)

    # in any case we update the authenciation token in the db
    # In case the user temporarily revoked access we will have
    # new tokens here.
    user.oauth_token = resp['oauth_token']
    user.oath_secret = resp['oauth_token_secret']
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
	inbox = user.inbox()
	inbox_count = inbox.count()
	return render_template('welcome.html', title = "Welcome!", inbox_count=inbox_count)

@app.route('/inbox', methods = ["GET", "POST"])
@login_required
def inbox():
	user = g.user
	inbox = user.inbox()
	inbox_count = inbox.count()
	user_tags = user.tags_for_user()
	return render_template('inbox.html', user=user, inbox = inbox, user_tags = user_tags, title = "Inbox", inbox_count=inbox_count)

@app.route('/top', methods = ["GET", "POST"])
@login_required
def top():
	user = g.user
	inbox = user.inbox()
	inbox_count = inbox.count()
	return render_template('inbox.html', user=user, inbox = inbox, inbox_count=inbox_count, title = "Top")

@app.route('/contacts', methods = ["GET", "POST"])
@login_required
def contacts():
	user = g.user
	contacts = user.contacts
	inbox = user.inbox()
	inbox_count = inbox.count()
	return render_template('contacts.html', user = user, title = 'Contacts', contacts = contacts, inbox = inbox, inbox_count = inbox_count)

@app.route('/user/<username>')
@login_required
def user(username):
	_user = User.query.filter_by(username=username).first()
	tags = _user.tags_for_user()
	inbox = g.user.inbox()
	inbox_count = inbox.count()
	return render_template('user.html', user = _user, tags = tags, title = 'Profile', inbox=inbox, inbox_count=inbox_count)


@app.route('/settings', methods = ["GET", "POST"])
@login_required
def settings():
	user = g.user
	inbox=user.inbox()
	inbox_count = inbox.count()
	return render_template('settings.html', title = 'Settings', inbox=inbox, inbox_count = inbox_count)


@app.route('/compose', methods = ["GET", "POST"])
@login_required
def compose():
	user = g.user
	inbox = user.inbox()
	inbox_count=inbox.count()
	form = NewMessageForm()
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
	else:
		form.flash_errors()
	return render_template('compose.html', form=form, title = "Compose", inbox =inbox, inbox_count=inbox_count)


@app.route('/recipients', methods = ["GET", "POST"])
@login_required
def recipients():
	user = g.user
	form = RecipientsForm()
	inbox = user.inbox()
	inbox_count = inbox.count()

	form.recipients.choices = [(contact.id, contact.username) for contact in user.contacts]

	message_id = session['message_id']
	message = Message.query.get(message_id)

	if request.method == 'POST':
		recipients = form.recipients.data
		if form.validate_on_submit():
			for recipient in recipients:
				message.add_recipient(recipient)
				message.send_message(recipient)
			message.deliver_message()
			db.session.commit()
			session.pop('message_id', None)
			flash('Message Sent!')
			return redirect(url_for('index'))

		else:
			flash(form.errors)

	return render_template('selectrecipient.html', user = user, title = "Recipients", message = message, form = form, inbox_count = inbox_count)

@app.route('/bookmarks', methods = 	["GET", "POST"])
@login_required
def bookmarks():
	user = g.user
	bookmarks = user.bookmarks()
	user_tags = user.tags_for_user()
	inbox = user.inbox()
	inbox_count = inbox.count()
	return render_template('bookmarks.html', user = user, bookmarks = bookmarks, user_tags = user_tags, title = "Bookmarks", inbox_count=inbox_count)

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
	inbox = user.inbox()
	inbox_count = inbox.count()
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

		return render_template("bookmark.html", message = message, user = user, form = form, title = "Edit Bookmark", inbox_count=inbox_count)


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
	inbox = user.inbox()
	inbox_count = inbox.count()
	quickshare = "Sent by " + user.username +" via quickshare"
	form = RecipientsForm()

	form.recipients.choices = [(contact.id, contact.username) for contact in user.contacts]

	message = Message(title = quickshare, url = request.args.get('url'), author = g.user, timestamp = datetime.utcnow())

	if request.method == 'POST':
		recipients = form.recipients.data

		if form.validate_on_submit():
			db.session.add(message)
			for recipient in recipients:
				message.add_recipient(recipient)
				message.send_message(recipient)
				message.deliver_message()
				flash('Message Sent!')
				return redirect(request.args.get('url'))

		else:
			flash(form.errors)

	return render_template('selectrecipient.html', user = user, title = "Recipients", message = message, form = form, inbox_count=inbox_count)



@app.route('/share/<message_id>', methods = ["GET", "POST"])
@login_required
def share(message_id):
	#user and original message
	user = g.user
	message = UserMessage.query.filter(UserMessage.message_id == message_id)
	inbox = user.inbox()
	inbox_count = inbox.count()

	#select recipients
	form = RecipientsForm()
	form.recipients.choices = [(contact.id, contact.username) for contact in user.contacts]

	#if the form was submitted
	if request.method == 'POST':
		recipients = form.recipients.data
		if form.validate_on_submit():
			#create a new message using the parent message as the paramas
			new_message = Message(title = message.message.title,
			url = message.message.url,
			author = g.user,
			timestamp = datetime.utcnow())
			db.session.add(new_message)
			db.session.commit()

			#append the new recipients
			for recipient in recipients:
				new_message.add_recipient(recipient)
				new_message.send_message(recipient)

			#deliver message
			new_message.deliver_message()
			db.session.commit()
			flash('Message Shared!')
			return redirect(url_for(redirect_url()))

		else:
			flash(form.errors)

	return render_template('selectrecipient.html', user = user, title = "Recipients", message = message, form = form, inbox_count=inbox_count)


@app.route('/tag/<name>', methods = ["GET", "POST"])
@login_required
def tag(name):
	user = g.user
	tag_name = urllib.unquote(name)
	bookmarks = user.get_bookmarks_with_tag(tag_name)
	inbox = user.inbox()
	inbox_count = inbox.count()
	return render_template('tag.html', user = user, title = "#" + name, bookmarks = bookmarks, inbox_count=inbox_count, name = name)

@app.route('/tags', methods = ["GET", "POST"])
@login_required
def tags():
	user = g.user
	inbox_count = user.inbox().count()
	user_tags = user.tags_for_user()
	return render_template('tags.html', user = user, title = 'Tags', user_tags = user_tags, inbox_count = inbox_count)



def redirect_url(default='index'):
	return request.args.get('next') or request.referrer or default
