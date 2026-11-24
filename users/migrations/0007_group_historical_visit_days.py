from zoneinfo import ZoneInfo

from django.db import migrations
from django.utils import timezone


def group_visit_days(apps, schema_editor):
    Visit = apps.get_model('users', 'Visit')
    visits = Visit.objects.using(schema_editor.connection.alias)
    clinic_zone = ZoneInfo('Asia/Kolkata')
    previous_patient = None
    previous_day = None
    visit_number = 0
    pending = []

    for visit in visits.only('patient_id', 'created_at', 'visit_number').order_by(
            'patient_id', 'created_at', 'pk').iterator(chunk_size=500):
        day = timezone.localdate(visit.created_at, clinic_zone)
        if visit.patient_id != previous_patient:
            visit_number = 1
        elif day != previous_day:
            visit_number += 1
        previous_patient = visit.patient_id
        previous_day = day
        if visit.visit_number != visit_number:
            visit.visit_number = visit_number
            pending.append(visit)
        if len(pending) == 500:
            visits.bulk_update(pending, ['visit_number'])
            pending.clear()

    if pending:
        visits.bulk_update(pending, ['visit_number'])


class Migration(migrations.Migration):
    dependencies = [('users', '0006_allow_same_day_retakes')]
    operations = [migrations.RunPython(group_visit_days)]
