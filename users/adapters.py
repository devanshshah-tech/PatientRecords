from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.core.exceptions import ImmediateHttpResponse
from django.shortcuts import redirect
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from allauth.account.models import EmailAddress
from .access import active_grant, can_review


class ClosedAccountAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request):
        return False


class InvitedSocialAdapter(DefaultSocialAccountAdapter):
    def can_authenticate_by_email(self, login, email):
        # Google is authoritative for Gmail and verified Workspace identities
        # carrying its hosted-domain claim. An arbitrary third-party Google
        # account's email_verified flag alone is insufficient for linking.
        profile = login.account.extra_data or {}
        authoritative = email.lower().endswith('@gmail.com') or bool(profile.get('hd'))
        if login.account.provider != 'google' or not authoritative:
            return False
        if not any(e.verified and e.email.lower() == email.lower() for e in login.email_addresses):
            return False
        candidates = list(get_user_model().objects.filter(email__iexact=email)[:2])
        return len(candidates) == 1 and candidates[0].is_active and (
            can_review(candidates[0]) or active_grant(email))

    def allowed(self, sociallogin):
        if sociallogin.account.provider != 'google':
            return False
        verified = [e.email for e in sociallogin.email_addresses if e.verified]
        return bool(verified) and (any(active_grant(e) for e in verified) or
            (sociallogin.is_existing and can_review(sociallogin.user)))

    def pre_social_login(self, request, sociallogin):
        if not self.allowed(sociallogin):
            raise ImmediateHttpResponse(redirect('access_denied'))
        # Email authentication can select a pre-created user without creating
        # an EmailAddress. Persist only the matching identity verified by Google,
        # so request-time checks can enforce that user's invitation afterward.
        if sociallogin.is_existing:
            for identity in sociallogin.email_addresses:
                if identity.verified and identity.email.lower() == sociallogin.user.email.lower():
                    try:
                        with transaction.atomic():
                            if EmailAddress.objects.filter(email__iexact=identity.email).exclude(user=sociallogin.user).exists():
                                raise IntegrityError
                            EmailAddress.objects.update_or_create(user=sociallogin.user,
                                email__iexact=identity.email,
                                defaults={'email': identity.email.lower(), 'verified': True})
                            profile = sociallogin.account.extra_data or {}
                            changed = []
                            for field, key in [('first_name', 'given_name'), ('last_name', 'family_name')]:
                                value = profile.get(key)
                                if not getattr(sociallogin.user, field) and isinstance(value, str) and value.strip():
                                    limit = sociallogin.user._meta.get_field(field).max_length
                                    setattr(sociallogin.user, field, value.strip()[:limit])
                                    changed.append(field)
                            if changed:
                                sociallogin.user.save(update_fields=changed)
                    except IntegrityError:
                        raise ImmediateHttpResponse(redirect('access_denied')) from None

    def is_open_for_signup(self, request, sociallogin):
        return self.allowed(sociallogin)
