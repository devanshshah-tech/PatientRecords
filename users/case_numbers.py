"""Shared case-number and private folder formatting; never log clinical input."""
import re
import unicodedata
from django.core.exceptions import ValidationError

ANAND = 'AnandHospital'
TF = 'TribhuvandasFoundation'
LOCATION_CHOICES = [(ANAND, 'Anand Hospital'), (TF, 'Tribhuvandas Foundation')]


def normalize_case_number(value, *, strict=False):
    value = str(value or '').strip()
    if re.fullmatch(r'[0-9]{1,6}', value) and int(value) > 0:
        return value.zfill(6)
    if strict:
        raise ValidationError('Enter a case number from 1 to 999999, using digits only.')
    return value


def folder_words(value):
    value = unicodedata.normalize('NFC', str(value)).strip()
    value = re.sub(r'[^\w-]+', '-', value, flags=re.UNICODE).strip('-_')
    if len(value) > 200:
        raise ValidationError('Patient names, intern names and visit reasons must be at most 200 characters.')
    return value or 'Unspecified'
