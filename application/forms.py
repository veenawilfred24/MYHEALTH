from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, PasswordField, SubmitField, FileField
from wtforms.validators import DataRequired, Length, EqualTo, ValidationError
from application.models import is_valid_patient_username

class PatientLoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

class PatientSignupForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=4, max=25)])
    email = StringField('Email', validators=[DataRequired()])
    name = StringField('Full Name', validators=[DataRequired()])
    mobile_no = StringField('Mobile Number', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Sign Up')

class DoctorLoginForm(FlaskForm):
    d_username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

class DoctorSignupForm(FlaskForm):
    d_username = StringField('Username', validators=[DataRequired(), Length(min=4, max=25)])
    email = StringField('Email', validators=[DataRequired()])
    name = StringField('Full Name', validators=[DataRequired()])
    mobile_no = StringField('Mobile Number', validators=[DataRequired()])
    license_no = StringField('License Number', validators=[DataRequired()])
    hospital_name = StringField('Hospital Name', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Sign Up')

class SelectUserForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    submit = SubmitField('Select User')

class AddPrescriptionForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    hospital_name = StringField('Hospital Name', validators=[DataRequired()])
    medication_name = StringField('Medication Name', validators=[DataRequired()])
    dosage = StringField('Dosage', validators=[DataRequired()])
    before_food = StringField('Before Food')
    after_food = StringField('After Food')
    morning = StringField('Morning')
    afternoon = StringField('Afternoon')
    evening = StringField('Evening')
    remarks = TextAreaField('Remarks')
    note = TextAreaField('Note')
    submit = SubmitField('Submit Prescription')

class ValidatePatientUsernameForm(FlaskForm):
    username = StringField('Patient Username', validators=[DataRequired()])
    submit = SubmitField('Validate Username')

    def validate_patient_username(self, patient_username):
        if not is_valid_patient_username(patient_username.data):
            raise ValidationError('Invalid patient username.')
class ReportUploadForm(FlaskForm):
    report = FileField('Upload Report', validators=[DataRequired()])
    submit = SubmitField('Upload')
