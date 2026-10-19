import re
from django import forms
from django.contrib import admin
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import render, redirect
from django.urls import path, reverse
from .models import InternAccess, AuditEvent, current_intern_batch, validate_intern_batch


class AccessForm(forms.ModelForm):
    class Meta:
        model = InternAccess
        fields = '__all__'

    def clean_reason(self):
        reason = self.cleaned_data['reason'].strip()
        if not reason:
            raise forms.ValidationError('Record the reason for this access decision.')
        return reason


class SemesterInviteForm(forms.Form):
    batch = forms.CharField(max_length=9, initial=current_intern_batch, validators=[validate_intern_batch],
        help_text="Consecutive batch years, for example 2026-2027. This label does not change grant dates.")
    emails = forms.CharField(widget=forms.Textarea, help_text='Paste an Excel email column. Line breaks, tabs, spaces, commas and semicolons are accepted; up to 500 unique addresses.')
    reason = forms.CharField(widget=forms.Textarea, max_length=2000)

    def clean_emails(self):
        validator = forms.EmailField()
        emails = []
        invalid_lines = []
        for number, line in enumerate(self.cleaned_data['emails'].splitlines(), start=1):
            for token in re.split(r'[\s,;]+', line.strip()):
                if not token:
                    continue
                try:
                    email = validator.clean(token).lower()
                except forms.ValidationError:
                    invalid_lines.append(number)
                    continue
                if email not in emails:
                    emails.append(email)
        if invalid_lines:
            lines = ', '.join(str(number) for number in sorted(set(invalid_lines)))
            raise forms.ValidationError(
                f'Check line(s) {lines}: paste email addresses only, without column headings or names. '
                'No invitations have been added. Correct these lines and submit again.')
        if not 1 <= len(emails) <= 500:
            raise forms.ValidationError('Enter between 1 and 500 unique email addresses.')
        return emails


@admin.register(InternAccess)
class InternAccessAdmin(admin.ModelAdmin):
    form = AccessForm
    list_display = ('email', 'batch', 'starts_at', 'expires_at', 'revoked')
    search_fields = ('email', 'batch')
    list_filter = ('batch', 'revoked')
    ordering = ('batch', 'email')
    list_per_page = 100
    change_list_template = 'admin/users/internaccess/change_list.html'

    class Media:
        js = ('users/intern_access_admin.js',)

    def changelist_view(self, request, extra_context=None):
        return super().changelist_view(request, extra_context={
            **(extra_context or {}), 'can_delete_access': self.has_delete_permission(request)})

    def get_actions(self, request):
        actions = super().get_actions(request)
        if 'delete_selected' in actions:
            action, name, _ = actions['delete_selected']
            actions['delete_selected'] = (action, name, 'Delete selected access (revoke immediately)')
        return actions

    def get_urls(self):
        return [path('invite/', self.admin_site.admin_view(self.invite_semester),
            name='users_internaccess_invite')] + super().get_urls()

    def invite_semester(self, request):
        if not self.has_add_permission(request):
            raise PermissionDenied
        form = SemesterInviteForm(request.POST if request.method == 'POST' else None)
        if request.method == 'POST' and form.is_valid():
            created_count = 0
            with transaction.atomic():
                for email in form.cleaned_data['emails']:
                    grant, created = InternAccess.objects.get_or_create(email=email,
                        defaults={'reason': form.cleaned_data['reason'], 'batch': form.cleaned_data['batch']})
                    if created:
                        created_count += 1
                        AuditEvent.objects.create(actor=request.user, action='access_change', object_id=str(grant.pk),
                            details={'after': {'email': grant.email, 'batch': grant.batch, 'expires_at': str(grant.expires_at), 'reason': grant.reason}})
            existing_count = len(form.cleaned_data['emails']) - created_count
            messages.success(request, f'Processed {len(form.cleaned_data["emails"])} unique addresses: granted one-year access to {created_count} new interns; {existing_count} already had grants. Existing grants were kept; edit them individually to extend or revoke.')
            return redirect(reverse('admin:users_internaccess_changelist'))
        context = {**self.admin_site.each_context(request), 'form': form, 'title': 'Invite semester interns', 'opts': self.model._meta}
        return render(request, 'admin/users/internaccess/invite.html', context)

    def save_model(self, request, obj, form, change):
        previous = InternAccess.objects.filter(pk=obj.pk).values('starts_at', 'expires_at', 'revoked', 'email', 'reason', 'batch').first()
        super().save_model(request, obj, form, change)
        after = {key: str(getattr(obj, key)) for key in ('email', 'starts_at', 'expires_at', 'revoked', 'reason', 'batch')}
        AuditEvent.objects.create(actor=request.user, action='access_change', object_id=str(obj.pk),
            details={'before': {k: str(v) for k, v in (previous or {}).items()}, 'after': after})

    def delete_queryset(self, request, queryset):
        with transaction.atomic():
            grants = list(queryset.select_for_update())
            for grant in grants:
                AuditEvent.objects.create(actor=request.user, action='access_delete', object_id=str(grant.pk),
                    details={'before': {'email': grant.email, 'batch': grant.batch,
                        'starts_at': grant.starts_at.isoformat(), 'expires_at': grant.expires_at.isoformat(),
                        'revoked': grant.revoked, 'reason': grant.reason},
                        'reason': 'Administrator confirmed deletion of intern access.'})
            self.model.objects.filter(pk__in=[grant.pk for grant in grants]).delete()

    def delete_model(self, request, obj):
        self.delete_queryset(request, self.model.objects.filter(pk=obj.pk))


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'actor', 'action', 'object_id')
    readonly_fields = ('actor', 'created_at', 'action', 'object_id', 'details')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
