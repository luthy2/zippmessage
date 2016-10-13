from flask import flash, g
from flask_wtf import Form
from wtforms import StringField, SubmitField, SelectMultipleField, BooleanField, widgets
from wtforms.widgets import ListWidget
from wtforms.validators import DataRequired, Length, URL, Email


class NewMessageForm(Form):
	message_title = StringField('title', validators=[Length(max = 300, message="The note is too long! Try Again")])
	message_url = StringField('url', validators=[DataRequired(), URL(require_tld = False, message = 'Must contain a valid URL'), Length(min = 7, max = 350)])
	#add bookmarked = True field


class MultiCheckboxField(SelectMultipleField):
    """
    A multiple-select, except displays a list of checkboxes.

    Iterating the field will produce subfields, allowing custom rendering of
    the enclosed checkbox fields.
    """
    widget = widgets.ListWidget(prefix_label=False)
    option_widget = widgets.CheckboxInput()

class RecipientsForm(Form):
	recipients = MultiCheckboxField("recipients", choices = [], coerce=int, validators=[DataRequired()])

class TagForm(Form):
	tags = StringField('title', validators = [Length(max=300, message="Too many tags! Sorry.")])

class EmailForm(Form):
	email = StringField('email', validators = [Email(message="Please enter a valid email")])
	notifications_status = BooleanField('notifications', default = 'checked')
