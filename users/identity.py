"""Consistent account labels for the application and allauth notifications."""
from .access import can_review, can_submit


def display_name(user):
    return user.get_full_name().strip() or 'Your account'


def display_role(user):
    if can_review(user):
        return 'Doctor/Admin'
    return 'Intern' if can_submit(user) else 'Access inactive'


def user_display(user):
    return f'{display_name(user)} ({display_role(user)})'
