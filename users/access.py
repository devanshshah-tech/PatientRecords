from allauth.account.models import EmailAddress
from django.utils import timezone
from .models import InternAccess


def can_review(user):
    return user.is_authenticated and user.is_active and user.has_perm('users.compare_patients')


def active_grant(email):
    now = timezone.now()
    return InternAccess.objects.filter(email__iexact=email, revoked=False,
        starts_at__lte=now, expires_at__gt=now).exists()


def can_submit(user):
    if not user.is_authenticated or not user.is_active:
        return False
    if can_review(user):
        return True
    return any(active_grant(email) for email in
        EmailAddress.objects.filter(user=user, verified=True).values_list('email', flat=True))
