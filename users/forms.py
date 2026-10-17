from django import forms
import datetime
import uuid
from django.utils.safestring import mark_safe

current_date = datetime.datetime.now()
current_month = current_date.month

if current_month <= 3:  # January to March
    current_year = current_date.year - 1
else:  # April to December
    current_year = current_date.year
    
academic_year_choices = [(f"{year}-{year + 1}", f"{year}-{year + 1}") for year in range(current_year - 5, current_year + 6)]
default_academic_year = f"{current_year}-{current_year + 1}"

class DoctorSearchForm(forms.Form):
    patient_id = forms.CharField(label='UHID / Case No.', max_length=100, required=False)
    name_of_patient = forms.CharField(label='Patient name', max_length=200, required=False)
    opd_number = forms.CharField(label='Aadhar/ABHA ID', max_length=100, required=False)
    case_year = forms.CharField(label='Case year', max_length=100, required=False)
    diagnosis = forms.CharField(max_length=200, required=False)

    def clean(self):
        cleaned = super().clean()
        if not any(cleaned.values()):
            raise forms.ValidationError('Enter at least one search field.')
        return cleaned

class PatientDetailsForm(forms.Form):
    submission_id = forms.UUIDField(widget=forms.HiddenInput, initial=uuid.uuid4)
    patient_id = forms.RegexField(regex=r'^[A-Za-z0-9_-]+$', label='UHID / Case No.', max_length=100,
        help_text='Use the clinic-issued UHID or case number. Letters, numbers, hyphens and underscores only.')
    consent_confirmed = forms.BooleanField(label='I have obtained the patient’s consent for clinical photographs and storage.')
    opd_number = forms.CharField(label='Aadhar/ABHA ID', max_length=100, required=False)
    case_year = forms.CharField(label='Case Year', max_length=100)
    previous_opd_number = forms.CharField(label='Previous UHID / Case No.', max_length=100, required=False)
    previous_case_year = forms.CharField(label='Previous Case Year', max_length=100, required=False)
    name_of_patient = forms.CharField(label='Name of Patient', max_length=200)
    age = forms.IntegerField(label='Age', min_value=0, max_value=130)
    gender = forms.ChoiceField(label='Gender', choices=[('M', 'Male'), ('F', 'Female'), ('O', 'Other')])
    diagnosis = forms.CharField(label='Diagnosis', max_length=200)
    peripheral_opd = forms.CharField(label='Peripheral OPD Name', required=False)
    name_of_intern = forms.CharField(label='Name of Intern', max_length=200)
    academic_year = forms.ChoiceField(label="Academic Year", choices=academic_year_choices, initial=default_academic_year, required=False)
    roll_number = forms.CharField(label='Roll Number', max_length=100)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if field.required:
                field.label = mark_safe(f"{field.label} <span style='color: red;'>*</span>")
