from flask import flash, g
from flask.ext.wtf import Form
from wtforms import StringField, SubmitField, SelectMultipleField, BooleanField, widgets
from wtforms.widgets import ListWidget
from wtforms.validators import DataRequired, Length, URL


class NewMessageForm(Form):
	message_title = StringField('title', validators=[DataRequired(), Length(min = 1, max = 100)])
	message_url = StringField('url', validators=[DataRequired(), URL(require_tld = False, message = 'Must contain a valid URL'), Length(min = 7, max = 300)])

	def flash_errors(form):
		for field, errors in form.errors.items():
			for error in errors:
				flash(u"Error in the %s field - %s" % (getattr(form, field).label.text,error))

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
	tags = StringField('title', validators = [Length(max=300)])
